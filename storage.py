from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from astrbot.api import logger

SEEN_GROUP_REFRESH_SECONDS = 5 * 60
SEEN_GROUP_LIMIT = 1000
GROUP_UID_START = 100001
STATE_KEYS = (
    "group_admins",
    "group_feature_overrides",
    "pending",
    "reviewed",
    "verifications",
    "seen_groups",
    "group_notes",
    "group_names",
    "ui_preferences",
)


class PluginStorage:
    def __init__(self, path: Path, retention_days: int = 30) -> None:
        self.path = path
        self.retention_days = max(1, retention_days)
        self.data: dict[str, Any] = {
            "group_admins": {},
            "group_feature_overrides": {},
            "pending": {},
            "reviewed": {},
            "verifications": {},
            "seen_groups": {},
            "group_notes": {},
            "group_names": {},
            "group_ids": {},
            "free_group_ids": [],
            "ui_preferences": {},
        }
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._validate(raw)
        except FileNotFoundError:
            return
        except (ValueError, UnicodeError) as exc:
            backup = self.path.with_name(f"{self.path.stem}.corrupt-{uuid4().hex}.json")
            # Both paths stay in the same data directory. If preserving the file
            # fails, abort loading rather than overwrite the only recovery copy.
            self.path.replace(backup)
            logger.error("群管存储格式损坏，原文件已保留至 %s：%s", backup, exc)
            return
        except OSError as exc:
            raise OSError(f"无法读取群管存储 {self.path}，原文件未修改") from exc
        self.data.update(raw)
        self.data.pop("pending_counters", None)
        self.prune(save=False)

    @staticmethod
    def _validate(raw: Any) -> None:
        if not isinstance(raw, dict):
            raise ValueError("存储根节点必须是对象")
        for name in (
            "group_admins",
            "group_feature_overrides",
            "pending",
            "reviewed",
            "verifications",
            "seen_groups",
            "group_notes",
            "group_names",
            "group_ids",
            "ui_preferences",
        ):
            if not isinstance(raw.get(name, {}), dict):
                raise ValueError(f"{name} 必须是对象")
        if not isinstance(raw.get("free_group_ids", []), list):
            raise ValueError("free_group_ids 必须是列表")
        if any(
            not isinstance(item, dict) for item in raw.get("verifications", {}).values()
        ):
            raise ValueError("进群验证记录必须是对象")
        if any(
            not isinstance(value, str) for value in raw.get("reviewed", {}).values()
        ):
            raise ValueError("已审批记录必须包含时间字符串")
        for admins in raw.get("group_admins", {}).values():
            if not isinstance(admins, list) or any(
                not isinstance(member, str) for member in admins
            ):
                raise ValueError("群管名单必须是 OpenID 字符串列表")
        for overrides in raw.get("group_feature_overrides", {}).values():
            if not isinstance(overrides, dict) or any(
                not isinstance(value, bool) for value in overrides.values()
            ):
                raise ValueError("分群开关必须是布尔值对象")
        for item in raw.get("pending", {}).values():
            if not isinstance(item, dict):
                raise ValueError("待审记录必须是对象")
            for key in (
                "platform_id",
                "group_openid",
                "member_openid",
                "join_request_id",
                "stored_at",
                "ref_idx",
                "callback_token",
            ):
                if key in item and not isinstance(item[key], str):
                    raise ValueError(f"待审记录 {key} 必须是字符串")
            callbacks = item.get("review_callbacks", {})
            if not isinstance(callbacks, dict) or any(
                not isinstance(binding, dict) for binding in callbacks.values()
            ):
                raise ValueError("审批按钮映射必须是对象")
        for key, value in raw.get("ui_preferences", {}).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("界面偏好必须是字符串键值对象")
        for key, item in raw.get("seen_groups", {}).items():
            if not isinstance(key, str) or not isinstance(item, dict):
                raise ValueError("群组记录必须是对象")
            for field in ("platform_id", "group_openid", "last_seen"):
                if not isinstance(item.get(field), str):
                    raise ValueError(f"群组记录 {field} 必须是字符串")
        for key, note in raw.get("group_notes", {}).items():
            if not isinstance(key, str) or not isinstance(note, str):
                raise ValueError("群备注必须是字符串键值对象")
        for key, name in raw.get("group_names", {}).items():
            if not isinstance(key, str) or not isinstance(name, str):
                raise ValueError("群名必须是字符串键值对象")
        for key, value in raw.get("group_ids", {}).items():
            if not isinstance(key, str) or not str(value).isdigit():
                raise ValueError("群 UID 编号必须是字符串数字")
        if any(not str(value).isdigit() for value in raw.get("free_group_ids", [])):
            raise ValueError("空闲群 UID 必须是字符串数字")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)

    def group_admins(self, group_openid: str) -> list[str]:
        admins = self.data["group_admins"].get(group_openid, [])
        return [str(item) for item in admins]

    def add_group_admin(self, group_openid: str, member_openid: str) -> bool:
        return bool(self.update_group_admins(group_openid, [member_openid], add=True))

    def remove_group_admin(self, group_openid: str, member_openid: str) -> bool:
        return bool(self.update_group_admins(group_openid, [member_openid], add=False))

    def update_group_admins(
        self, group_openid: str, members: list[str], *, add: bool
    ) -> int:
        """Commit a whole command together; failed writes cannot change permissions."""
        groups = self.data["group_admins"]
        previous = groups.get(group_openid)
        admins = self.group_admins(group_openid)
        changed = 0
        for member in members:
            if add and member not in admins:
                admins.append(member)
                changed += 1
            elif not add and member in admins:
                admins.remove(member)
                changed += 1
        if not changed:
            return 0
        groups[group_openid] = admins
        try:
            self.save()
        except Exception:
            if previous is None:
                groups.pop(group_openid, None)
            else:
                groups[group_openid] = previous
            raise
        return changed

    def group_feature_override(self, group_umo: str, key: str) -> bool | None:
        overrides = self.data["group_feature_overrides"].get(group_umo, {})
        if not isinstance(overrides, dict):
            return None
        value = overrides.get(key)
        return value if isinstance(value, bool) else None

    def ui_preferences(self) -> dict[str, str]:
        preferences = self.data.get("ui_preferences")
        if not isinstance(preferences, dict):
            return {}
        return {
            str(key): str(value)
            for key, value in preferences.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    def set_ui_preferences(self, values: dict[str, str]) -> dict[str, str]:
        before = self.ui_preferences()
        preferences = self.data.get("ui_preferences")
        if not isinstance(preferences, dict):
            preferences = {}
            self.data["ui_preferences"] = preferences
        preferences.update({str(key): str(value) for key, value in values.items()})
        try:
            self.save()
        except Exception:
            self.data["ui_preferences"] = before
            raise
        return self.ui_preferences()

    def seen_groups(self) -> list[dict[str, str]]:
        groups = self.data.get("seen_groups")
        if not isinstance(groups, dict):
            return []
        result: list[dict[str, str]] = []
        for item in groups.values():
            if not isinstance(item, dict):
                continue
            platform_id = str(item.get("platform_id") or "")
            group_openid = str(item.get("group_openid") or "")
            if not platform_id or not group_openid:
                continue
            result.append(
                {
                    "umo": f"{platform_id}:GroupMessage:{group_openid}",
                    "platform_id": platform_id,
                    "group_openid": group_openid,
                    "last_seen": str(item.get("last_seen") or ""),
                }
            )
        result.sort(key=lambda item: item["last_seen"], reverse=True)
        return result

    def remember_group(
        self,
        platform_id: str,
        group_openid: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Remember a group seen on a group message without storing its content.

        A busy group updates ``last_seen`` at most once every five minutes so
        ordinary chat does not write ``state.json`` on every message.
        """
        platform_id = str(platform_id or "").strip()
        group_openid = str(group_openid or "").strip()
        if not platform_id or not group_openid:
            return False
        seen = self.data.get("seen_groups")
        if not isinstance(seen, dict):
            seen = {}
            self.data["seen_groups"] = seen
        umo = f"{platform_id}:GroupMessage:{group_openid}"
        current = now or datetime.now(timezone.utc)
        previous = seen.get(umo)
        if isinstance(previous, dict):
            try:
                last_seen = datetime.fromisoformat(str(previous.get("last_seen") or ""))
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                if 0 <= (current - last_seen).total_seconds() < SEEN_GROUP_REFRESH_SECONDS:
                    self.ensure_group_uid(umo)
                    return False
            except (TypeError, ValueError):
                pass
        before = dict(seen)
        seen[umo] = {
            "platform_id": platform_id,
            "group_openid": group_openid,
            "last_seen": current.isoformat(),
        }
        if len(seen) > SEEN_GROUP_LIMIT:
            oldest = sorted(
                seen,
                key=lambda key: str(seen[key].get("last_seen") or ""),
            )[: len(seen) - SEEN_GROUP_LIMIT]
            for key in oldest:
                seen.pop(key, None)
        try:
            self.save()
        except Exception:
            self.data["seen_groups"] = before
            raise
        self.ensure_group_uid(umo)
        return True

    def group_note(self, umo: str) -> str:
        notes = self.data.get("group_notes")
        if not isinstance(notes, dict):
            return ""
        return str(notes.get(str(umo or "")) or "")

    def group_name(self, umo: str) -> str:
        names = self.data.get("group_names")
        if not isinstance(names, dict):
            return ""
        return str(names.get(str(umo or "")) or "")

    def set_group_name(self, umo: str, name: str) -> str:
        umo = str(umo or "").strip()
        name = str(name or "").strip()[:80]
        if not umo:
            return ""
        names = self.data.get("group_names")
        if not isinstance(names, dict):
            names = {}
            self.data["group_names"] = names
        before = dict(names)
        previous = names.get(umo)
        if name:
            names[umo] = name
        else:
            names.pop(umo, None)
        if previous == (name or None):
            return self.group_name(umo)
        try:
            self.save()
        except Exception:
            self.data["group_names"] = before
            raise
        return self.group_name(umo)

    def group_uid(self, umo: str) -> str:
        ids = self.data.get("group_ids")
        if not isinstance(ids, dict):
            return ""
        return str(ids.get(str(umo or "")) or "")

    def ensure_group_uids(self, umos: list[str]) -> dict[str, str]:
        """Allocate stable 100001, 100002... IDs, reusing IDs freed by kick."""
        ids = self.data.get("group_ids")
        if not isinstance(ids, dict):
            ids = {}
            self.data["group_ids"] = ids
        free_raw = self.data.get("free_group_ids")
        free = [str(value) for value in free_raw] if isinstance(free_raw, list) else []
        used = {str(value) for value in ids.values()}
        free = sorted({value for value in free if value not in used}, key=int)
        missing = [umo for umo in umos if umo and umo not in ids]
        if not missing:
            return {umo: str(ids[umo]) for umo in umos if umo in ids}
        before_ids = dict(ids)
        before_free = list(free)
        next_number = max([int(value) for value in used] + [GROUP_UID_START - 1]) + 1
        try:
            for umo in missing:
                if free:
                    uid = free.pop(0)
                else:
                    uid = str(next_number)
                    next_number += 1
                ids[umo] = uid
                used.add(uid)
            self.data["free_group_ids"] = free
            self.save()
        except Exception:
            self.data["group_ids"] = before_ids
            self.data["free_group_ids"] = before_free
            raise
        return {umo: str(ids[umo]) for umo in umos if umo in ids}

    def ensure_group_uid(self, umo: str) -> str:
        return self.ensure_group_uids([umo]).get(umo, "")

    def set_group_note(self, umo: str, note: str) -> str:
        umo = str(umo or "").strip()
        note = str(note or "").strip()
        if not umo:
            return ""
        notes = self.data.get("group_notes")
        if not isinstance(notes, dict):
            notes = {}
            self.data["group_notes"] = notes
        before = dict(notes)
        previous = notes.get(umo)
        if note:
            notes[umo] = note
        else:
            notes.pop(umo, None)
        if previous == (note or None):
            return self.group_note(umo)
        try:
            self.save()
        except Exception:
            self.data["group_notes"] = before
            raise
        return self.group_note(umo)

    def set_group_feature_override(
        self,
        group_umo: str,
        key: str,
        value: bool,
    ) -> None:
        groups = self.data["group_feature_overrides"]
        overrides = groups.get(group_umo)
        if not isinstance(overrides, dict):
            overrides = {}
        overrides[key] = bool(value)
        groups[group_umo] = overrides
        self.save()

    def put_pending(self, notification_message_id: str, item: dict[str, Any]) -> None:
        item = dict(item)
        item["stored_at"] = datetime.now(timezone.utc).isoformat()
        self.data["pending"][notification_message_id] = item
        self.prune(save=False)
        self.save()

    def reserve_pending(self, item: dict[str, Any]) -> str:
        """Persist an application until its notification message ID is available."""
        item = dict(item)
        group_openid = str(item.get("group_openid") or "")
        item["stored_at"] = datetime.now(timezone.utc).isoformat()
        join_request_id = str(item["join_request_id"])
        key = f"request:{item.get('platform_id', '')}:{group_openid}:{join_request_id}"
        previous = self.data["pending"].get(key)
        self.data["pending"][key] = item
        self.prune(save=False)
        try:
            self.save()
        except Exception:
            if previous is None:
                self.data["pending"].pop(key, None)
            else:
                self.data["pending"][key] = previous
            raise
        return key

    def bind_pending_message(
        self, pending_key: str, message_id: str, ref_idx: str = ""
    ) -> str:
        """Save QQ's reference index even if the send response has no message ID."""
        item = self.data["pending"].pop(pending_key, None)
        if not isinstance(item, dict):
            return pending_key
        if ref_idx:
            item["ref_idx"] = ref_idx
        key = message_id or pending_key
        self.data["pending"][key] = item
        self.save()
        return key

    def find_pending_by_quote(
        self, references: set[str], platform_id: str, group_openid: str
    ) -> tuple[str, dict[str, Any]] | None:
        self.prune()
        matched = None
        for key, item in self.data["pending"].items():
            if not isinstance(item, dict):
                continue
            if (
                item.get("platform_id") != platform_id
                or item.get("group_openid") != group_openid
            ):
                continue
            if key not in references and item.get("ref_idx") not in references:
                continue
            if matched is not None:
                return None  # Conflicting quote identifiers must never pick a request.
            matched = str(key), dict(item)
        return matched

    def get_pending(self, notification_message_id: str) -> dict[str, Any] | None:
        item = self.data["pending"].get(notification_message_id)
        return dict(item) if isinstance(item, dict) else None

    def find_pending_by_join_request_id(
        self,
        join_request_id: str,
        group_openid: str = "",
        platform_id: str = "",
    ) -> tuple[str, dict[str, Any]] | None:
        for message_id, item in self.data["pending"].items():
            if not isinstance(item, dict):
                continue
            if str(item.get("join_request_id") or "") != join_request_id:
                continue
            if group_openid and str(item.get("group_openid") or "") != group_openid:
                continue
            if platform_id and str(item.get("platform_id") or "") != platform_id:
                continue
            return str(message_id), dict(item)
        return None

    def find_pending_by_token(self, token: str) -> tuple[str, dict[str, Any]] | None:
        self.prune()
        for message_id, item in self.data["pending"].items():
            if not isinstance(item, dict):
                continue
            if item.get("callback_token") == token or token in item.get(
                "review_callbacks", {}
            ):
                return str(message_id), dict(item)
        return None

    def remove_reviewed_request(
        self, platform_id: str, group_openid: str, join_request_id: str
    ) -> None:
        """Keep a completion marker and invalidate every card for the application."""
        key = json.dumps([platform_id, group_openid, join_request_id])
        self.data["reviewed"][key] = datetime.now(timezone.utc).isoformat()
        keys = [
            key
            for key, item in self.data["pending"].items()
            if item.get("platform_id") == platform_id
            and item.get("group_openid") == group_openid
            and str(item.get("join_request_id")) == join_request_id
        ]
        for key in keys:
            del self.data["pending"][key]
        self.prune(save=False)
        # Keep the live completion marker even if persistence fails: QQ has
        # already executed the operation, so a retry must not execute it again.
        self.save()

    def is_reviewed(
        self, platform_id: str, group_openid: str, join_request_id: str
    ) -> bool:
        self.prune(save=False)
        return (
            json.dumps([platform_id, group_openid, join_request_id])
            in self.data["reviewed"]
        )

    def remove_pending(self, notification_message_id: str) -> None:
        if self.data["pending"].pop(notification_message_id, None) is not None:
            self.save()

    @staticmethod
    def _verification_key(platform_id: str, group_openid: str, member_openid: str) -> str:
        return json.dumps([platform_id, group_openid, member_openid])

    def verification(
        self, platform_id: str, group_openid: str, member_openid: str
    ) -> dict[str, Any] | None:
        """返回实时记录对象，调用方修改后需调用 put_verification 保存。"""
        return self.data["verifications"].get(
            self._verification_key(platform_id, group_openid, member_openid)
        )

    def verifications(self) -> list[dict[str, Any]]:
        return list(self.data["verifications"].values())

    def find_verification_by_token(self, token: str) -> dict[str, Any] | None:
        """按题目 token 查找实时记录；token 每题随机生成且唯一。"""
        for record in self.data["verifications"].values():
            if isinstance(record, dict) and record.get("token") == token:
                return record
        return None

    def put_verification(self, record: dict[str, Any]) -> None:
        key = self._verification_key(
            record["platform_id"], record["group_openid"], record["member_openid"]
        )
        self.data["verifications"][key] = record
        self.save()

    def remove_verification(
        self, platform_id: str, group_openid: str, member_openid: str
    ) -> dict[str, Any] | None:
        record = self.data["verifications"].pop(
            self._verification_key(platform_id, group_openid, member_openid), None
        )
        if record is not None:
            self.save()
        return record

    def prune(self, *, save: bool = True) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        removed = False
        for section in ("pending", "reviewed"):
            for key, item in list(self.data[section].items()):
                timestamp = item.get("stored_at", "") if section == "pending" else item
                try:
                    stored_at = datetime.fromisoformat(str(timestamp))
                    if stored_at.tzinfo is None:
                        stored_at = stored_at.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    stored_at = datetime.min.replace(tzinfo=timezone.utc)
                if stored_at < cutoff:
                    del self.data[section][key]
                    removed = True
        # 进群验证记录不在这里清理：只在验证通过、退群或管理员处理时删除。
        if removed and save:
            self.save()

    # ---------- 机器人退群清理 ----------

    def purge_group(self, platform_id: str, group_openid: str) -> dict[str, Any]:
        """Remove a group from every runtime index without keeping an archive."""
        platform_id = str(platform_id or "").strip()
        group_openid = str(group_openid or "").strip()
        if not platform_id or not group_openid:
            return {"removed": False, "reason": "缺少平台或群 ID"}
        umo = f"{platform_id}:GroupMessage:{group_openid}"
        pending = [
            key
            for key, value in self.data.get("pending", {}).items()
            if isinstance(value, dict)
            and str(value.get("platform_id") or "") == platform_id
            and str(value.get("group_openid") or "") == group_openid
        ]
        verifications = [
            key
            for key, value in self.data.get("verifications", {}).items()
            if isinstance(value, dict)
            and str(value.get("platform_id") or "") == platform_id
            and str(value.get("group_openid") or "") == group_openid
        ]
        reviewed = []
        for key in self.data.get("reviewed", {}):
            try:
                parts = json.loads(key)
            except (TypeError, ValueError):
                continue
            if (
                isinstance(parts, list)
                and len(parts) >= 2
                and str(parts[0]) == platform_id
                and str(parts[1]) == group_openid
            ):
                reviewed.append(key)
        before = deepcopy(self.data)
        freed_uid = ""
        try:
            for section in ("seen_groups", "group_notes", "group_names", "group_feature_overrides"):
                self.data.get(section, {}).pop(umo, None)
            self.data.get("group_admins", {}).pop(group_openid, None)
            for key in pending:
                self.data.get("pending", {}).pop(key, None)
            for key in verifications:
                self.data.get("verifications", {}).pop(key, None)
            for key in reviewed:
                self.data.get("reviewed", {}).pop(key, None)
            ids = self.data.get("group_ids")
            if isinstance(ids, dict):
                freed_uid = str(ids.pop(umo, "") or "")
            if freed_uid:
                free = self.data.get("free_group_ids")
                if not isinstance(free, list):
                    free = []
                    self.data["free_group_ids"] = free
                if freed_uid not in free:
                    free.append(freed_uid)
                    free.sort(key=int)
            self.save()
        except Exception:
            self.data = before
            raise
        return {
            "removed": True,
            "umo": umo,
            "freed_uid": freed_uid,
            "pending": len(pending),
            "verifications": len(verifications),
            "reviewed": len(reviewed),
        }

    # ---------- 安全导入 ----------

    @staticmethod
    def _import_body(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
            raw = raw["data"]
        if not isinstance(raw, dict):
            raise ValueError("运行数据快照根节点必须是对象")
        schema = raw.get("schema_version")
        if schema is not None and (not isinstance(schema, int) or schema > 1):
            raise ValueError("运行数据快照版本高于当前插件支持的版本")
        PluginStorage._validate(raw)
        return raw

    @staticmethod
    def state_preview(raw: Any) -> dict[str, Any]:
        data = PluginStorage._import_body(raw)
        admins = data.get("group_admins", {})
        pending = data.get("pending", {})
        verifications = data.get("verifications", {})
        seen = data.get("seen_groups", {})
        notes = data.get("group_notes", {})
        names = data.get("group_names", {})
        prefs = data.get("ui_preferences", {})
        return {
            "kind": "state",
            "admin_groups": len(admins),
            "admin_members": sum(len(items) for items in admins.values()),
            "pending": len(pending),
            "verifications": len(verifications),
            "seen_groups": len(seen),
            "group_notes": len(notes),
            "group_names": len(names),
            "ui_preferences": len(prefs),
        }

    def import_state(self, raw: Any, mode: str) -> dict[str, Any]:
        data = self._import_body(raw)
        if mode not in {"merge", "replace"}:
            raise ValueError("导入模式只能是 merge 或 replace")
        before = deepcopy(self.data)
        candidate = deepcopy(self.data)
        if mode == "replace":
            candidate = {key: deepcopy(data.get(key, {})) for key in STATE_KEYS}
        else:
            for key in STATE_KEYS:
                incoming = data.get(key, {})
                if not isinstance(incoming, dict):
                    continue
                if key == "group_admins":
                    for group, members in incoming.items():
                        existing = candidate[key].setdefault(group, [])
                        for member in members:
                            if member not in existing:
                                existing.append(member)
                elif key == "group_feature_overrides":
                    for group, overrides in incoming.items():
                        current = candidate[key].setdefault(group, {})
                        current.update(overrides)
                else:
                    candidate[key].update(deepcopy(incoming))
        backup_path = self.path.with_name(
            f"{self.path.stem}.bak-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
        )
        if self.path.exists():
            shutil.copy2(self.path, backup_path)
        self.data = candidate
        try:
            self.prune(save=False)
            self.save()
        except Exception:
            self.data = before
            raise
        summary = self.state_preview(data)
        summary.update({"ok": True, "mode": mode, "backup": str(backup_path)})
        return summary

