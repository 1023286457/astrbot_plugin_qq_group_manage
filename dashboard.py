"""WebUI 可视化视图的后端 API。

视图运行在 Dashboard 的受限 iframe 中，所有请求都经由 bridge 转发到
``context.register_web_api()`` 注册的插件路由。这里的每个 handler 都只返回
JSON，不依赖 Quart/FastAPI 的请求对象。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from astrbot.api import logger

from .api import QQGroupManageAPI
from .durations import parse_duration
from .group_config import GROUP_SECTIONS, SCHEMA, GroupConfig, valid_group_umo
from .join_verify import parse_custom_questions
from .keyword_rules import compile_join_pattern
from .panel import (
    PANEL_IMAGE_KEYS,
    delete_image,
    image_data_url,
    image_meta,
    save_image,
)

try:  # AstrBot >= 4.26.0
    from astrbot.api.web import (
        error_response,
        file_response,
        json_response,
        request,
    )

    WEB_API_AVAILABLE = True
    WEB_API_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - 仅在旧的 AstrBot 上触发
    error_response = None  # type: ignore[assignment]
    file_response = None  # type: ignore[assignment]
    json_response = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]
    WEB_API_AVAILABLE = False
    WEB_API_IMPORT_ERROR = str(exc)

PLUGIN_NAME = "astrbot_plugin_qq_group_manage"
PLUGIN_DISPLAY_NAME = "QQ官机群管"
PLUGIN_VERSION = "2.9.7"
QQ_PLATFORMS = {"qq_official", "qq_official_webhook"}
VIEW_NAME = "console"
SECTION_ORDER = (
    "scope_settings",
    "permission_settings",
    "command_settings",
    "join_request_settings",
    "member_notice_settings",
    "llm_tool_settings",
    "limit_settings",
    "keyword_settings",
    "verify_settings",
    "spam_settings",
)
SECTION_ICONS = {
    "scope_settings": "globe",
    "permission_settings": "shield",
    "command_settings": "terminal",
    "join_request_settings": "inbox",
    "member_notice_settings": "bell",
    "llm_tool_settings": "sparkles",
    "limit_settings": "gauge",
    "keyword_settings": "filter",
    "verify_settings": "badge-check",
    "spam_settings": "activity",
}
SECTION_FOR_KEY: dict[str, str] = {}
for _section in SECTION_ORDER:
    for _key in SCHEMA.get(_section, {}).get("items", {}):
        SECTION_FOR_KEY[_key] = _section
del _section, _key

DURATION_KEYS = {
    "default_mute_duration",
    "keyword_mute_duration",
    "verify_fail_mute_duration",
    "spam_mute_duration",
}
INT_RANGES = {
    "join_request_page_size": (1, 100),
    "pending_retention_days": (1, 365),
    "max_mute_seconds": (1, 31536000),
    "arithmetic_max_number": (2, 1000),
    "verify_max_failures": (1, 20),
    "verify_timeout_minutes": (0, 1440),
    "spam_limit_1s": (0, 1000),
    "spam_limit_1m": (0, 100000),
    "spam_limit_1h": (0, 1000000),
    "spam_night_limit": (0, 100000),
    "spam_recall_threshold": (0, 100),
}
INT_UNITS = {
    "spam_limit_1s": "条/秒",
    "spam_limit_1m": "条/分",
    "spam_limit_1h": "条/小时",
    "spam_night_limit": "条/分",
    "spam_recall_threshold": "条",
}
SPAM_KEYS = (
    "enable_anti_spam",
    "spam_limit_1s",
    "spam_limit_1m",
    "spam_limit_1h",
    "spam_night_enabled",
    "spam_night_limit",
    "spam_mute_duration",
    "spam_recall_threshold",
)
RECALL_KEYS = (
    "enable_link_recall",
    "link_recall_notice",
    "enable_qr_recall",
    "qr_recall_notice",
)
LIST_CHOICES = {
    "arithmetic_ops": ["加", "减", "乘", "除"],
}
REGEX_LIST_KEYS = {"join_whitelist_words", "join_blacklist_words"}
APPLY_SOURCE_NAMES = {
    "self_apply": "自主申请",
    "search": "搜索群聊申请",
    "scan_qr_code": "扫描二维码申请",
    "group_card": "群分享卡片申请",
    "shared_card": "群分享卡片申请",
    "invited": "受邀加入",
    "invite": "受邀加入",
    "admin_invite": "管理员邀请",
}
STATUS_LABELS = {
    "pending": "待验证",
    "failed": "验证失败",
}
THEME_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class DashboardError(Exception):
    """可以直接展示给前端面板的业务错误。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _short(value: Any, keep_start: int = 6, keep_end: int = 4) -> str:
    text = str(value or "").strip()
    if len(text) <= keep_start + keep_end + 1:
        return text
    return f"{text[:keep_start]}…{text[-keep_end:]}"


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class DashboardAPI:
    """把插件状态与操作暴露给 ``pages/console`` 视图。"""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self.context = plugin.context
        self._broadcast_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 路由注册
    # ------------------------------------------------------------------
    def register(self) -> bool:
        if not WEB_API_AVAILABLE:
            logger.warning(
                "[%s] 当前 AstrBot 缺少 astrbot.api.web（%s），"
                "WebUI 视图将不可用，请升级到 4.26.0 及以上版本。",
                PLUGIN_NAME,
                WEB_API_IMPORT_ERROR,
            )
            return False
        register = getattr(self.context, "register_web_api", None)
        if not callable(register):
            logger.warning("[%s] 当前 AstrBot 不支持 register_web_api", PLUGIN_NAME)
            return False

        prefix = f"/{PLUGIN_NAME}/"
        registered = getattr(self.context, "registered_web_apis", None)
        if isinstance(registered, list):
            registered[:] = [
                api for api in registered if not str(api[0]).startswith(prefix)
            ]

        routes = (
            ("overview", self.get_overview, ["GET"], "群管总览"),
            ("pending", self.get_pending, ["GET"], "待审批入群申请"),
            ("pending/review", self.review_pending, ["POST"], "审批入群申请"),
            ("verifications", self.get_verifications, ["GET"], "进群验证队列"),
            (
                "verifications/release",
                self.release_verification,
                ["POST"],
                "放行进群验证",
            ),
            (
                "verifications/release-all",
                self.release_all_verifications,
                ["POST"],
                "一键放行进群验证",
            ),
            (
                "verifications/retry",
                self.retry_verification,
                ["POST"],
                "重新发起进群验证",
            ),
            ("groups", self.get_groups, ["GET"], "群组列表"),
            ("groups/detail", self.get_group_detail, ["GET"], "群组详情"),
            ("groups/admins", self.update_group_admins, ["POST"], "维护群管名单"),
            ("groups/note", self.update_group_note, ["POST"], "保存群备注"),
            ("spam", self.get_spam, ["GET"], "刷屏监控状态"),
            ("recall", self.get_recall, ["GET"], "风险消息撤回状态"),
            ("broadcast/send", self.send_broadcast, ["POST"], "群广播"),
            ("panel/images", self.get_panel_images, ["GET"], "群管面板图片"),
            ("panel/images/save", self.save_panel_image, ["POST"], "保存群管面板图片"),
            ("panel/images/delete", self.delete_panel_image, ["POST"], "删除群管面板图片"),
            ("config", self.get_config, ["GET"], "读取插件配置"),
            ("config/save", self.save_config, ["POST"], "保存插件配置"),
            (
                "config/group/create",
                self.create_group_profile,
                ["POST"],
                "创建分群配置",
            ),
            (
                "config/group/delete",
                self.delete_group_profile,
                ["POST"],
                "恢复继承全局配置",
            ),
            ("ui/preferences", self.get_ui_preferences, ["GET"], "读取界面偏好"),
            (
                "ui/preferences/save",
                self.save_ui_preferences,
                ["POST"],
                "保存界面偏好",
            ),
            ("export/state", self.export_state, ["GET"], "导出运行数据"),
            ("export/config", self.export_config, ["GET"], "导出插件配置"),
            ("import/preview", self.import_preview, ["POST"], "预览安全导入"),
            ("import/state", self.import_state, ["POST"], "导入运行数据"),
            ("import/config", self.import_config, ["POST"], "导入插件配置"),
        )
        for route, handler, methods, desc in routes:
            register(f"{prefix}{route}", handler, methods, desc)
        return True

    def unregister(self) -> None:
        prefix = f"/{PLUGIN_NAME}/"
        registered = getattr(self.context, "registered_web_apis", None)
        if isinstance(registered, list):
            registered[:] = [
                api for api in registered if not str(api[0]).startswith(prefix)
            ]

    # ------------------------------------------------------------------
    # 通用辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _error(exc: Exception, fallback: str = "操作失败，请稍后重试"):
        if isinstance(exc, DashboardError):
            return error_response(str(exc), status_code=exc.status_code)
        logger.exception("[%s] WebUI API 执行失败", PLUGIN_NAME)
        return error_response(fallback, status_code=500)

    def _platforms(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        try:
            platforms = self.context.platform_manager.platform_insts
        except Exception:
            return result
        for platform in platforms:
            try:
                meta = platform.meta()
            except Exception:
                continue
            if getattr(meta, "name", "") not in QQ_PLATFORMS:
                continue
            client = getattr(platform, "client", None)
            result.append(
                {
                    "id": str(getattr(meta, "id", "") or ""),
                    "name": str(getattr(meta, "name", "") or ""),
                    "online": client is not None,
                    "appid": str(getattr(platform, "appid", "") or ""),
                }
            )
        return result

    def _platform(self, platform_id: str) -> Any:
        for platform in self.context.platform_manager.platform_insts:
            try:
                if platform.meta().id == platform_id:
                    return platform
            except Exception:
                continue
        return None

    def _platform_name(self, platform_id: str) -> str:
        for platform in self._platforms():
            if platform["id"] == platform_id:
                return platform["name"]
        return platform_id

    @staticmethod
    def _group_umo(platform_id: str, group_openid: str) -> str:
        return f"{platform_id}:GroupMessage:{group_openid}"

    def _global_value(self, key: str, default: Any = None) -> Any:
        try:
            return self.plugin._config(key, default)
        except Exception:
            return default

    def _group_value(self, key: str, umo: str, default: Any = None) -> Any:
        try:
            return self.plugin._group_setting(key, umo, default)
        except Exception:
            return self._global_value(key, default)

    def _profile_state(self, umo: str) -> dict[str, Any]:
        try:
            data = GroupConfig(self.plugin.config).data
        except Exception:
            return {"exists": False, "confirmed": False, "note": ""}
        matches = [
            profile
            for profile in data.get("groups", [])
            if isinstance(profile, dict) and profile.get("umo") == umo
        ]
        if not matches:
            return {"exists": False, "confirmed": False, "note": ""}
        profile = matches[0]
        return {
            "exists": True,
            "confirmed": bool(profile.get("confirmed", True)),
            "note": str(profile.get("migration_note") or ""),
            "duplicate": len(matches) > 1,
        }

    # ------------------------------------------------------------------
    # 群组
    # ------------------------------------------------------------------
    def _known_groups(self) -> dict[str, dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        storage = self.plugin.storage

        def add(
            umo: str,
            platform_id: str,
            source: str,
            *,
            group_openid: str = "",
        ) -> dict[str, Any] | None:
            if not valid_group_umo(umo):
                return None
            item = groups.get(umo)
            if item is None:
                item = {
                    "umo": umo,
                    "platform_id": platform_id,
                    "group_openid": group_openid or umo.rsplit(":", 1)[-1],
                    "sources": set(),
                    "pending_count": 0,
                    "verification_count": 0,
                }
                groups[umo] = item
            item["sources"].add(source)
            return item

        try:
            profiles = GroupConfig(self.plugin.config).data.get("groups", [])
        except Exception:
            profiles = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            umo = str(profile.get("umo") or "").strip()
            item = add(umo, umo.split(":", 1)[0] if ":" in umo else "", "profile")
            if item is not None:
                item["confirmed"] = bool(profile.get("confirmed", True))

        try:
            pending = list(storage.data.get("pending", {}).values())
        except Exception:
            pending = []
        for entry in pending:
            if not isinstance(entry, dict):
                continue
            platform_id = str(entry.get("platform_id") or "")
            group_openid = str(entry.get("group_openid") or "")
            if not platform_id or not group_openid:
                continue
            umo = self._group_umo(platform_id, group_openid)
            item = add(umo, platform_id, "pending", group_openid=group_openid)
            if item is not None:
                item["pending_count"] += 1

        try:
            verifications = storage.verifications()
        except Exception:
            verifications = []
        for entry in verifications:
            if not isinstance(entry, dict):
                continue
            platform_id = str(entry.get("platform_id") or "")
            group_openid = str(entry.get("group_openid") or "")
            if not platform_id or not group_openid:
                continue
            umo = self._group_umo(platform_id, group_openid)
            item = add(umo, platform_id, "verification", group_openid=group_openid)
            if item is not None:
                item["verification_count"] += 1

        try:
            seen_groups = storage.seen_groups()
        except Exception:
            seen_groups = []
        for entry in seen_groups:
            if not isinstance(entry, dict):
                continue
            platform_id = str(entry.get("platform_id") or "")
            group_openid = str(entry.get("group_openid") or "")
            last_seen = str(entry.get("last_seen") or "")
            if not platform_id or not group_openid:
                continue
            umo = self._group_umo(platform_id, group_openid)
            item = add(umo, platform_id, "seen", group_openid=group_openid)
            if item is not None and last_seen:
                item["last_seen"] = max(str(item.get("last_seen") or ""), last_seen)

        # 群管名单只记录 group_openid；只有一个 QQ 平台时可以安全补全 UMO。
        platforms = self._platforms()
        if len(platforms) == 1:
            platform_id = platforms[0]["id"]
            try:
                admin_groups = storage.data.get("group_admins", {})
            except Exception:
                admin_groups = {}
            for group_openid in admin_groups:
                if group_openid:
                    add(
                        self._group_umo(platform_id, str(group_openid)),
                        platform_id,
                        "admins",
                        group_openid=str(group_openid),
                    )

        for item in groups.values():
            item["sources"] = sorted(item["sources"])
        try:
            uid_map = storage.ensure_group_uids(list(groups))
        except Exception:
            logger.exception("[%s] 分配群 UID 失败", PLUGIN_NAME)
            uid_map = {}
        for umo, item in groups.items():
            item["group_uid"] = uid_map.get(umo, "")
        return groups

    def _group_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        umo = item["umo"]
        platform_id = item.get("platform_id", "")
        group_openid = item.get("group_openid", "")
        profile = self._profile_state(umo)
        try:
            admins = self.plugin.storage.group_admins(group_openid)
        except Exception:
            admins = []
        platform = self._platform(platform_id)
        platform_name = self._platform_name(platform_id) if platform_id else "未关联平台"
        return {
            "umo": umo,
            "platform_id": platform_id,
            "platform_name": platform_name,
            "group_openid": group_openid,
            "group_uid": str(item.get("group_uid") or ""),
            "label": f"{platform_name} · {_short(group_openid, 8, 4)}",
            "profile": profile,
            "confirmed": bool(profile.get("confirmed", False)),
            "admins": admins,
            "admin_count": len(admins),
            "pending_count": int(item.get("pending_count", 0)),
            "verification_count": int(item.get("verification_count", 0)),
            "platform_online": platform is not None,
            "whitelisted": bool(self.plugin._umo_enabled(umo)),
            "last_seen": str(item.get("last_seen") or ""),
            "note": self.plugin.storage.group_note(umo),
            "sources": item.get("sources", []),
        }

    def _group_summaries(self) -> list[dict[str, Any]]:
        items = [self._group_summary(item) for item in self._known_groups().values()]
        items.sort(
            key=lambda item: (
                not item["profile"]["exists"],
                not item["platform_online"],
                -item["pending_count"],
                -item["verification_count"],
                item["umo"],
            )
        )
        return items

    def _features(self, umo: str = "") -> list[dict[str, Any]]:
        try:
            from .main import FEATURES
        except Exception:
            return []
        result: list[dict[str, Any]] = []
        for feature in FEATURES:
            raw = (
                self._group_value(feature.key, umo, feature.default)
                if umo
                else self._global_value(feature.key, feature.default)
            )
            enabled = not bool(raw) if feature.inverted else bool(raw)
            result.append(
                {
                    "name": feature.name,
                    "key": feature.key,
                    "category": feature.category,
                    "enabled": enabled,
                    "global_enabled": not bool(
                        self._global_value(feature.key, feature.default)
                    )
                    if feature.inverted
                    else bool(self._global_value(feature.key, feature.default)),
                }
            )
        return result

    # ------------------------------------------------------------------
    # 入群申请
    # ------------------------------------------------------------------
    @staticmethod
    def _pending_id(item: dict[str, Any]) -> str:
        raw = "\x1f".join(
            [
                str(item.get("platform_id") or ""),
                str(item.get("group_openid") or ""),
                str(item.get("join_request_id") or ""),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def _pending_items(self) -> list[dict[str, Any]]:
        storage = self.plugin.storage
        try:
            storage.prune()
            raw_items = list(storage.data.get("pending", {}).items())
        except Exception:
            raw_items = []
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for _, item in raw_items:
            if not isinstance(item, dict):
                continue
            platform_id = str(item.get("platform_id") or "")
            group_openid = str(item.get("group_openid") or "")
            request_id = str(item.get("join_request_id") or "")
            if not platform_id or not group_openid or not request_id:
                continue
            if storage.is_reviewed(platform_id, group_openid, request_id):
                continue
            pending_id = self._pending_id(item)
            if pending_id in seen:
                continue
            seen.add(pending_id)
            umo = self._group_umo(platform_id, group_openid)
            verify = item.get("verify_info")
            if not isinstance(verify, dict):
                verify = {}
            qa_list = verify.get("review_qa_list") or []
            questions = []
            if isinstance(qa_list, list):
                for qa in qa_list[:10]:
                    if not isinstance(qa, dict):
                        continue
                    questions.append(
                        {
                            "question": str(qa.get("question") or "")[:1000],
                            "answer": str(qa.get("answer") or "")[:1000],
                        }
                    )
            source = str(item.get("apply_source") or "")
            platform = self._platform(platform_id)
            result.append(
                {
                    "id": pending_id,
                    "group_umo": umo,
                    "group_label": f"{self._platform_name(platform_id)} · "
                    f"{_short(group_openid, 8, 4)}",
                    "platform_id": platform_id,
                    "platform_name": self._platform_name(platform_id),
                    "nickname": str(item.get("username") or "未提供昵称")[:80],
                    "apply_at": str(item.get("apply_at") or ""),
                    "stored_at": str(item.get("stored_at") or ""),
                    "source": APPLY_SOURCE_NAMES.get(
                        source.lower(), "其他来源" if source else "未提供"
                    ),
                    "risk_tips": str(item.get("risk_tips") or "")[:500],
                    "verify_message": str(verify.get("verify_message") or "")[:1000],
                    "questions": questions,
                    "auto_approved": bool(item.get("auto_approved")),
                    "can_review": platform is not None
                    and getattr(platform, "client", None) is not None,
                    "age_seconds": self._age_seconds(item.get("stored_at")),
                }
            )
        result.sort(key=lambda item: item.get("stored_at") or "", reverse=True)
        return result

    @staticmethod
    def _age_seconds(value: Any) -> int:
        try:
            parsed = datetime.fromisoformat(str(value))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(0, int(_now() - parsed.timestamp()))
        except (TypeError, ValueError):
            return 0

    def _find_pending(self, pending_id: str) -> tuple[str, dict[str, Any]] | None:
        if not pending_id:
            return None
        for key, item in self.plugin.storage.data.get("pending", {}).items():
            if not isinstance(item, dict):
                continue
            candidate = self._pending_id(item)
            if hmac.compare_digest(candidate, pending_id):
                return str(key), item
        return None

    # ------------------------------------------------------------------
    # 进群验证
    # ------------------------------------------------------------------
    def _verification_items(self) -> list[dict[str, Any]]:
        storage = self.plugin.storage
        try:
            records = storage.verifications()
        except Exception:
            records = []
        now = _now()
        result: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            token = str(record.get("token") or "")
            platform_id = str(record.get("platform_id") or "")
            group_openid = str(record.get("group_openid") or "")
            member_openid = str(record.get("member_openid") or "")
            if not token or not platform_id or not group_openid or not member_openid:
                continue
            umo = self._group_umo(platform_id, group_openid)
            status = str(record.get("status") or "pending")
            deadline = float(record.get("deadline") or 0)
            try:
                max_failures = int(
                    self.plugin._group_setting(umo, "verify_max_failures", 3)
                )
            except Exception:
                max_failures = 3
            platform = self._platform(platform_id)
            result.append(
                {
                    "id": token,
                    "group_umo": umo,
                    "group_label": f"{self._platform_name(platform_id)} · "
                    f"{_short(group_openid, 8, 4)}",
                    "platform_id": platform_id,
                    "platform_name": self._platform_name(platform_id),
                    "member_openid": member_openid,
                    "member_short": _short(member_openid, 6, 4),
                    "mode": str(record.get("mode") or "arithmetic"),
                    "mode_label": "自定义问题"
                    if record.get("mode") == "custom"
                    else "算术题",
                    "question": str(record.get("question") or "")[:1000],
                    "status": status,
                    "status_label": STATUS_LABELS.get(status, status),
                    "failures": int(record.get("failures") or 0),
                    "max_failures": max(1, max_failures),
                    "delivered": bool(record.get("delivered")),
                    "deadline": deadline,
                    "remaining_seconds": max(0, int(deadline - now)) if deadline else 0,
                    "timeout_handled": bool(record.get("timeout_handled")),
                    "joined_at": float(record.get("joined_at") or 0),
                    "last_remind_at": float(record.get("last_remind_at") or 0),
                    "expired": status == "pending"
                    and bool(deadline)
                    and now >= deadline,
                    "can_act": platform is not None
                    and getattr(platform, "client", None) is not None,
                }
            )
        result.sort(
            key=lambda item: (
                0 if item["status"] == "failed" else 1,
                -item["joined_at"],
            )
        )
        return result

    def _find_verification(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        try:
            record = self.plugin.storage.find_verification_by_token(token)
        except Exception:
            return None
        return record if isinstance(record, dict) else None

    async def _acquire_verification_lock(self, key: tuple[str, str, str]):
        lock = self.plugin.verifier._lock(key)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=6)
        except asyncio.TimeoutError as exc:
            raise DashboardError(
                "该成员正在作答或处理中，请稍后刷新重试", status_code=409
            ) from exc
        return lock

    async def _unmute_if_failed(
        self, platform: Any, record: dict[str, Any]
    ) -> str:
        if record.get("status") != "failed":
            return ""
        try:
            await asyncio.wait_for(
                self.plugin._mute_on_platform(
                    platform,
                    str(record["group_openid"]),
                    str(record["member_openid"]),
                    0,
                ),
                10,
            )
            return ""
        except Exception as exc:
            logger.exception("[%s] WebUI 放行后解除禁言失败", PLUGIN_NAME)
            return f"解除禁言失败：{type(exc).__name__}"

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    @staticmethod
    def _field_from_schema(key: str, meta: dict[str, Any]) -> dict[str, Any]:
        kind = str(meta.get("type") or "string")
        field: dict[str, Any] = {
            "key": key,
            "kind": kind,
            "label": str(meta.get("description") or key),
            "hint": str(meta.get("hint") or ""),
            "default": _json_safe(meta.get("default")),
            "condition": meta.get("condition")
            if isinstance(meta.get("condition"), dict)
            else None,
        }
        if kind == "int":
            low, high = INT_RANGES.get(key, (0, 2_147_483_647))
            field.update({"min": low, "max": high, "step": 1})
            if key in INT_UNITS:
                field["unit"] = INT_UNITS[key]
        elif kind == "string":
            options = meta.get("options")
            if isinstance(options, list) and options:
                field["options"] = [str(option) for option in options]
            if key in DURATION_KEYS:
                field["unit"] = "时长"
                field["placeholder"] = "例如 10分、2小时、1天2小时"
        elif kind == "text":
            field["rows"] = 6 if key == "verify_prompt" else 4
        elif kind == "list":
            choices = LIST_CHOICES.get(key)
            if choices:
                field["choices"] = choices
            if key == "custom_questions":
                field["rows"] = 5
                field["placeholder"] = "每行一条：问题 => 正则，例如 本群主题？ => ^(天文|astronomy)$"
            elif key == "enabled_group_umos":
                field["placeholder"] = "平台ID:GroupMessage:群ID"
            else:
                field["placeholder"] = "输入后按回车添加"
        return field

    @classmethod
    def _sections(cls, scope: str) -> list[dict[str, Any]]:
        sections: list[dict[str, Any]] = []
        for section in SECTION_ORDER:
            if scope == "group" and section == "scope_settings":
                continue
            meta = SCHEMA.get(section) or {}
            fields: list[dict[str, Any]] = []
            for key, item_meta in (meta.get("items") or {}).items():
                if scope == "group" and key == "pending_retention_days":
                    continue
                if not isinstance(item_meta, dict):
                    continue
                field = cls._field_from_schema(key, item_meta)
                field["section"] = section
                fields.append(field)
            if not fields:
                continue
            sections.append(
                {
                    "key": section,
                    "title": str(meta.get("description") or section),
                    "hint": str(meta.get("hint") or ""),
                    "icon": SECTION_ICONS.get(section, "settings"),
                    "fields": fields,
                }
            )
        return sections

    def _config_values(self, scope: str, umo: str = "") -> dict[str, Any]:
        values: dict[str, Any] = {}
        for section in self._sections(scope):
            for field in section["fields"]:
                key = field["key"]
                default = field.get("default")
                if scope == "group":
                    value = self._group_value(key, umo, default)
                else:
                    value = self._global_value(key, default)
                if field["kind"] == "list":
                    value = _as_list(value)
                values[key] = _json_safe(value)
        return values

    def _config_response(self, umo: str = "") -> dict[str, Any]:
        scope = "group" if umo else "global"
        if umo and not valid_group_umo(umo):
            raise DashboardError("群 UMO 必须使用 平台ID:GroupMessage:群ID 格式")
        profile = self._profile_state(umo) if umo else {"exists": False}
        per_group = bool(self._global_value("enable_per_group_feature_settings", False))
        warnings: list[str] = []
        if umo:
            if profile.get("duplicate"):
                warnings.append("检测到多个相同 UMO 的群配置，请先在插件配置面板合并。")
            if profile.get("note"):
                warnings.append(str(profile["note"]))
            if not profile["exists"]:
                warnings.append("该群还没有分群配置，当前显示并继承全局配置。")
            if not per_group:
                warnings.append("分群功能管理当前已关闭，分群配置不会生效。")
        return {
            "scope": scope,
            "umo": umo,
            "per_group": per_group,
            "profile": profile,
            "sections": self._sections(scope),
            "values": self._config_values(scope, umo),
            "warnings": warnings,
            "plugin": {
                "name": PLUGIN_NAME,
                "display_name": PLUGIN_DISPLAY_NAME,
                "version": PLUGIN_VERSION,
            },
        }

    def _normalize_value(
        self,
        key: str,
        value: Any,
        field: dict[str, Any],
        scope: str,
        umo: str,
        updates: dict[str, Any],
    ) -> Any:
        kind = field["kind"]
        if kind == "bool":
            if not isinstance(value, bool):
                raise DashboardError(f"“{field['label']}”需要布尔值")
            return value
        if kind == "int":
            if isinstance(value, bool):
                raise DashboardError(f"“{field['label']}”需要整数")
            if isinstance(value, float) and not value.is_integer():
                raise DashboardError(f"“{field['label']}”需要整数")
            try:
                number = int(value)
            except (TypeError, ValueError) as exc:
                raise DashboardError(f"“{field['label']}”需要整数") from exc
            low, high = field.get("min", 0), field.get("max", 2_147_483_647)
            if number < low or number > high:
                raise DashboardError(
                    f"“{field['label']}”应在 {low} 到 {high} 之间"
                )
            return number
        if kind in {"string", "text"}:
            if not isinstance(value, str):
                raise DashboardError(f"“{field['label']}”需要文本")
            text = value.strip()
            limit = 8192 if kind == "text" else 512
            if len(text) > limit:
                raise DashboardError(f"“{field['label']}”不能超过 {limit} 个字符")
            options = field.get("options")
            if isinstance(options, list) and options and text not in options:
                raise DashboardError(
                    f"“{field['label']}”只能选择：{'、'.join(options)}"
                )
            return text
        if kind == "list":
            items = _as_list(value)
            limit = 500 if key != "enabled_group_umos" else 200
            if len(items) > limit:
                raise DashboardError(f"“{field['label']}”最多 {limit} 条")
            for item in items:
                if len(item) > 1000:
                    raise DashboardError(f"“{field['label']}”中的单条内容过长")
            choices = field.get("choices")
            if choices and any(item not in choices for item in items):
                raise DashboardError(
                    f"“{field['label']}”只能填写：{'、'.join(choices)}"
                )
            if key == "enabled_group_umos":
                invalid = [item for item in items if not valid_group_umo(item)]
                if invalid:
                    raise DashboardError(
                        "以下 UMO 格式不正确："
                        + "、".join(invalid[:3])
                        + ("…" if len(invalid) > 3 else "")
                    )
            if key == "custom_questions":
                _, invalid = parse_custom_questions(items)
                if invalid:
                    raise DashboardError(
                        "以下自定义问题格式或正则无效："
                        + "；".join(invalid[:3])
                        + ("…" if len(invalid) > 3 else "")
                    )
            if key in REGEX_LIST_KEYS:
                mode = updates.get(
                    "join_keyword_match_mode",
                    self._group_value("join_keyword_match_mode", umo, "包含匹配")
                    if scope == "group"
                    else self._global_value("join_keyword_match_mode", "包含匹配"),
                )
                if mode == "正则匹配":
                    for pattern in items:
                        try:
                            compile_join_pattern(pattern)
                        except ValueError as exc:
                            raise DashboardError(
                                f"正则无效：{pattern}（{exc}）"
                            ) from exc
            return items
        return value

    def _prepare_updates(self, scope: str, umo: str, raw: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise DashboardError("请求体格式不正确")
        if not raw:
            raise DashboardError("没有需要保存的配置项")
        if len(raw) > 80:
            raise DashboardError("一次保存的配置项过多")
        allowed = {
            field["key"]: field
            for section in self._sections(scope)
            for field in section["fields"]
        }
        updates: dict[str, Any] = {}
        for key, value in raw.items():
            field = allowed.get(str(key))
            if field is None:
                raise DashboardError(f"不支持的配置项：{key}")
            updates[str(key)] = self._normalize_value(
                str(key), value, field, scope, umo, raw
            )
        for key, value in updates.items():
            if key not in DURATION_KEYS:
                continue
            try:
                seconds = parse_duration(str(value))
            except ValueError as exc:
                raise DashboardError(f"“{allowed[key]['label']}”时长格式错误") from exc
            if seconds <= 0:
                raise DashboardError(f"“{allowed[key]['label']}”必须大于 0")
            maximum = int(
                updates.get(
                    "max_mute_seconds",
                    self._group_value("max_mute_seconds", umo, 2592000)
                    if scope == "group"
                    else self._global_value("max_mute_seconds", 2592000),
                )
            )
            if seconds > maximum:
                raise DashboardError(
                    f"“{allowed[key]['label']}”不能超过单次禁言上限 {maximum} 秒"
                )
        return updates

    def _apply_global_updates(self, updates: dict[str, Any]) -> None:
        layout = int(self.plugin.config.get("config_layout_version", 0) or 0)
        if layout < 2:
            raise DashboardError(
                "插件配置尚未迁移到新版布局，请先重载插件后再保存", status_code=409
            )
        management = self.plugin.config.setdefault("group_management", {})
        global_settings = management.setdefault("global_settings", {})
        for key, value in updates.items():
            if key == "enable_per_group_feature_settings":
                management["enabled"] = value
            elif key in {"enabled_group_umos"}:
                self.plugin.config.setdefault("scope_settings", {})[key] = value
            else:
                section_name = SECTION_FOR_KEY.get(key)
                if section_name is None:
                    raise DashboardError(f"不支持的配置项：{key}")
                global_settings.setdefault(section_name, {})[key] = value

    def _apply_group_updates(self, umo: str, updates: dict[str, Any]) -> None:
        layout = int(self.plugin.config.get("config_layout_version", 0) or 0)
        if layout < 2:
            raise DashboardError(
                "插件配置尚未迁移到新版布局，请先重载插件后再保存", status_code=409
            )
        group_config = GroupConfig(self.plugin.config)
        data = group_config.data
        matches = [
            item
            for item in data.get("groups", [])
            if isinstance(item, dict) and item.get("umo") == umo
        ]
        if len(matches) > 1:
            raise DashboardError(
                "检测到多个相同 UMO 的群配置，请先在插件配置面板合并后再编辑",
                status_code=409,
            )
        profile = matches[0] if matches else None
        if profile is None:
            profile = group_config.snapshot(umo)
            data.setdefault("groups", []).append(profile)
        elif not profile.get("confirmed", True):
            # 旧迁移标记不再在界面上展示；编辑当前群时直接视为确认。
            profile["confirmed"] = True
        for key, value in updates.items():
            section_name = SECTION_FOR_KEY.get(key)
            if section_name is None or section_name == "scope_settings":
                raise DashboardError(f"不支持的配置项：{key}")
            profile.setdefault(section_name, {})[key] = value

    @staticmethod
    def _save_config(plugin: Any) -> None:
        save = getattr(plugin.config, "save_config", None)
        if callable(save):
            save()
        else:
            GroupConfig(plugin.config).save()

    # ------------------------------------------------------------------
    # Handler: 总览
    # ------------------------------------------------------------------
    async def get_overview(self) -> Any:
        try:
            pending = self._pending_items()
            verifications = self._verification_items()
            groups = self._group_summaries()
            platforms = self._platforms()
            admin_count = sum(item["admin_count"] for item in groups)
            per_group = bool(
                self._global_value("enable_per_group_feature_settings", False)
            )
            layout = int(self.plugin.config.get("config_layout_version", 0) or 0)
            enabled_verify_groups = sum(
                1
                for item in groups
                if bool(self._group_value("enable_join_verify", item["umo"], False))
            )
            storage_path = getattr(self.plugin.storage, "path", None)
            storage_ok = bool(storage_path and storage_path.parent.exists())
            duplicate_profiles = self._duplicate_profile_count()
            health = [
                {
                    "key": "platform",
                    "label": "QQ 官方平台",
                    "status": "ok" if any(p["online"] for p in platforms) else "warn",
                    "detail": (
                        f"{sum(1 for p in platforms if p['online'])} 个在线"
                        if platforms
                        else "未检测到 qq_official / qq_official_webhook 平台"
                    ),
                },
                {
                    "key": "storage",
                    "label": "运行数据",
                    "status": "ok" if storage_ok else "warn",
                    "detail": "数据目录可写" if storage_ok else "数据目录尚未创建",
                },
                {
                    "key": "config",
                    "label": "配置布局",
                    "status": "ok" if layout >= 2 else "warn",
                    "detail": "新版分群布局" if layout >= 2 else "等待迁移（重载插件）",
                },
                {
                    "key": "profile",
                    "label": "分群配置",
                    "status": "ok" if duplicate_profiles == 0 else "warn",
                    "detail": "无重复 UMO"
                    if duplicate_profiles == 0
                    else f"{duplicate_profiles} 个重复 UMO",
                },
                {
                    "key": "verify",
                    "label": "进群验证",
                    "status": "info",
                    "detail": f"{enabled_verify_groups} 个群已开启",
                },
            ]
            return json_response(
                {
                    "plugin": {
                        "name": PLUGIN_NAME,
                        "display_name": PLUGIN_DISPLAY_NAME,
                        "version": PLUGIN_VERSION,
                        "view": VIEW_NAME,
                        "repo": "https://github.com/1023286457/astrbot_plugin_qq_group_manage",
                    },
                    "runtime": {
                        "per_group": per_group,
                        "group_count": len(groups),
                        "pending_count": len(pending),
                        "verification_count": len(verifications),
                        "admin_count": admin_count,
                        "platforms": platforms,
                        "online_platform_count": sum(
                            1 for p in platforms if p["online"]
                        ),
                        "retention_days": int(
                            getattr(self.plugin.storage, "retention_days", 30)
                        ),
                        "config_layout_version": layout,
                        "enabled_verify_groups": enabled_verify_groups,
                        "storage_available": storage_ok,
                        "duplicate_profiles": duplicate_profiles,
                    },
                    "features": self._features(),
                    "groups": groups[:8],
                    "pending": pending[:5],
                    "verifications": verifications[:5],
                    "health": health,
                }
            )
        except Exception as exc:
            return self._error(exc, "读取总览失败")

    def _duplicate_profile_count(self) -> int:
        try:
            profiles = GroupConfig(self.plugin.config).data.get("groups", [])
        except Exception:
            return 0
        seen: set[str] = set()
        duplicates: set[str] = set()
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            umo = str(profile.get("umo") or "")
            if not umo:
                continue
            if umo in seen:
                duplicates.add(umo)
            seen.add(umo)
        return len(duplicates)

    # ------------------------------------------------------------------
    # Handler: 刷屏监控
    # ------------------------------------------------------------------
    async def get_spam(self) -> Any:
        try:
            per_group = bool(
                self._global_value("enable_per_group_feature_settings", False)
            )
            enabled = bool(self._global_value("enable_anti_spam", False))
            enabled_groups = 0
            if per_group:
                try:
                    profiles = GroupConfig(self.plugin.config).data.get("groups", [])
                except Exception:
                    profiles = []
                for profile in profiles:
                    if not isinstance(profile, dict) or not profile.get(
                        "confirmed", True
                    ):
                        continue
                    section = profile.get("spam_settings")
                    value = None
                    if isinstance(section, dict):
                        value = section.get("enable_anti_spam")
                    if value is None:
                        value = enabled
                    if bool(value):
                        enabled_groups += 1
            monitor = getattr(self.plugin, "spam_monitor", None)
            if monitor is not None:
                snapshot = monitor.snapshot(time.monotonic())
            else:
                snapshot = {
                    "tracked_groups": 0,
                    "tracked_users": 0,
                    "active_users": 0,
                    "rows": [],
                }
            limits = {
                key: _json_safe(self._global_value(key)) for key in SPAM_KEYS
            }
            return json_response(
                {
                    "enabled": enabled or enabled_groups > 0,
                    "per_group": per_group,
                    "enabled_groups": enabled_groups,
                    "limits": limits,
                    "stats": {
                        "enabled": enabled or enabled_groups > 0,
                        "tracked_groups": snapshot["tracked_groups"],
                        "tracked_users": snapshot["tracked_users"],
                        "active_users": snapshot["active_users"],
                    },
                    "rows": snapshot["rows"],
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception as exc:
            return self._error(exc, "读取刷屏监控失败")

    # ------------------------------------------------------------------
    # Handler: 风险消息撤回
    # ------------------------------------------------------------------
    async def get_recall(self) -> Any:
        try:
            per_group = bool(
                self._global_value("enable_per_group_feature_settings", False)
            )
            umo = str(request.query.get("umo") or "").strip()
            if umo and not valid_group_umo(umo):
                raise DashboardError("群 UMO 格式不正确")
            scope = "group" if per_group and umo else "global"
            if scope == "group":
                config = {
                    key: _json_safe(self._group_value(key, umo, self._global_value(key)))
                    for key in RECALL_KEYS
                }
            else:
                config = {
                    key: _json_safe(self._global_value(key)) for key in RECALL_KEYS
                }
            monitor = getattr(self.plugin, "recall_monitor", None)
            if monitor is not None:
                snapshot = monitor.snapshot(time.monotonic())
            else:
                snapshot = {
                    "tracked_groups": 0,
                    "total": 0,
                    "link_count": 0,
                    "qr_count": 0,
                    "rows": [],
                }
            groups: list[dict[str, str]] = []
            if per_group:
                try:
                    for item in self._known_groups().values():
                        summary = self._group_summary(item)
                        label = summary["label"]
                        note = summary.get("note") or ""
                        groups.append(
                            {
                                "umo": summary["umo"],
                                "label": f"{note} · {label}" if note else label,
                            }
                        )
                except Exception:
                    groups = []
            return json_response(
                {
                    "enabled": bool(config.get("enable_link_recall"))
                    or bool(config.get("enable_qr_recall")),
                    "per_group": per_group,
                    "scope": scope,
                    "umo": umo if scope == "group" else "",
                    "config": config,
                    "stats": {
                        "total": snapshot["total"],
                        "link_count": snapshot["link_count"],
                        "qr_count": snapshot["qr_count"],
                        "tracked_groups": snapshot["tracked_groups"],
                    },
                    "rows": snapshot["rows"],
                    "groups": groups,
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception as exc:
            return self._error(exc, "读取风险消息撤回失败")

    # ------------------------------------------------------------------
    # Handler: 入群申请
    # ------------------------------------------------------------------
    async def get_pending(self) -> Any:
        try:
            items = self._pending_items()
            return json_response({"items": items, "total": len(items)})
        except Exception as exc:
            return self._error(exc, "读取入群申请失败")

    async def review_pending(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            pending_id = str(payload.get("id") or "").strip()
            action = str(payload.get("action") or "").strip().lower()
            reason = str(payload.get("reason") or "").strip()[:200]
            if action not in {"approve", "decline"}:
                raise DashboardError("审批动作只能是 approve 或 decline")
            matched = self._find_pending(pending_id)
            if matched is None:
                raise DashboardError("该申请不存在或已被处理", status_code=404)
            _, item = matched
            platform_id = str(item.get("platform_id") or "")
            group_openid = str(item.get("group_openid") or "")
            member_openid = str(item.get("member_openid") or "")
            join_request_id = str(item.get("join_request_id") or "")
            if not all((platform_id, group_openid, member_openid, join_request_id)):
                raise DashboardError("申请数据不完整，无法审批")
            if self.plugin.storage.is_reviewed(
                platform_id, group_openid, join_request_id
            ):
                raise DashboardError("该申请已处理，请勿重复审批", status_code=409)
            platform = self._platform(platform_id)
            if platform is None or getattr(platform, "client", None) is None:
                raise DashboardError("对应的 QQ 平台当前不在线", status_code=503)
            request_key = (platform_id, group_openid, join_request_id)
            if request_key in self.plugin._reviews_inflight:
                raise DashboardError("该申请正在处理中，请勿重复提交", status_code=409)
            self.plugin._reviews_inflight.add(request_key)
            try:
                await asyncio.wait_for(
                    QQGroupManageAPI(platform.client).review_join_request(
                        group_openid,
                        member_openid,
                        join_request_id,
                        approve=action == "approve",
                        reject_reason=reason if action == "decline" else "",
                    ),
                    timeout=20,
                )
            except asyncio.TimeoutError as exc:
                raise DashboardError("QQ 接口响应超时，请稍后刷新确认", 504) from exc
            except Exception as exc:
                logger.exception("[%s] WebUI 审批入群申请失败", PLUGIN_NAME)
                raise DashboardError(
                    "QQ 接口调用失败，请查看 AstrBot 日志确认申请状态",
                    status_code=502,
                ) from exc
            finally:
                self.plugin._reviews_inflight.discard(request_key)
            self.plugin._record_reviewed_request(
                platform_id, group_openid, join_request_id
            )
            return json_response(
                {
                    "ok": True,
                    "action": action,
                    "message": "已同意入群申请" if action == "approve" else "已拒绝入群申请",
                }
            )
        except Exception as exc:
            return self._error(exc, "审批入群申请失败")

    # ------------------------------------------------------------------
    # Handler: 进群验证
    # ------------------------------------------------------------------
    async def get_verifications(self) -> Any:
        try:
            items = self._verification_items()
            return json_response({"items": items, "total": len(items)})
        except Exception as exc:
            return self._error(exc, "读取进群验证失败")

    async def release_verification(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            token = str(payload.get("id") or "").strip()
            record = self._find_verification(token)
            if record is None:
                raise DashboardError("该验证记录不存在或已被处理", status_code=404)
            platform_id = str(record.get("platform_id") or "")
            group_openid = str(record.get("group_openid") or "")
            member_openid = str(record.get("member_openid") or "")
            platform = self._platform(platform_id)
            if platform is None or getattr(platform, "client", None) is None:
                raise DashboardError("对应的 QQ 平台当前不在线", status_code=503)
            key = (platform_id, group_openid, member_openid)
            lock = await self._acquire_verification_lock(key)
            try:
                current = self._find_verification(token)
                if current is None:
                    raise DashboardError("该验证记录已被处理", status_code=409)
                warning = await self._unmute_if_failed(platform, current)
                self.plugin.storage.remove_verification(*key)
            finally:
                lock.release()
            message = "已放行该成员"
            if warning:
                message += f"；{warning}"
            return json_response({"ok": True, "warning": warning, "message": message})
        except Exception as exc:
            return self._error(exc, "放行进群验证失败")

    async def release_all_verifications(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            raw_ids = payload.get("ids")
            if not isinstance(raw_ids, list):
                raise DashboardError("ids 必须是验证记录列表")
            ids = list(dict.fromkeys(str(item).strip() for item in raw_ids if str(item).strip()))
            if not ids:
                raise DashboardError("没有可放行的验证记录")
            if len(ids) > 200:
                raise DashboardError("一次最多放行 200 条验证记录，请先按群筛选")
            released = 0
            failed = 0
            warnings: list[str] = []
            for token in ids:
                try:
                    record = self._find_verification(token)
                    if record is None:
                        failed += 1
                        continue
                    platform_id = str(record.get("platform_id") or "")
                    group_openid = str(record.get("group_openid") or "")
                    member_openid = str(record.get("member_openid") or "")
                    platform = self._platform(platform_id)
                    if platform is None or getattr(platform, "client", None) is None:
                        failed += 1
                        warnings.append(f"{member_openid or token}：对应平台离线")
                        continue
                    key = (platform_id, group_openid, member_openid)
                    lock = await self._acquire_verification_lock(key)
                    try:
                        current = self._find_verification(token)
                        if current is None:
                            failed += 1
                            continue
                        warning = await self._unmute_if_failed(platform, current)
                        self.plugin.storage.remove_verification(*key)
                        released += 1
                        if warning:
                            warnings.append(f"{member_openid or token}：{warning}")
                    finally:
                        lock.release()
                except Exception:
                    failed += 1
                    logger.exception("[%s] 一键放行单条验证失败", PLUGIN_NAME)
            message = f"已放行 {released} 人"
            if failed:
                message += f"，{failed} 条未处理"
            if warnings:
                message += f"；{warnings[0]}"
                if len(warnings) > 1:
                    message += f" 等 {len(warnings)} 条提示"
            return json_response(
                {
                    "ok": True,
                    "released": released,
                    "failed": failed,
                    "warnings": warnings[:50],
                    "message": message,
                }
            )
        except Exception as exc:
            return self._error(exc, "一键放行进群验证失败")

    async def retry_verification(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            token = str(payload.get("id") or "").strip()
            record = self._find_verification(token)
            if record is None:
                raise DashboardError("该验证记录不存在或已被处理", status_code=404)
            platform_id = str(record.get("platform_id") or "")
            group_openid = str(record.get("group_openid") or "")
            member_openid = str(record.get("member_openid") or "")
            umo = self._group_umo(platform_id, group_openid)
            if not bool(self._group_value("enable_join_verify", umo, False)):
                raise DashboardError("该群未开启进群验证", status_code=409)
            platform = self._platform(platform_id)
            if platform is None or getattr(platform, "client", None) is None:
                raise DashboardError("对应的 QQ 平台当前不在线", status_code=503)
            key = (platform_id, group_openid, member_openid)
            lock = await self._acquire_verification_lock(key)
            try:
                current = self._find_verification(token)
                if current is None:
                    raise DashboardError("该验证记录已被处理", status_code=409)
                warning = await self._unmute_if_failed(platform, current)
                self.plugin.storage.remove_verification(*key)
                new_record = self.plugin.verifier._new_record(
                    platform_id, group_openid, member_openid
                )
                self.plugin.storage.put_verification(new_record)
                await self.plugin.verifier._send_first(platform, new_record)
            finally:
                lock.release()
            message = "已重新出题" if new_record.get("delivered") else "已重新出题，但题目发送失败"
            if warning:
                message += f"；{warning}"
            return json_response(
                {
                    "ok": True,
                    "delivered": bool(new_record.get("delivered")),
                    "warning": warning,
                    "message": message,
                    "id": str(new_record.get("token") or ""),
                }
            )
        except Exception as exc:
            return self._error(exc, "重新发起进群验证失败")

    # ------------------------------------------------------------------
    # Handler: 群组
    # ------------------------------------------------------------------
    async def get_groups(self) -> Any:
        try:
            items = self._group_summaries()
            return json_response({"items": items, "total": len(items)})
        except Exception as exc:
            return self._error(exc, "读取群组列表失败")

    async def get_group_detail(self) -> Any:
        try:
            umo = str(request.query.get("umo") or "").strip()
            if not valid_group_umo(umo):
                raise DashboardError("群 UMO 格式不正确")
            item = self._known_groups().get(umo)
            if item is None:
                raise DashboardError("该群不在已知列表中", status_code=404)
            summary = self._group_summary(item)
            return json_response(
                {
                    "group": summary,
                    "features": self._features(umo),
                }
            )
        except Exception as exc:
            return self._error(exc, "读取群组详情失败")

    async def update_group_admins(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            umo = str(payload.get("umo") or "").strip()
            member = str(payload.get("member_openid") or "").strip()
            action = str(payload.get("action") or "add").strip().lower()
            if not valid_group_umo(umo):
                raise DashboardError("群 UMO 格式不正确")
            if not member or len(member) > 128 or any(char.isspace() for char in member):
                raise DashboardError("成员 OpenID 格式不正确")
            if action not in {"add", "remove"}:
                raise DashboardError("动作只能是 add 或 remove")
            group_openid = umo.rsplit(":", 1)[-1]
            if action == "add" and len(self.plugin.storage.group_admins(group_openid)) >= 50:
                raise DashboardError("单个群的插件群管最多 50 名")
            changed = self.plugin.storage.update_group_admins(
                group_openid, [member], add=action == "add"
            )
            return json_response(
                {
                    "ok": True,
                    "changed": changed,
                    "action": action,
                    "admins": self.plugin.storage.group_admins(group_openid),
                }
            )
        except Exception as exc:
            return self._error(exc, "更新群管名单失败")

    async def update_group_note(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            umo = str(payload.get("umo") or "").strip()
            note = str(payload.get("note") or "").strip()
            if not valid_group_umo(umo):
                raise DashboardError("群 UMO 格式不正确")
            if len(note) > 120:
                raise DashboardError("群备注不能超过 120 个字符")
            saved = self.plugin.storage.set_group_note(umo, note)
            return json_response(
                {
                    "ok": True,
                    "note": saved,
                    "message": "群备注已保存" if saved else "群备注已清除",
                }
            )
        except Exception as exc:
            return self._error(exc, "保存群备注失败")

    async def send_broadcast(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            text = str(payload.get("text") or "").strip()
            image = payload.get("image")
            if not text and not image:
                raise DashboardError("广播内容不能为空")
            if len(text) > 2000:
                raise DashboardError("广播文字不能超过 2000 个字符")
            image_data = ""
            image_name = "broadcast.png"
            image_mime = ""
            if image is not None:
                if not isinstance(image, dict):
                    raise DashboardError("图片格式不正确")
                image_data = str(image.get("data") or "").strip()
                image_name = str(image.get("name") or "broadcast.png").strip()
                image_mime = str(image.get("mime") or "").strip().lower()
                if image_mime not in {"image/png", "image/jpeg", "image/jpg"}:
                    raise DashboardError("只支持 PNG 或 JPG 图片")
                try:
                    raw_image = base64.b64decode(image_data, validate=True)
                except Exception as exc:
                    raise DashboardError("图片数据不是有效的 Base64") from exc
                if not raw_image:
                    raise DashboardError("图片内容为空")
                if len(raw_image) > 5 * 1024 * 1024:
                    raise DashboardError("图片不能超过 5MB")
                if image_mime == "image/jpg":
                    image_mime = "image/jpeg"
                if not image_name.lower().endswith((".png", ".jpg", ".jpeg")):
                    image_name = "broadcast.png" if image_mime == "image/png" else "broadcast.jpg"

            if self._broadcast_lock.locked():
                raise DashboardError("已有群广播正在进行，请稍后再试", status_code=409)
            async with self._broadcast_lock:
                known = self._known_groups()
                targets = []
                for umo, item in known.items():
                    platform_id = str(item.get("platform_id") or "")
                    group_openid = str(item.get("group_openid") or "")
                    if not platform_id or not group_openid:
                        continue
                    targets.append((umo, platform_id, group_openid))
                if not targets:
                    raise DashboardError("当前没有已知群组，无法广播")
                if len(targets) > 200:
                    raise DashboardError("一次最多广播 200 个群，请先清理群组记录")
                sent = 0
                failed = 0
                image_failed = 0
                errors: list[str] = []
                for index, (umo, platform_id, group_openid) in enumerate(targets):
                    platform = self._platform(platform_id)
                    if platform is None or getattr(platform, "client", None) is None:
                        failed += 1
                        if len(errors) < 20:
                            errors.append(f"{umo}：平台离线")
                        continue
                    api = QQGroupManageAPI(platform.client)
                    delivered = False
                    if text:
                        try:
                            await asyncio.wait_for(
                                api.send_group_text(group_openid, text), 15
                            )
                            delivered = True
                        except Exception as exc:
                            if len(errors) < 20:
                                errors.append(f"{umo}：文字发送失败 {exc}")
                    if image_data:
                        try:
                            uploaded = await asyncio.wait_for(
                                api.upload_group_image(
                                    group_openid, image_name, image_data
                                ),
                                20,
                            )
                            file_info = (
                                str(uploaded.get("file_info") or "")
                                if isinstance(uploaded, dict)
                                else ""
                            )
                            if not file_info:
                                raise RuntimeError("图片上传未返回 file_info")
                            await asyncio.wait_for(
                                api.send_group_media(group_openid, file_info), 15
                            )
                            delivered = True
                        except Exception as exc:
                            image_failed += 1
                            if len(errors) < 20:
                                errors.append(f"{umo}：图片发送失败 {exc}")
                    if delivered:
                        sent += 1
                    else:
                        failed += 1
                    if index + 1 < len(targets):
                        await asyncio.sleep(0.25)
                message = f"广播完成：成功 {sent} 个群"
                if failed:
                    message += f"，失败 {failed} 个"
                if image_failed:
                    message += f"，图片失败 {image_failed} 个"
                return json_response(
                    {
                        "ok": True,
                        "total": len(targets),
                        "sent": sent,
                        "failed": failed,
                        "image_failed": image_failed,
                        "errors": errors,
                        "message": message,
                    }
                )
        except Exception as exc:
            return self._error(exc, "群广播失败")

    async def get_panel_images(self) -> Any:
        try:
            meta = image_meta(self.plugin.storage)
            items = {}
            for key, label in PANEL_IMAGE_KEYS.items():
                item = meta.get(key)
                items[key] = {
                    "key": key,
                    "label": label,
                    "exists": isinstance(item, dict),
                    "name": str(item.get("name") or "") if isinstance(item, dict) else "",
                    "mime": str(item.get("mime") or "") if isinstance(item, dict) else "",
                    "size": int(item.get("size") or 0) if isinstance(item, dict) else 0,
                    "preview": image_data_url(self.plugin.storage, key),
                }
            return json_response({"items": items})
        except Exception as exc:
            return self._error(exc, "读取群管面板图片失败")

    async def save_panel_image(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            key = str(payload.get("key") or "").strip()
            if key not in PANEL_IMAGE_KEYS:
                raise DashboardError("不支持的图片类型")
            mime = str(payload.get("mime") or "").strip().lower()
            if mime not in {"image/png", "image/jpeg", "image/jpg"}:
                raise DashboardError("只支持 PNG 或 JPG 图片")
            try:
                raw = base64.b64decode(str(payload.get("data") or ""), validate=True)
            except Exception as exc:
                raise DashboardError("图片数据不是有效的 Base64") from exc
            item = save_image(
                self.plugin.storage,
                key,
                raw,
                mime,
                str(payload.get("name") or f"{key}.png"),
            )
            return json_response(
                {
                    "ok": True,
                    "key": key,
                    "item": item,
                    "message": f"{PANEL_IMAGE_KEYS[key]}图片已保存",
                }
            )
        except Exception as exc:
            return self._error(exc, "保存群管面板图片失败")

    async def delete_panel_image(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            key = str(payload.get("key") or "").strip()
            if key not in PANEL_IMAGE_KEYS:
                raise DashboardError("不支持的图片类型")
            changed = delete_image(self.plugin.storage, key)
            return json_response(
                {
                    "ok": True,
                    "changed": changed,
                    "message": "图片已删除" if changed else "图片本来就不存在",
                }
            )
        except Exception as exc:
            return self._error(exc, "删除群管面板图片失败")

    # ------------------------------------------------------------------
    # Handler: 配置
    # ------------------------------------------------------------------
    async def get_config(self) -> Any:
        try:
            umo = str(request.query.get("umo") or "").strip()
            return json_response(self._config_response(umo))
        except Exception as exc:
            return self._error(exc, "读取插件配置失败")

    async def save_config(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            scope = str(payload.get("scope") or "global").strip().lower()
            umo = str(payload.get("umo") or "").strip()
            updates = payload.get("values")
            if scope not in {"global", "group"}:
                raise DashboardError("scope 只能是 global 或 group")
            if scope == "group":
                if not valid_group_umo(umo):
                    raise DashboardError("群 UMO 格式不正确")
            else:
                umo = ""
            normalized = self._prepare_updates(scope, umo, updates)
            before = deepcopy(dict(self.plugin.config))
            try:
                if scope == "group":
                    self._apply_group_updates(umo, normalized)
                else:
                    self._apply_global_updates(normalized)
                self._save_config(self.plugin)
            except Exception:
                self.plugin.config.clear()
                self.plugin.config.update(before)
                raise
            if "pending_retention_days" in normalized:
                self.plugin.storage.retention_days = max(
                    1, int(self.plugin._config("pending_retention_days", 30))
                )
                self.plugin.storage.prune()
            return json_response(
                {
                    "ok": True,
                    "saved": len(normalized),
                    "message": f"已保存 {len(normalized)} 项配置",
                    "config": self._config_response(umo),
                }
            )
        except Exception as exc:
            return self._error(exc, "保存插件配置失败")

    async def create_group_profile(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            umo = str(payload.get("umo") or "").strip()
            if not valid_group_umo(umo):
                raise DashboardError("群 UMO 格式不正确")
            group_config = GroupConfig(self.plugin.config)
            existing = next(
                (
                    item
                    for item in group_config.data.get("groups", [])
                    if isinstance(item, dict) and item.get("umo") == umo
                ),
                None,
            )
            if existing is not None:
                raise DashboardError("该群已经存在分群配置", status_code=409)
            before = deepcopy(dict(self.plugin.config))
            try:
                profile = group_config.snapshot(umo)
                group_config.data.setdefault("groups", []).append(profile)
                self._save_config(self.plugin)
            except Exception:
                self.plugin.config.clear()
                self.plugin.config.update(before)
                raise
            return json_response(
                {
                    "ok": True,
                    "message": "已创建分群配置",
                    "config": self._config_response(umo),
                }
            )
        except Exception as exc:
            return self._error(exc, "创建分群配置失败")

    async def delete_group_profile(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            umo = str(payload.get("umo") or "").strip()
            if not valid_group_umo(umo):
                raise DashboardError("群 UMO 格式不正确")
            group_config = GroupConfig(self.plugin.config)
            profiles = group_config.data.get("groups", [])
            remaining = [
                item
                for item in profiles
                if not (isinstance(item, dict) and item.get("umo") == umo)
            ]
            if len(remaining) == len(profiles):
                raise DashboardError("该群没有分群配置", status_code=404)
            before = deepcopy(dict(self.plugin.config))
            try:
                group_config.data["groups"] = remaining
                self._save_config(self.plugin)
            except Exception:
                self.plugin.config.clear()
                self.plugin.config.update(before)
                raise
            return json_response(
                {
                    "ok": True,
                    "message": "已恢复继承全局配置",
                    "config": self._config_response(umo),
                }
            )
        except Exception as exc:
            return self._error(exc, "删除分群配置失败")

    # ------------------------------------------------------------------
    # Handler: 界面偏好
    # ------------------------------------------------------------------
    async def get_ui_preferences(self) -> Any:
        try:
            preferences = self.plugin.storage.ui_preferences()
            color = preferences.get("theme_color", "")
            if color and not THEME_COLOR_RE.fullmatch(color):
                color = ""
            return json_response({"theme_color": color})
        except Exception as exc:
            return self._error(exc, "读取界面偏好失败")

    async def save_ui_preferences(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            color = str(payload.get("theme_color") or "").strip()
            if color and not THEME_COLOR_RE.fullmatch(color):
                raise DashboardError("主题色必须是 #RRGGBB 格式")
            color = color.lower()
            self.plugin.storage.set_ui_preferences({"theme_color": color})
            return json_response(
                {
                    "ok": True,
                    "theme_color": color,
                    "message": "主题色已保存",
                }
            )
        except Exception as exc:
            return self._error(exc, "保存界面偏好失败")

    # ------------------------------------------------------------------
    # Handler: 安全导入
    # ------------------------------------------------------------------
    def _config_import_data(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict) or str(raw.get("plugin") or "") != PLUGIN_NAME:
            raise DashboardError("这不是本插件的配置快照")
        config = raw.get("config")
        if not isinstance(config, dict):
            raise DashboardError("配置快照缺少 config 对象")
        layout = config.get("config_layout_version", 0)
        if not isinstance(layout, int) or layout < 2:
            raise DashboardError("配置快照不是新版分群布局，无法安全导入")
        current_layout = int(
            getattr(self.plugin, "config", {}).get("config_layout_version", 0) or 0
        )
        if layout != current_layout:
            raise DashboardError("配置布局版本不一致，请先升级/重载插件再导入")
        management = config.get("group_management", {})
        if not isinstance(management, dict):
            raise DashboardError("配置快照的 group_management 必须是对象")
        if not isinstance(management.get("global_settings", {}), dict):
            raise DashboardError("global_settings 必须是对象")
        groups = management.get("groups", [])
        if not isinstance(groups, list):
            raise DashboardError("分群配置必须是列表")
        seen: set[str] = set()
        for item in groups:
            if not isinstance(item, dict) or not valid_group_umo(
                str(item.get("umo") or "")
            ):
                raise DashboardError("分群配置中存在无效的群 UMO")
            umo = str(item["umo"])
            if umo in seen:
                raise DashboardError(f"分群配置中存在重复 UMO：{umo}")
            seen.add(umo)
        scope = config.get("scope_settings", {})
        if not isinstance(scope, dict):
            raise DashboardError("scope_settings 必须是对象")
        return config

    def _config_import_preview(self, raw: Any) -> dict[str, Any]:
        config = self._config_import_data(raw)
        management = config.get("group_management", {})
        groups = management.get("groups", [])
        return {
            "kind": "config",
            "version": str(raw.get("version") or ""),
            "exported_at": str(raw.get("exported_at") or ""),
            "groups": len(groups),
            "global_settings": len(management.get("global_settings", {})),
            "scope_keys": len(config.get("scope_settings", {})),
        }

    def _apply_config_import(self, config: dict[str, Any], mode: str) -> dict[str, Any]:
        if mode not in {"merge", "replace"}:
            raise DashboardError("导入模式只能是 merge 或 replace")
        before = deepcopy(dict(self.plugin.config))
        backup = self.plugin.storage.path.with_name(
            "config-backup-"
            + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            + ".json"
        )
        backup.write_text(
            json.dumps(_json_safe(before), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        incoming_management = deepcopy(config.get("group_management", {}))
        incoming_scope = deepcopy(config.get("scope_settings", {}))
        if mode == "replace":
            self.plugin.config["group_management"] = incoming_management
            self.plugin.config["scope_settings"] = incoming_scope
        else:
            current_management = self.plugin.config.setdefault(
                "group_management", {}
            )
            current_management["enabled"] = incoming_management.get(
                "enabled", current_management.get("enabled", False)
            )
            current_management["global_settings"] = {
                **current_management.get("global_settings", {}),
                **incoming_management.get("global_settings", {}),
            }
            by_umo = {
                str(item.get("umo")): item
                for item in current_management.get("groups", [])
                if isinstance(item, dict) and item.get("umo")
            }
            for item in incoming_management.get("groups", []):
                by_umo[str(item["umo"])] = item
            current_management["groups"] = list(by_umo.values())
            self.plugin.config["scope_settings"] = {
                **self.plugin.config.get("scope_settings", {}),
                **incoming_scope,
            }
        self.plugin.config["config_layout_version"] = int(
            config.get("config_layout_version", 0)
        )
        try:
            self._save_config(self.plugin)
        except Exception:
            self.plugin.config.clear()
            self.plugin.config.update(before)
            raise
        if "pending_retention_days" in incoming_management.get(
            "global_settings", {}
        ):
            self.plugin.storage.retention_days = max(
                1, int(self.plugin._config("pending_retention_days", 30))
            )
            self.plugin.storage.prune()
        management = self.plugin.config.get("group_management", {})
        return {
            "ok": True,
            "mode": mode,
            "groups": len(management.get("groups", [])),
            "backup": str(backup),
        }

    async def import_preview(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            kind = str(payload.get("kind") or "").strip().lower()
            data = payload.get("data")
            if kind == "state":
                return json_response(
                    {"kind": "state", "preview": self.plugin.storage.state_preview(data)}
                )
            if kind == "config":
                return json_response(
                    {"kind": "config", "preview": self._config_import_preview(data)}
                )
            raise DashboardError("导入类型只能是 state 或 config")
        except Exception as exc:
            return self._error(exc, "预览导入失败")

    async def import_state(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            mode = str(payload.get("mode") or "merge").strip().lower()
            result = self.plugin.storage.import_state(payload.get("data"), mode)
            return json_response(result)
        except Exception as exc:
            return self._error(exc, "导入运行数据失败")

    async def import_config(self) -> Any:
        try:
            payload = await request.json(default={})
            if not isinstance(payload, dict):
                raise DashboardError("请求体格式不正确")
            config = self._config_import_data(payload.get("data"))
            mode = str(payload.get("mode") or "merge").strip().lower()
            result = self._apply_config_import(config, mode)
            return json_response(
                {
                    **result,
                    "message": "配置已导入，当前视图会刷新",
                    "config": self._config_response(""),
                }
            )
        except Exception as exc:
            return self._error(exc, "导入插件配置失败")

    # ------------------------------------------------------------------
    # Handler: 导出
    # ------------------------------------------------------------------
    async def export_state(self) -> Any:
        try:
            storage = self.plugin.storage
            storage.prune(save=False)
            storage.save()
            filename = (
                "qq-group-manage-state-"
                + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                + ".json"
            )
            return file_response(
                storage.path,
                filename=filename,
                content_type="application/json",
            )
        except Exception as exc:
            return self._error(exc, "导出运行数据失败")

    async def export_config(self) -> Any:
        try:
            return json_response(
                {
                    "plugin": PLUGIN_NAME,
                    "version": PLUGIN_VERSION,
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "config": _json_safe(dict(self.plugin.config)),
                }
            )
        except Exception as exc:
            return self._error(exc, "导出配置失败")


__all__ = ["DashboardAPI", "PLUGIN_NAME", "VIEW_NAME"]
