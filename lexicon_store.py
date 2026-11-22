"""本地词库：内置词表 + 本地上传词表，供违禁词拦截和 WebUI 使用。"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

PLUGIN_DIR = Path(__file__).resolve().parent
BUILTIN_DIR = PLUGIN_DIR / "lexicons"
STATE_FILE = "lexicons.json"
MAX_WORDS = 20000


def _flatten(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, list):
        for item in value:
            result.extend(_flatten(item))
    elif isinstance(value, dict):
        for item in value.values():
            result.extend(_flatten(item))
    elif value is not None:
        text = str(value).strip()
        if text:
            result.append(text)
    return result


def _clean_words(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in _flatten(values):
        text = item.strip()
        if not text or text.startswith(("#", "//")):
            continue
        if text not in seen:
            seen.add(text)
            result.append(text[:120])
        if len(result) >= MAX_WORDS:
            break
    return result


def parse_lexicon(content: str) -> tuple[list[str], list[str]]:
    """解析 TXT/CSV/JSON 词表，返回 (字面量, 正则)。"""
    text = str(content or "").strip()
    if not text:
        return [], []
    literals: list[str] = []
    regexes: list[str] = []

    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if data is not None:
            if isinstance(data, dict):
                words = data.get("words") or data.get("keywords") or data.get("key_words")
                patterns = data.get("regex") or data.get("regexes") or data.get("patterns")
                categories = data.get("categories") or data.get("分类")
                literals.extend(_clean_words(words))
                if categories:
                    literals.extend(_clean_words(categories))
                regexes.extend(_clean_words(patterns))
            else:
                literals.extend(_clean_words(data))
            return _clean_words(literals), _clean_words(regexes)

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        if line.startswith("re:") or (line.startswith("/") and line.endswith("/") and len(line) > 2):
            pattern = line[3:].strip() if line.lower().startswith("re:") else line[1:-1]
            if pattern:
                regexes.append(pattern[:300])
            continue
        # CSV 第一个字段作为词条；TXT 一行一条。
        word = line.split(",", 1)[0].strip()
        if word:
            literals.append(word[:120])
    return _clean_words(literals), _clean_words(regexes)


class LexiconStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / STATE_FILE
        self.state: dict[str, Any] = {"enabled": [], "custom": []}
        self.builtins: dict[str, dict[str, Any]] = {}
        self._load_builtins()
        self._load_state()

    def _load_builtins(self) -> None:
        if not BUILTIN_DIR.is_dir():
            return
        for path in sorted(BUILTIN_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            literals = _clean_words(data.get("categories"))
            regexes = _clean_words(data.get("regexes"))
            lid = f"builtin_{path.stem}"
            self.builtins[lid] = {
                "id": lid,
                "name": str(data.get("name") or path.stem),
                "description": str(data.get("description") or ""),
                "words": literals,
                "regex": regexes,
                "builtin": True,
            }

    def _load_state(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict):
            enabled = data.get("enabled")
            custom = data.get("custom")
            if isinstance(enabled, list):
                self.state["enabled"] = [str(item) for item in enabled]
            if isinstance(custom, list):
                self.state["custom"] = [item for item in custom if isinstance(item, dict)]

    def _save_state(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _all(self) -> list[dict[str, Any]]:
        result = list(self.builtins.values()) + list(self.state.get("custom") or [])
        for item in result:
            item["words"] = _clean_words(item.get("words"))
            item["regex"] = _clean_words(item.get("regex"))
        return result

    def _enabled_set(self) -> set[str]:
        return {str(item) for item in self.state.get("enabled") or []}

    def _is_enabled(self, item: dict[str, Any]) -> bool:
        return str(item.get("id")) in self._enabled_set()

    def payload(self, item: dict[str, Any]) -> dict[str, Any]:
        words = item.get("words") or []
        regexes = item.get("regex") or []
        return {
            "id": item.get("id"),
            "name": item.get("name") or "未命名词库",
            "description": item.get("description") or "",
            "count": len(words) + len(regexes),
            "literal_count": len(words),
            "regex_count": len(regexes),
            "enabled": self._is_enabled(item),
            "builtin": bool(item.get("builtin")),
        }

    def list_payload(self) -> dict[str, Any]:
        items = self._all()
        rows = [self.payload(item) for item in items]
        enabled_rows = [row for row in rows if row["enabled"]]
        literals = sum(row["literal_count"] for row in enabled_rows)
        regexes = sum(row["regex_count"] for row in enabled_rows)
        chinese = 0
        for item in items:
            if not self._is_enabled(item):
                continue
            for word in item.get("words") or []:
                chinese += len(re.findall(r"[\u4e00-\u9fff]", word))
        custom_count = sum(1 for row in rows if not row["builtin"])
        return {
            "lexicons": rows,
            "stats": {
                "lexicon_count": len(rows),
                "enabled_count": len(enabled_rows),
                "pattern_count": literals + regexes,
                "literal_count": literals,
                "regex_count": regexes,
                "chinese_count": chinese,
                "custom_count": custom_count,
                "allow_count": 0,
                "error_count": 0,
            },
        }

    def toggle(self, lid: str, enabled: bool) -> bool:
        ids = self._enabled_set()
        if enabled:
            ids.add(lid)
        else:
            ids.discard(lid)
        self.state["enabled"] = sorted(ids)
        self._save_state()
        return True

    def upload(
        self,
        *,
        name: str,
        content: str,
        mode: str = "new",
        target_id: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        literals, regexes = parse_lexicon(content)
        if not literals and not regexes:
            raise ValueError("没有解析到有效词条")
        target = None
        if mode in {"append", "merge"} and target_id:
            target = next(
                (item for item in self.state["custom"] if item.get("id") == target_id),
                None,
            )
        if target is None:
            target = {
                "id": f"custom_{uuid.uuid4().hex[:12]}",
                "name": (name or "本地上传").strip()[:40],
                "description": (description or "本地上传词库").strip()[:120],
                "words": [],
                "regex": [],
                "builtin": False,
            }
            self.state["custom"].append(target)
        before = len(target.get("words") or []) + len(target.get("regex") or [])
        target["words"] = _clean_words(list(target.get("words") or []) + literals)
        target["regex"] = _clean_words(list(target.get("regex") or []) + regexes)
        total = len(target["words"]) + len(target["regex"])
        ids = self._enabled_set()
        ids.add(target["id"])
        self.state["enabled"] = sorted(ids)
        self._save_state()
        return {
            "ok": True,
            "id": target["id"],
            "name": target["name"],
            "count": total,
            "added": total - before,
        }

    def delete(self, lid: str) -> bool:
        before = len(self.state.get("custom") or [])
        self.state["custom"] = [
            item for item in self.state.get("custom") or [] if item.get("id") != lid
        ]
        self.state["enabled"] = [
            item for item in self.state.get("enabled") or [] if item != lid
        ]
        self._save_state()
        return len(self.state["custom"]) != before

    def export(self, lid: str) -> str:
        item = next((item for item in self._all() if item.get("id") == lid), None)
        if item is None:
            raise ValueError("词库不存在")
        return json.dumps(
            {
                "name": item.get("name"),
                "description": item.get("description"),
                "words": item.get("words") or [],
                "regex": item.get("regex") or [],
            },
            ensure_ascii=False,
            indent=2,
        )

    def match(self, text: str) -> bool:
        source = str(text or "")
        if not source:
            return False
        for item in self._all():
            if not self._is_enabled(item):
                continue
            for word in item.get("words") or []:
                if word and word in source:
                    return True
            for pattern in item.get("regex") or []:
                try:
                    if re.search(pattern, source):
                        return True
                except re.error:
                    continue
        return False

    def test(self, text: str, include_disabled: bool = False) -> dict[str, Any]:
        """返回命中明细；为避免在界面展开敏感词，不返回命中词本身。"""
        source = str(text or "")
        hits: list[dict[str, Any]] = []
        for item in self._all():
            if not include_disabled and not self._is_enabled(item):
                continue
            for word in item.get("words") or []:
                start = source.find(word)
                if start >= 0:
                    hits.append(
                        {
                            "lexicon": item.get("name") or "未命名词库",
                            "kind": "literal",
                            "length": len(word),
                            "start": start,
                            "end": start + len(word),
                        }
                    )
            for pattern in item.get("regex") or []:
                try:
                    match = re.search(pattern, source)
                except re.error:
                    continue
                if match:
                    hits.append(
                        {
                            "lexicon": item.get("name") or "未命名词库",
                            "kind": "regex",
                            "length": len(match.group(0)),
                            "start": match.start(),
                            "end": match.end(),
                        }
                    )
        return {"count": len(hits), "hits": hits[:100]}
