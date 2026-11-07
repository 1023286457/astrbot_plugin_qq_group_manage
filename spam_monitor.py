"""内存中的成员消息频率追踪，供刷屏监控与 WebUI 实时面板使用。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

RETENTION_SECONDS = 3600.0


@dataclass
class _Track:
    events: deque = field(default_factory=deque)
    last_seen: float = 0.0
    punished_at: float = 0.0
    mute_seconds: float = 0.0
    reason: str = ""


class SpamMonitor:
    """按 (群 UMO, 成员 ID) 记录最近一小时的消息时间戳。"""

    def __init__(self, retention: float = RETENTION_SECONDS) -> None:
        self.retention = retention
        self._tracks: dict[tuple[str, str], _Track] = {}
        self._last_prune = 0.0

    def record(
        self,
        group_umo: str,
        user_id: str,
        message_id: str,
        now: float,
    ) -> dict[int, int]:
        if now - self._last_prune > 60:
            self._prune_all(now)
            self._last_prune = now
        key = (group_umo, user_id)
        track = self._tracks.get(key)
        if track is None:
            track = _Track()
            self._tracks[key] = track
        track.events.append((now, str(message_id or "")))
        track.last_seen = now
        self._prune(track, now)
        return self._counts(track, now)

    def _prune(self, track: _Track, now: float) -> None:
        cutoff = now - self.retention
        while track.events and track.events[0][0] < cutoff:
            track.events.popleft()

    def _prune_all(self, now: float) -> None:
        for key, track in list(self._tracks.items()):
            self._prune(track, now)
            if not track.events:
                self._tracks.pop(key, None)

    @staticmethod
    def _counts(track: _Track, now: float) -> dict[int, int]:
        counts = {1: 0, 60: 0, 3600: 0}
        for timestamp, _ in reversed(track.events):
            age = now - timestamp
            if age <= 1:
                counts[1] += 1
            if age <= 60:
                counts[60] += 1
            if age <= 3600:
                counts[3600] += 1
            else:
                break
        return counts

    def recent_ids(self, group_umo: str, user_id: str, limit: int) -> list[str]:
        if limit <= 0:
            return []
        track = self._tracks.get((group_umo, user_id))
        if track is None:
            return []
        result: list[str] = []
        for _, message_id in reversed(track.events):
            if message_id:
                result.append(message_id)
            if len(result) >= limit:
                break
        return result

    def in_cooldown(self, group_umo: str, user_id: str, now: float) -> bool:
        track = self._tracks.get((group_umo, user_id))
        if track is None or track.punished_at <= 0:
            return False
        return (now - track.punished_at) < max(1.0, track.mute_seconds)

    def mark_punished(
        self,
        group_umo: str,
        user_id: str,
        now: float,
        mute_seconds: float,
        reason: str,
    ) -> None:
        key = (group_umo, user_id)
        track = self._tracks.get(key)
        if track is None:
            track = _Track()
            self._tracks[key] = track
        track.punished_at = now
        track.mute_seconds = max(0.0, float(mute_seconds))
        track.reason = reason

    def snapshot(
        self, now: float, active_window: float = 60.0
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        groups: set[str] = set()
        active_users = 0
        for (group_umo, user_id), track in list(self._tracks.items()):
            self._prune(track, now)
            if not track.events:
                self._tracks.pop((group_umo, user_id), None)
                continue
            counts = self._counts(track, now)
            groups.add(group_umo)
            last_seen_ago = max(0.0, now - track.last_seen)
            if last_seen_ago <= active_window:
                active_users += 1
            if self.in_cooldown(group_umo, user_id, now):
                status_key, status = "muted", "已禁言"
            elif counts[60] > 0:
                status_key, status = "tracking", "追踪中"
            else:
                status_key, status = "normal", "正常"
            rows.append(
                {
                    "umo": group_umo,
                    "group_id": group_umo.rsplit(":", 1)[-1],
                    "user_id": user_id,
                    "queue": len(track.events),
                    "recent_1s": counts[1],
                    "recent_1m": counts[60],
                    "recent_1h": counts[3600],
                    "status": status,
                    "status_key": status_key,
                    "last_seen_ago": round(last_seen_ago, 1),
                    "reason": track.reason,
                }
            )
        rows.sort(
            key=lambda item: (
                -item["recent_1m"],
                -item["recent_1h"],
                item["last_seen_ago"],
            )
        )
        return {
            "tracked_groups": len(groups),
            "tracked_users": len(rows),
            "active_users": active_users,
            "rows": rows,
        }

    def clear(self) -> None:
        self._tracks.clear()
