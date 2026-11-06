"""进群验证流程：进群出题、未验证发言拦截、按钮作答、超时处理与管理员操作。"""

from __future__ import annotations

import asyncio
import math
import secrets
import time
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain

from .api import QQGroupManageAPI
from .durations import parse_duration
from .join_verify import (
    ADMIN_EXEMPT_CALLBACK_RE,
    DEFAULT_PROMPT,
    MODE_ARITHMETIC,
    MODE_CUSTOM,
    TIMEOUT_FAIL,
    TIMEOUT_REMIND,
    VERIFY_CALLBACK_RE,
    check_custom_answer,
    make_arithmetic,
    parse_custom_questions,
    question_text,
    render_prompt,
    rules_text,
    verify_keyboard,
)

REMIND_COOLDOWN = 30
SCAN_INTERVAL = 30
API_TIMEOUT = 10
BOT_STATE_TIMEOUT = 3
BOT_ROLE_CACHE_SECONDS = 60
PASSED_TEXT = "验证通过，欢迎加入！"


class JoinVerifier:
    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        # 同一成员的作答、超时、放行和重新验证都在这把锁内串行执行，
        # 进锁后重新读取记录，保证状态变更与禁言、解禁的先后顺序一致。
        self._locks: dict[tuple[str, str, str], asyncio.Lock] = {}
        self._bot_roles: dict[tuple[str, str], tuple[float, bool | None]] = {}
        self._bot_role_warned: set[tuple[str, str]] = set()

    @property
    def storage(self) -> Any:
        return self.plugin.storage

    def _lock(self, key: tuple[str, str, str]) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    def _setting(self, umo: str, key: str, default: Any) -> Any:
        return self.plugin._group_setting(key, umo, default)

    def _int_setting(self, umo: str, key: str, default: int, minimum: int) -> int:
        return max(minimum, int(self._setting(umo, key, default)))

    async def enabled(self, umo: str, actor_id: str = "") -> bool:
        return await self.plugin._sdk_group_enabled(umo, actor_id=actor_id) and bool(
            self._setting(umo, "enable_join_verify", False)
        )

    # ---------- 出题与发送 ----------

    def _new_record(self, platform_id: str, group: str, member: str) -> dict[str, Any]:
        # 倒计时在题目送达后才开始，见 _send_first 和发言提醒补发题目。
        record = {
            "platform_id": platform_id,
            "group_openid": group,
            "member_openid": member,
            "status": "pending",
            "failures": 0,
            "joined_at": time.time(),
            "delivered": False,
            "deadline": 0,
            "timeout_handled": False,
            "last_remind_at": 0.0,
        }
        self._new_question(record, self.plugin._group_umo(platform_id, group))
        return record

    def _mark_delivered(self, record: dict[str, Any], umo: str) -> None:
        record["delivered"] = True
        timeout = self._int_setting(umo, "verify_timeout_minutes", 10, 0)
        record["deadline"] = time.time() + timeout * 60 if timeout else 0

    @staticmethod
    def _mark_undelivered(record: dict[str, Any]) -> None:
        """当前题目未送达：停止计时，算术题改为文字作答，等成员发言时补发。"""
        record["delivered"] = False
        record["deadline"] = 0
        if record["mode"] == "arithmetic":
            record["text_answer"] = True

    async def _send_first(self, platform: Any, record: dict[str, Any]) -> None:
        umo = self.plugin._group_umo(record["platform_id"], record["group_openid"])
        if await self.send_question(platform, record):
            self._mark_delivered(record, umo)
        else:
            self._mark_undelivered(record)
        self.storage.put_verification(record)

    def _new_question(self, record: dict[str, Any], umo: str) -> None:
        # 每道题都换新 token，旧消息上的按钮随之失效。
        record["token"] = secrets.token_hex(16)
        record["text_answer"] = False
        if self._setting(umo, "verify_mode", MODE_ARITHMETIC) == MODE_CUSTOM:
            questions, invalid = parse_custom_questions(
                list(self._setting(umo, "custom_questions", []) or [])
            )
            if invalid:
                logger.warning("[进群验证] 以下自定义问题格式或正则无效，已跳过：%s", invalid)
            if questions:
                question, pattern = secrets.choice(questions)
                record.update(mode="custom", question=question, answer=pattern, options=[])
                return
            logger.warning("[进群验证] %s 没有有效的自定义问题，改用算术题", umo)
        question, options, correct = make_arithmetic(
            list(self._setting(umo, "arithmetic_ops", []) or []),
            self._int_setting(umo, "arithmetic_max_number", 20, 2),
        )
        record.update(mode="arithmetic", question=question, options=options, answer=correct)

    def _rules(self, umo: str) -> str:
        return rules_text(
            self._int_setting(umo, "verify_max_failures", 3, 1),
            self._int_setting(umo, "verify_timeout_minutes", 10, 0),
            str(self._setting(umo, "verify_timeout_action", TIMEOUT_FAIL)),
        )

    async def send_question(
        self,
        platform: Any,
        record: dict[str, Any],
        *,
        intro: str = "",
        event_id: str = "",
    ) -> bool:
        """返回题目是否送达。intro 为空时使用面板模板；重新出题和超时提醒使用简短开头。

        调用方必须持有该成员的锁，且记录仍是存储中的有效记录。
        """
        umo = self.plugin._group_umo(record["platform_id"], record["group_openid"])
        allowed = await self.bot_role_allows_verification(
            record["platform_id"], record["group_openid"]
        )
        if allowed is False:
            logger.warning(
                "[进群验证] 机器人不是群管理员，取消发送验证题：%s",
                record["group_openid"],
            )
            return False
        template = (
            f"{{member_at}} {intro}\n\n{{question}}\n\n{{rules}}"
            if intro
            else str(self._setting(umo, "verify_prompt", DEFAULT_PROMPT) or "")
        )
        api = QQGroupManageAPI(platform.client)
        group, member = record["group_openid"], record["member_openid"]
        buttons = record["mode"] == "arithmetic" and not record["text_answer"]
        try:
            await asyncio.wait_for(
                api.send_group_markdown(
                    group,
                    render_prompt(
                        template, member, question_text(record), self._rules(umo), markdown=True
                    ),
                    event_id=event_id,
                    keyboard=verify_keyboard(record["token"], member, record["options"])
                    if buttons
                    else None,
                ),
                API_TIMEOUT,
            )
            return True
        except Exception:
            logger.warning("[进群验证] Markdown 题目发送失败，降级为普通文本", exc_info=True)
        if buttons:
            # 没有按钮可点时改为直接发送答案数字。
            record["text_answer"] = True
            self.storage.put_verification(record)
        try:
            await asyncio.wait_for(
                api.send_group_text(
                    group,
                    render_prompt(
                        template, member, question_text(record), self._rules(umo), markdown=False
                    ),
                    event_id=event_id,
                ),
                API_TIMEOUT,
            )
            return True
        except Exception:
            logger.exception("[进群验证] 验证题发送失败")
            return False

    async def _notice(
        self,
        platform: Any,
        record: dict[str, Any],
        text: str,
        *,
        event: AstrMessageEvent | None = None,
        event_id: str = "",
    ) -> None:
        """有消息事件时直接被动回复；否则艾特成员发送，Markdown 失败时降级。"""
        if event is not None:
            await self._reply(event, text)
            return
        api = QQGroupManageAPI(platform.client)
        group, member = record["group_openid"], record["member_openid"]
        try:
            await asyncio.wait_for(
                api.send_group_markdown(
                    group, f'<qqbot-at-user id="{member}" /> {text}', event_id=event_id
                ),
                API_TIMEOUT,
            )
            return
        except Exception:
            logger.warning("[进群验证] Markdown 提示发送失败，降级为普通文本", exc_info=True)
        try:
            await asyncio.wait_for(
                api.send_group_text(group, text, event_id=event_id), API_TIMEOUT
            )
        except Exception:
            logger.exception("[进群验证] 提示发送失败")

    async def _resend(self, event: AstrMessageEvent, record: dict[str, Any]) -> bool:
        """补发题目需要确认送达，不用 event.send：适配器会吞掉发送失败。

        插件接口在 HTTP 错误和超时时都会抛出异常，没有异常即视为送达。
        """
        try:
            await asyncio.wait_for(
                QQGroupManageAPI(self.plugin._platform(event).client).send_group_text(
                    event.get_group_id(),
                    "请先完成进群验证再发言：\n" + question_text(record),
                    msg_id=str(event.message_obj.message_id),
                ),
                API_TIMEOUT,
            )
        except Exception:
            logger.warning("[进群验证] 补发验证题失败", exc_info=True)
            return False
        return True

    @staticmethod
    async def _reply(event: AstrMessageEvent, text: str) -> None:
        try:
            await event.send(event.plain_result(text))
        except Exception:
            logger.exception("[进群验证] 回复消息失败")

    async def _recall(self, event: AstrMessageEvent) -> None:
        try:
            await asyncio.wait_for(
                QQGroupManageAPI(self.plugin._platform(event).client).recall_group_message(
                    event.get_group_id(), str(event.message_obj.message_id)
                ),
                API_TIMEOUT,
            )
        except Exception as exc:
            logger.warning("[进群验证] 撤回未验证成员的消息失败：%r", exc)

    async def _fail(
        self,
        platform: Any,
        record: dict[str, Any],
        *,
        event: AstrMessageEvent | None = None,
        event_id: str = "",
    ) -> None:
        """先落盘失败状态再禁言；禁言失败只记日志，仍等待管理员处理。"""
        umo = self.plugin._group_umo(record["platform_id"], record["group_openid"])
        record["status"] = "failed"
        self.storage.put_verification(record)
        duration = str(self._setting(umo, "verify_fail_mute_duration", "1天") or "1天")
        try:
            seconds = parse_duration(duration)
            if seconds == 0:
                raise ValueError("验证失败禁言时长必须大于 0")
            self.plugin._validate_duration(seconds, umo)
            await asyncio.wait_for(
                self.plugin._mute_on_platform(
                    platform, record["group_openid"], record["member_openid"], seconds
                ),
                API_TIMEOUT,
            )
            text = f"进群验证未通过，已禁言 {duration}，请等待管理员处理。"
        except Exception:
            logger.exception("[进群验证] 验证失败后禁言未成功")
            text = "进群验证未通过，请等待管理员处理。"
        await self._notice(platform, record, text, event=event, event_id=event_id)

    # ---------- 事件入口 ----------

    async def bot_role_allows_verification(
        self, platform_id: str, group: str
    ) -> bool | None:
        """Return whether the bot can moderate; None means the role is unknown.

        ``bot_state`` is a QQ whitelist endpoint. When it is unavailable we
        return None and keep the previous permissive behavior so verification
        does not stop working for every bot without that permission.
        """
        key = (platform_id, group)
        now = time.time()
        cached = self._bot_roles.get(key)
        if cached is not None and now - cached[0] < BOT_ROLE_CACHE_SECONDS:
            return cached[1]
        platform = self.plugin.context.get_platform_inst(platform_id)
        if platform is None:
            return None
        api = QQGroupManageAPI(platform.client)
        try:
            state = await asyncio.wait_for(
                api.get_bot_state(group),
                BOT_STATE_TIMEOUT,
            )
        except Exception as exc:
            self._bot_roles[key] = (now, None)
            if key not in self._bot_role_warned:
                self._bot_role_warned.add(key)
                logger.warning(
                    "[进群验证] 无法确认机器人群内角色，按兼容模式继续：%r",
                    exc,
                )
            return None
        role = str((state or {}).get("member_role") or "").strip().lower()
        allowed: bool | None
        if role in {"owner", "admin"}:
            allowed = True
        elif role == "member":
            allowed = False
        else:
            allowed = None
        self._bot_roles[key] = (now, allowed)
        if allowed is False and key not in self._bot_role_warned:
            self._bot_role_warned.add(key)
            logger.warning(
                "[进群验证] 机器人在群 %s 的角色是普通成员，已跳过进群验证出题",
                group,
            )
        return allowed

    async def prepare(self, platform_id: str, item: dict[str, Any]) -> dict[str, Any] | None:
        """进群后先登记待验证，欢迎消息发送期间也能拦截发言；题目由 deliver 发送。"""
        group = str(item.get("group_openid") or "")
        member = str(item.get("member_openid") or "")
        if not group or not member:
            return None
        try:
            if not await self.enabled(self.plugin._group_umo(platform_id, group)):
                return None
            allowed = await self.bot_role_allows_verification(platform_id, group)
            if allowed is False:
                return None
            async with self._lock((platform_id, group, member)):
                # 重复推送的进群事件不重新出题。
                if self.storage.verification(platform_id, group, member) is not None:
                    return None
                record = self._new_record(platform_id, group, member)
                self.storage.put_verification(record)
                return record
        except Exception:
            logger.exception("[进群验证] 创建进群验证失败")
            return None

    async def deliver(self, platform_id: str, record: dict[str, Any]) -> None:
        key = (platform_id, record["group_openid"], record["member_openid"])
        try:
            async with self._lock(key):
                # 等待期间可能已被放行、退群、重新验证，或已在发言时补发过题目。
                if self.storage.verification(*key) is not record or record["delivered"]:
                    return
                platform = self.plugin.context.get_platform_inst(platform_id)
                if platform is not None:
                    await self._send_first(platform, record)
        except Exception:
            logger.exception("[进群验证] 发送进群验证题失败")

    async def clear(self, platform_id: str, item: dict[str, Any]) -> None:
        group = str(item.get("group_openid") or "")
        member = str(item.get("member_openid") or "")
        if not group or not member:
            return
        try:
            async with self._lock((platform_id, group, member)):
                self.storage.remove_verification(platform_id, group, member)
        except Exception:
            logger.exception("[进群验证] 清理退群成员的验证记录失败")

    async def guard(self, event: AstrMessageEvent) -> None:
        key = (event.get_platform_id(), event.get_group_id(), event.get_sender_id())
        if self.storage.verification(*key) is None or not self.plugin._is_qq_group(event):
            return
        umo = self.plugin._event_group_umo(event)
        if not self._setting(umo, "enable_join_verify", False):
            return
        stop = True
        try:
            async with self._lock(key):
                record = self.storage.verification(*key)
                if record is None:
                    stop = False  # 排队期间已通过或被放行
                    return
                await self._guard_message(event, record, umo)
        except Exception:
            logger.exception("[进群验证] 处理未验证成员的消息失败")
        finally:
            # 未验证成员的消息不再交给指令、违禁词和 LLM 处理。
            if stop:
                event.stop_event()

    async def _guard_message(
        self, event: AstrMessageEvent, record: dict[str, Any], umo: str
    ) -> None:
        text = "".join(
            part.text for part in event.get_messages() if isinstance(part, Plain)
        ).strip()
        now = time.time()
        if record["status"] == "pending" and not record["delivered"]:
            # 题目还没送达：回复本条消息补发文字题，确认送达后才开始计时，本条消息不计作答。
            self._mark_undelivered(record)
            if await self._resend(event, record):
                self._mark_delivered(record, umo)
                record["last_remind_at"] = now
            self.storage.put_verification(record)
            await self._recall(event)
            return
        answering = (
            record["status"] == "pending"
            and (record["mode"] == "custom" or record["text_answer"])
            and bool(text)
        )
        if not answering:
            if now - record["last_remind_at"] >= REMIND_COOLDOWN:
                record["last_remind_at"] = now
                self.storage.put_verification(record)
                await self._reply(
                    event,
                    "你未通过进群验证，请等待管理员处理。"
                    if record["status"] == "failed"
                    else "请先完成进群验证再发言：\n" + question_text(record),
                )
            await self._recall(event)
            return

        if record["mode"] == "custom":
            try:
                correct = check_custom_answer(record["answer"], text)
            except (ValueError, TimeoutError):
                logger.exception("[进群验证] 验证题正则无效或匹配超时：%s", record["question"])
                await self._reply(event, "验证题配置有误，本次作答不计次数，请联系管理员。")
                return
        else:
            correct = text == record["options"][record["answer"]]
        if correct:
            self.storage.remove_verification(
                record["platform_id"], record["group_openid"], record["member_openid"]
            )
            await self._reply(event, PASSED_TEXT)
            return

        record["failures"] += 1
        maximum = self._int_setting(umo, "verify_max_failures", 3, 1)
        if record["failures"] >= maximum:
            await self._fail(self.plugin._platform(event), record, event=event)
        else:
            self.storage.put_verification(record)
            await self._reply(
                event, f"答错了，还剩 {maximum - record['failures']} 次机会。"
            )
        await self._recall(event)

    async def handle_interaction(self, platform_id: str, interaction: Any) -> bool:
        resolved = getattr(getattr(interaction, "data", None), "resolved", None)
        data = str(getattr(resolved, "button_data", "") or "")
        exempt = ADMIN_EXEMPT_CALLBACK_RE.fullmatch(data) is not None
        if not exempt and not data.startswith("qqgv:"):
            return False
        platform = self.plugin.context.get_platform_inst(platform_id)
        interaction_id = str(getattr(interaction, "id", "") or "")
        if platform is None or not interaction_id:
            return True
        api = QQGroupManageAPI(platform.client)

        async def acknowledge(code: int) -> None:
            try:
                await asyncio.wait_for(api.acknowledge_interaction(interaction_id, code), 3)
            except Exception:
                logger.warning("[进群验证] 回应验证按钮失败", exc_info=True)

        match = VERIFY_CALLBACK_RE.fullmatch(data)
        group = str(getattr(interaction, "group_openid", "") or "")
        sender = str(getattr(interaction, "group_member_openid", "") or "")
        if (
            (not exempt and not match)
            or not group
            or not sender
            or getattr(interaction, "type", None) != 11
            or getattr(interaction, "chat_type", None) != 1
        ):
            await acknowledge(4)
            return True
        if exempt:
            return await self._handle_admin_exempt(
                platform_id,
                platform,
                api,
                resolved,
                interaction_id,
                str(getattr(interaction, "event_id", "") or interaction_id),
                acknowledge,
                group,
                sender,
            )
        if getattr(resolved, "button_id", None) != f"qqgv-{match.group(2)}":
            await acknowledge(4)
            return True
        token, index = match.group(1), int(match.group(2))
        umo = self.plugin._group_umo(platform_id, group)
        if not await self.enabled(umo, actor_id=sender):
            await acknowledge(4)
            return True
        key = (platform_id, group, sender)
        # 按点击者查找记录，别人的题目按钮对他无效。
        if self.storage.verification(*key) is None:
            await acknowledge(4)
            return True
        lock = self._lock(key)
        if lock.locked():
            await acknowledge(2)  # 上一次点击或其他操作仍在处理
            return True
        try:
            async with lock:
                record = self.storage.verification(*key)
                if (
                    record is None
                    or record["token"] != token
                    or record["status"] != "pending"
                    or record["text_answer"]
                ):
                    await acknowledge(3)  # 已放行、已换题、已失败或改为文字作答
                    return True
                await acknowledge(0)
                event_id = str(getattr(interaction, "event_id", "") or interaction_id)
                if index == record["answer"]:
                    self.storage.remove_verification(*key)
                    await self._notice(platform, record, PASSED_TEXT, event_id=event_id)
                    return True
                record["failures"] += 1
                maximum = self._int_setting(umo, "verify_max_failures", 3, 1)
                if record["failures"] >= maximum:
                    await self._fail(platform, record, event_id=event_id)
                    return True
                # 选错就换题，避免逐个尝试选项。
                self._new_question(record, umo)
                self.storage.put_verification(record)
                if not await self.send_question(
                    platform,
                    record,
                    intro=f"选错了，还剩 {maximum - record['failures']} 次机会，请重新作答：",
                    event_id=event_id,
                ):
                    # 旧按钮已失效、新题又没送达，不能继续沿用旧题的计时。
                    self._mark_undelivered(record)
                    self.storage.put_verification(record)
        except Exception:
            logger.exception("[进群验证] 处理验证按钮失败")
        return True

    # ---------- 管理员免除 ----------

    async def _admin_role_ok(
        self, api: QQGroupManageAPI, group: str, sender: str
    ) -> bool | None:
        """实时查询点击者角色；None 表示暂时无法确认，避免误判为无权限。"""
        guard = getattr(self.plugin, "_callback_guard", None)
        if guard is not None and not guard.start_lookup():
            return None
        try:
            member = await asyncio.wait_for(
                api.get_group_member_info(group, sender), 2
            )
        except Exception:
            logger.exception("[进群验证] 无法确认点击「管理员免除」的成员身份")
            return None
        finally:
            if guard is not None:
                guard.finish_lookup()
        return (
            isinstance(member, dict)
            and (
                not member.get("member_openid")
                or member.get("member_openid") == sender
            )
            and member.get("member_role") in {"owner", "admin"}
        )

    async def _handle_admin_exempt(
        self,
        platform_id: str,
        platform: Any,
        api: QQGroupManageAPI,
        resolved: Any,
        interaction_id: str,
        event_id: str,
        acknowledge: Any,
        group: str,
        sender: str,
    ) -> bool:
        """管理员点击「管理员免除」：直接放行该题对应的成员，失败禁言中的一并解禁。"""
        data = str(getattr(resolved, "button_data", "") or "")
        match = ADMIN_EXEMPT_CALLBACK_RE.fullmatch(data)
        if (
            match is None
            or getattr(resolved, "button_id", None) != f"qqgex-{match.group(1)}"
        ):
            await acknowledge(4)
            return True
        token = match.group(1)
        umo = self.plugin._group_umo(platform_id, group)
        if not await self.enabled(umo, actor_id=sender):
            await acknowledge(4)
            return True
        guard = getattr(self.plugin, "_callback_guard", None)
        # 插件管理员名单生效是即时的；群主/群管理员再实时查询一次角色。
        assigned = sender in self.plugin._callback_admin_ids(platform_id, group)
        if guard is not None:
            denial = guard.check_click(
                platform_id, group, sender, assigned_admin=assigned
            )
            if denial is not None:
                await acknowledge(denial)
                return True
        if not assigned:
            allowed = await self._admin_role_ok(api, group, sender)
            if allowed is None:
                await acknowledge(1)
                return True
            if not allowed:
                if guard is not None:
                    guard.remember_denied(platform_id, group, sender)
                await acknowledge(4)
                return True
        record = self.storage.find_verification_by_token(token)
        if (
            record is None
            or record.get("platform_id") != platform_id
            or record.get("group_openid") != group
        ):
            await acknowledge(3)  # 已放行、已换题或记录已清理
            return True
        member = str(record["member_openid"])
        key = (platform_id, group, member)
        lock = self._lock(key)
        if lock.locked():
            await acknowledge(2)  # 该成员正在作答
            return True
        try:
            async with lock:
                record = self.storage.verification(*key)
                if record is None or record["token"] != token:
                    await acknowledge(3)
                    return True
                await acknowledge(0)
                self.storage.remove_verification(*key)
                text = "管理员已免除该成员的进群验证，欢迎加入！"
                if record["status"] == "failed":
                    try:
                        await asyncio.wait_for(
                            self.plugin._mute_on_platform(platform, group, member, 0),
                            API_TIMEOUT,
                        )
                    except Exception:
                        logger.exception("[进群验证] 管理员免除后解除禁言失败")
                        text += "（解除禁言失败，请手动解禁）"
                await self._notice(platform, record, text, event_id=event_id)
        except Exception:
            logger.exception("[进群验证] 处理管理员免除失败")
        return True

    # ---------- 超时 ----------

    async def run(self) -> None:
        while True:
            await asyncio.sleep(SCAN_INTERVAL)
            try:
                await self.check_timeouts()
            except Exception:
                logger.exception("[进群验证] 检查验证超时失败")

    @staticmethod
    def _timed_out(record: dict[str, Any], now: float) -> bool:
        return (
            record["status"] == "pending"
            and not record["timeout_handled"]
            and bool(record["deadline"])
            and now >= record["deadline"]
        )

    async def check_timeouts(self) -> None:
        now = time.time()
        for record in self.storage.verifications():
            if not self._timed_out(record, now):
                continue
            key = (record["platform_id"], record["group_openid"], record["member_openid"])
            lock = self._lock(key)
            if lock.locked():
                continue  # 正在作答或被管理员处理，下一轮再看
            umo = self.plugin._group_umo(key[0], key[1])
            if not await self.enabled(umo):
                continue
            platform = self.plugin.context.get_platform_inst(key[0])
            if platform is None:
                continue
            async with lock:
                # 进锁后重新确认，已通过、退群或重新验证的成员不再处理。
                record = self.storage.verification(*key)
                if record is None or not self._timed_out(record, now):
                    continue
                record["timeout_handled"] = True
                self.storage.put_verification(record)
                action = str(self._setting(umo, "verify_timeout_action", TIMEOUT_FAIL))
                if action == TIMEOUT_REMIND:
                    await self.send_question(
                        platform, record, intro="验证时间已到，请尽快完成进群验证："
                    )
                elif action == TIMEOUT_FAIL:
                    await self._fail(platform, record)

    # ---------- 管理员指令 ----------

    async def _unmute(self, event: AstrMessageEvent, member: str) -> str:
        try:
            await asyncio.wait_for(
                self.plugin._mute_on_platform(
                    self.plugin._platform(event), event.get_group_id(), member, 0
                ),
                API_TIMEOUT,
            )
        except Exception as exc:
            return f"- {member}：{exc}"
        return ""

    async def release(self, event: AstrMessageEvent, targets: list[str]) -> str:
        released = 0
        failures: list[str] = []
        for member in targets:
            key = (event.get_platform_id(), event.get_group_id(), member)
            # 等该成员正在进行的失败禁言结束后再解禁，保证解禁在后。
            async with self._lock(key):
                record = self.storage.remove_verification(*key)
                if record is None:
                    continue
                released += 1
                if record["status"] == "failed" and (error := await self._unmute(event, member)):
                    failures.append(error)
        if not released:
            return "被艾特的成员都没有待处理的进群验证。"
        result = f"已放行 {released} 名成员。"
        if failures:
            result += "\n以下成员解除禁言失败，请手动解禁：\n" + "\n".join(failures)
        return result

    async def restart(self, event: AstrMessageEvent, targets: list[str]) -> str:
        umo = self.plugin._event_group_umo(event)
        if not self._setting(umo, "enable_join_verify", False):
            return "本群未开启进群验证。"
        platform = self.plugin._platform(event)
        failures: list[str] = []
        for member in targets:
            key = (event.get_platform_id(), event.get_group_id(), member)
            async with self._lock(key):
                old = self.storage.verification(*key)
                if old is not None and old["status"] == "failed":
                    if error := await self._unmute(event, member):
                        failures.append(error)
                record = self._new_record(*key)
                self.storage.put_verification(record)
                await self._send_first(platform, record)
        result = f"已让 {len(targets)} 名成员重新验证。"
        if failures:
            result += "\n以下成员解除禁言失败，可能无法作答：\n" + "\n".join(failures)
        return result

    def listing(self, event: AstrMessageEvent) -> str:
        now = time.time()
        records = [
            record
            for record in self.storage.verifications()
            if record["platform_id"] == event.get_platform_id()
            and record["group_openid"] == event.get_group_id()
        ]
        if not records:
            return "本群没有待处理的进群验证。"
        lines = [f"本群进群验证：{len(records)} 人"]
        for record in records:
            if record["status"] == "failed":
                status = "验证失败，等待管理员处理"
            else:
                status = f"待验证，已答错 {record['failures']} 次"
                deadline = record["deadline"]
                if not record["delivered"]:
                    status += "，题目未送达，发言时补发"
                elif deadline:
                    left = math.ceil((deadline - now) / 60)
                    status += f"，剩余 {left} 分钟" if left > 0 else "，已超时"
            lines.append(f"- {record['member_openid']}：{status}")
        return "\n".join(lines)
