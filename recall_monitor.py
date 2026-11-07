"""内存中的风险消息撤回记录，供 WebUI「风险消息撤回」页面展示。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Deque

RETENTION_SECONDS = 7 * 86400.0
MAX_EVENTS = 500


@dataclass
class RecallEvent:
    at: float
    group_umo: str
    group_id: str
    user_id: str
    kind: str
    content: str
    message_id: str


class RecallMonitor:
    """保存最近被撤回的链接与二维码记录。"""

    def __init__(
        self,
        retention: float = RETENTION_SECONDS,
        max_events: int = MAX_EVENTS,
    ) -> None:
        self.retention = retention
        self.max_events = max_events
        self._events: Deque[RecallEvent] = deque()
        self._message_ids: set[str] = set()

    def record(
        self,
        group_umo: str,
        group_id: str,
        user_id: str,
        kind: str,
        content: str,
        message_id: str,
        now: float,
    ) -> None:
        message_id = str(message_id or "")
        if message_id and message_id in self._message_ids:
            return
        self._events.append(
            RecallEvent(
                at=now,
                group_umo=group_umo,
                group_id=group_id,
                user_id=user_id,
                kind="qr" if kind == "qr" else "link",
                content=str(content or "")[:1000],
                message_id=message_id,
            )
        )
        if message_id:
            self._message_ids.add(message_id)
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.retention
        while self._events and self._events[0].at < cutoff:
            old = self._events.popleft()
            if old.message_id:
                self._message_ids.discard(old.message_id)
        while len(self._events) > self.max_events:
            old = self._events.popleft()
            if old.message_id:
                self._message_ids.discard(old.message_id)

    def snapshot(self, now: float) -> dict[str, Any]:
        self._prune(now)
        rows: list[dict[str, Any]] = []
        groups: set[str] = set()
        link_count = 0
        qr_count = 0
        for event in reversed(self._events):
            groups.add(event.group_umo)
            if event.kind == "qr":
                qr_count += 1
            else:
                link_count += 1
            rows.append(
                {
                    "umo": event.group_umo,
                    "group_id": event.group_id or event.group_umo.rsplit(":", 1)[-1],
                    "user_id": event.user_id,
                    "kind": event.kind,
                    "kind_label": "二维码" if event.kind == "qr" else "链接",
                    "content": event.content,
                    "is_url": event.kind == "qr",
                    "time": datetime.fromtimestamp(event.at).strftime(
                        "%m-%d %H:%M:%S"
                    ),
                    "seconds_ago": round(max(0.0, now - event.at), 1),
                }
            )
        return {
            "tracked_groups": len(groups),
            "total": len(rows),
            "link_count": link_count,
            "qr_count": qr_count,
            "rows": rows,
        }

    def clear(self) -> None:
        self._events.clear()
        self._message_ids.clear()
