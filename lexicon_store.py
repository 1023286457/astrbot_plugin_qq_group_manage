"""独立实现的规则中心与词库存储。

设计目标：
- 不依赖任何第三方词表文件，仓库内不携带预置敏感词。
- 关键词按“词库分类”管理，正则规则按条管理，二者共用同一个页面。
- 旧版 lexicons.json 中用户自己上传的词库会迁移过来；旧的内置文件不再读取。
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

STATE_FILE = "lexicons.json"
BUILTIN_SEED_FILE = Path(__file__).resolve().parent / "builtin_lexicons.json"
MAX_WORDS = 20000
MAX_RULES = 30000
MAX_WORD_LENGTH = 120
MAX_PATTERN_LENGTH = 300

DEFAULT_CATEGORIES = (
    {
        "id": "cat_ad",
        "name": "广告引流",
        "description": "推广、联系方式、引流类关键词",
    },
    {
        "id": "cat_abuse",
        "name": "辱骂攻击",
        "description": "人身攻击、侮辱性表达",
    },
    {
        "id": "cat_porn",
        "name": "色情内容",
        "description": "色情、低俗及性相关内容",
    },
)
DEFAULT_CATEGORY_MAP = {item["id"]: item for item in DEFAULT_CATEGORIES}
DEFAULT_CATEGORY_NAME_MAP = {item["name"]: item for item in DEFAULT_CATEGORIES}


def _clean_text(value: Any, limit: int = MAX_WORD_LENGTH) -> str:
    return str(value or "").strip()[:limit]


def _flatten(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, list):
        for item in value:
            result.extend(_flatten(item))
    elif isinstance(value, dict):
        for item in value.values():
            result.extend(_flatten(item))
    elif value is not None:
        text = _clean_text(value)
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
            result.append(text[:MAX_WORD_LENGTH])
        if len(result) >= MAX_WORDS:
            break
    return result


def _clean_patterns(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in _flatten(values):
        pattern = item.strip()
        if not pattern or pattern in seen:
            continue
        if len(pattern) > MAX_PATTERN_LENGTH or not _valid_pattern(pattern):
            continue
        seen.add(pattern)
        result.append(pattern)
        if len(result) >= MAX_RULES:
            break
    return result


def _valid_pattern(pattern: str) -> bool:
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True


def parse_lexicon(content: str) -> tuple[list[str], list[str]]:
    """解析 TXT/CSV/JSON：返回 (关键词, 正则表达式)。"""
    text = str(content or "").strip()
    if not text:
        return [], []
    literals: list[str] = []
    regexes: list[str] = []

    if text.startswith(("{", "[")):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if data is not None:
            if isinstance(data, dict):
                words = data.get("words") or data.get("keywords") or data.get("key_words")
                patterns = data.get("regex") or data.get("regexes") or data.get("patterns")
                literals.extend(_clean_words(words))
                regexes.extend(_clean_patterns(patterns))
            else:
                literals.extend(_clean_words(data))
            return _clean_words(literals), _clean_patterns(regexes)

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//")):
            continue
        if line.lower().startswith("re:"):
            pattern = line[3:].strip()
        elif line.startswith("/") and line.endswith("/") and len(line) > 2:
            pattern = line[1:-1]
        else:
            pattern = ""
        if pattern:
            if len(pattern) <= MAX_PATTERN_LENGTH and _valid_pattern(pattern):
                regexes.append(pattern)
            continue
        word = line.split(",", 1)[0].strip()
        if word:
            literals.append(word[:MAX_WORD_LENGTH])
    return _clean_words(literals), _clean_patterns(regexes)


class LexiconStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / STATE_FILE
        self.state: dict[str, Any] = {"version": 2, "categories": []}
        self._regex_cache: dict[str, re.Pattern[str]] = {}
        self._load_state()

    # ---------- 存储 ----------

    @staticmethod
    def _new_category(name: str, description: str = "") -> dict[str, Any]:
        return {
            "id": f"cat_{uuid.uuid4().hex[:12]}",
            "name": _clean_text(name, 40) or "未命名词库",
            "description": _clean_text(description, 120),
            "enabled": False,
            "builtin": False,
            "words": [],
            "disabled_words": [],
            "rules": [],
        }

    @staticmethod
    def _new_rule(
        name: str,
        pattern: str,
        description: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        return {
            "id": f"rule_{uuid.uuid4().hex[:12]}",
            "name": _clean_text(name, 40) or "未命名规则",
            "pattern": pattern[:MAX_PATTERN_LENGTH],
            "description": _clean_text(description, 120),
            "enabled": bool(enabled),
        }

    @staticmethod
    def _normalize_category(raw: dict[str, Any]) -> dict[str, Any]:
        words = _clean_words(raw.get("words") or raw.get("keywords") or [])
        rules: list[dict[str, Any]] = []
        for item in raw.get("rules") or []:
            if not isinstance(item, dict):
                continue
            pattern = str(item.get("pattern") or "").strip()
            if not pattern or len(pattern) > MAX_PATTERN_LENGTH or not _valid_pattern(pattern):
                continue
            rule = LexiconStore._new_rule(
                str(item.get("name") or "正则规则"),
                pattern,
                str(item.get("description") or ""),
                bool(item.get("enabled", True)),
            )
            if item.get("id"):
                rule["id"] = str(item["id"])
            rules.append(rule)
        # 兼容旧版词库：regex 列表直接转成正则规则。
        for pattern in _clean_patterns(raw.get("regex") or []):
            if len(pattern) <= MAX_PATTERN_LENGTH and _valid_pattern(pattern):
                rules.append(LexiconStore._new_rule("导入的正则", pattern))
        return {
            "id": str(raw.get("id") or f"cat_{uuid.uuid4().hex[:12]}"),
            "name": _clean_text(raw.get("name"), 40) or "未命名词库",
            "description": _clean_text(raw.get("description"), 120),
            "enabled": bool(raw.get("enabled", False)),
            "builtin": bool(raw.get("builtin", False)),
            "words": words,
            "disabled_words": [
                word
                for word in _clean_words(raw.get("disabled_words") or [])
                if word in words
            ],
            "rules": rules[:MAX_RULES],
        }

    def _load_state(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        categories: list[dict[str, Any]] = []
        needs_save = False
        if isinstance(raw, dict) and isinstance(raw.get("categories"), list):
            for item in raw["categories"]:
                if isinstance(item, dict):
                    categories.append(self._normalize_category(item))
        elif isinstance(raw, dict):
            # 旧版本只有 custom/enabled；保留用户上传的自定义词库。
            needs_save = True
            enabled = {str(item) for item in raw.get("enabled") or []}
            for item in raw.get("custom") or []:
                if not isinstance(item, dict):
                    continue
                category = self._normalize_category(item)
                category["enabled"] = str(item.get("id") or "") in enabled
                categories.append(category)
        if not categories:
            for item in DEFAULT_CATEGORIES:
                categories.append(
                    {
                        **item,
                        "enabled": False,
                        "builtin": True,
                        "words": [],
                        "disabled_words": [],
                        "rules": [],
                    }
                )
            needs_save = True
        for category in categories:
            default = DEFAULT_CATEGORY_MAP.get(
                str(category.get("id") or "")
            ) or DEFAULT_CATEGORY_NAME_MAP.get(str(category.get("name") or ""))
            if default is None:
                continue
            if not category.get("builtin") or category.get("description") != default["description"]:
                needs_save = True
            category["builtin"] = True
            category["description"] = default["description"]
        kept_categories = []
        for category in categories:
            if str(category.get("id") or "") == "cat_custom" or str(
                category.get("name") or ""
            ) == "自定义词库":
                needs_save = True
                continue
            kept_categories.append(category)
        categories = kept_categories
        existing_names = {str(item.get("name") or "") for item in categories}
        for default in DEFAULT_CATEGORIES:
            if default["name"] in existing_names:
                continue
            categories.append(
                {
                    **default,
                    "enabled": False,
                    "builtin": True,
                    "words": [],
                    "disabled_words": [],
                    "rules": [],
                }
            )
            existing_names.add(default["name"])
            needs_save = True
        self.state = {"version": 2, "categories": categories}
        seed_version = 0
        if isinstance(raw, dict):
            try:
                seed_version = int(raw.get("seed_version") or 0)
            except (TypeError, ValueError):
                seed_version = 0
        seed_changed = self._apply_builtin_seed(seed_version)
        if needs_save or seed_changed or not self.path.exists():
            self._save_state()

    def _apply_builtin_seed(self, applied_version: int) -> bool:
        """Merge bundled built-in keyword/rules once; never enable them."""
        try:
            seed = json.loads(BUILTIN_SEED_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(seed, dict):
            return False
        try:
            version = int(seed.get("seed_version") or 0)
        except (TypeError, ValueError):
            return False
        if version <= applied_version:
            return False
        by_name = {str(item.get("name") or ""): item for item in self._categories()}
        for source in seed.get("categories") or []:
            if not isinstance(source, dict):
                continue
            category = by_name.get(str(source.get("name") or ""))
            if category is None:
                continue
            words = _clean_words(category.get("words") or [])
            existing_words = set(words)
            for word in _clean_words(source.get("words") or []):
                if word not in existing_words and len(words) < MAX_WORDS:
                    words.append(word)
                    existing_words.add(word)
            category["words"] = words
            rules = self._rules_of(category)
            existing_patterns = {str(rule.get("pattern")) for rule in rules}
            for index, pattern in enumerate(source.get("rules") or [], start=1):
                pattern = str(pattern or "").strip()
                if (
                    not pattern
                    or pattern in existing_patterns
                    or len(rules) >= MAX_RULES
                    or not _valid_pattern(pattern)
                ):
                    continue
                rule = self._new_rule(f"内置规则 {index}", pattern)
                rules.append(rule)
                existing_patterns.add(pattern)
            category["rules"] = rules
        self.state["seed_version"] = version
        return True

    def _save_state(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    def _categories(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.state.get("categories", [])
            if isinstance(item, dict)
        ]

    def _category(self, category_id: str) -> dict[str, Any] | None:
        return next(
            (item for item in self._categories() if str(item.get("id")) == category_id),
            None,
        )

    @staticmethod
    def _rules_of(category: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            item
            for item in category.get("rules", [])
            if isinstance(item, dict)
        ]

    @staticmethod
    def _disabled_words(category: dict[str, Any]) -> set[str]:
        return {
            str(item)
            for item in category.get("disabled_words", [])
            if isinstance(item, str)
        }

    def _find_rule(self, rule_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        for category in self._categories():
            for rule in self._rules_of(category):
                if str(rule.get("id")) == rule_id:
                    return category, rule
        return None

    def _compiled(self, pattern: str) -> re.Pattern[str] | None:
        cached = self._regex_cache.get(pattern)
        if cached is not None:
            return cached
        try:
            compiled = re.compile(pattern)
        except re.error:
            return None
        self._regex_cache[pattern] = compiled
        return compiled

    # ---------- 对外查询 ----------

    def list_payload(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        rule_rows: list[dict[str, Any]] = []
        literal_count = 0
        regex_count = 0
        enabled_categories = 0
        for category in self._categories():
            words = _clean_words(category.get("words") or [])
            rules = self._rules_of(category)
            disabled = self._disabled_words(category)
            active_words = [word for word in words if word not in disabled]
            enabled = bool(category.get("enabled", False))
            if enabled:
                enabled_categories += 1
                literal_count += len(active_words)
                regex_count += sum(1 for rule in rules if rule.get("enabled", True))
            rows.append(
                {
                    "id": category.get("id"),
                    "name": category.get("name") or "未命名词库",
                    "description": category.get("description") or "",
                    "enabled": enabled,
                    "builtin": bool(category.get("builtin", False)),
                    "count": len(words),
                    "enabled_count": len(active_words),
                    "disabled_count": len(words) - len(active_words),
                    "literal_count": len(active_words),
                    "regex_count": len(rules),
                }
            )
            for rule in rules:
                rule_rows.append(
                    {
                        "id": rule.get("id"),
                        "name": rule.get("name") or "未命名规则",
                        "pattern": rule.get("pattern") or "",
                        "description": rule.get("description") or "",
                        "enabled": bool(rule.get("enabled", True)),
                        "category_id": category.get("id"),
                        "category_name": category.get("name") or "未命名词库",
                    }
                )
        return {
            "lexicons": rows,
            "rules": rule_rows[:200],
            "rule_total": len(rule_rows),
            "stats": {
                "lexicon_count": len(rows),
                "enabled_count": enabled_categories,
                "pattern_count": literal_count + regex_count,
                "literal_count": literal_count,
                "regex_count": regex_count,
                "chinese_count": 0,
                "custom_count": len(rows),
                "allow_count": 0,
                "error_count": 0,
            },
        }

    def toggle(self, category_id: str, enabled: bool) -> bool:
        category = self._category(category_id)
        if category is None:
            raise ValueError("词库不存在")
        category["enabled"] = bool(enabled)
        self._save_state()
        return True

    def words_payload(self, category_id: str) -> dict[str, Any]:
        category = self._category(category_id)
        if category is None:
            raise ValueError("词库不存在")
        disabled = self._disabled_words(category)
        return {
            "category": {
                "id": category.get("id"),
                "name": category.get("name"),
                "enabled": bool(category.get("enabled", False)),
            },
            "words": [
                {"text": word, "enabled": word not in disabled}
                for word in _clean_words(category.get("words") or [])
            ],
        }

    def update_words(
        self,
        category_id: str,
        action: str,
        words: list[str],
    ) -> dict[str, Any]:
        category = self._category(category_id)
        if category is None:
            raise ValueError("词库不存在")
        action = str(action or "").strip()
        values = _clean_words(words)
        current = _clean_words(category.get("words") or [])
        disabled = self._disabled_words(category)
        if action == "add":
            for word in values:
                if word not in current:
                    current.append(word)
                disabled.discard(word)
        elif action == "delete":
            remove = set(values)
            current = [word for word in current if word not in remove]
            disabled -= remove
        elif action in {"enable", "disable"}:
            select = set(values) & set(current)
            if action == "enable":
                disabled -= select
            else:
                disabled |= select
        else:
            raise ValueError("不支持的关键词操作")
        category["words"] = _clean_words(current)
        category["disabled_words"] = [
            word for word in _clean_words(sorted(disabled)) if word in category["words"]
        ]
        self._save_state()
        return self.words_payload(category_id)

    def toggle_rule(self, rule_id: str, enabled: bool) -> bool:
        found = self._find_rule(rule_id)
        if found is None:
            raise ValueError("正则规则不存在")
        _, rule = found
        rule["enabled"] = bool(enabled)
        self._save_state()
        return True

    # ---------- 编辑 ----------

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
            raise ValueError("没有解析到有效词条或正则")
        target = self._category(target_id) if mode in {"append", "merge"} else None
        if target is None:
            target = self._new_category(name or "本地上传", description or "本地上传词库")
            self.state["categories"].append(target)
        before = len(target.get("words") or []) + len(target.get("rules") or [])
        target["words"] = _clean_words(list(target.get("words") or []) + literals)
        if literals:
            disabled = self._disabled_words(target) - set(literals)
            target["disabled_words"] = sorted(disabled)
        rules = self._rules_of(target)
        existing_patterns = {str(rule.get("pattern")) for rule in rules}
        for pattern in regexes:
            if pattern in existing_patterns:
                continue
            rules.append(self._new_rule("导入的正则", pattern))
            existing_patterns.add(pattern)
            if len(rules) >= MAX_RULES:
                break
        target["rules"] = rules
        if not target.get("builtin"):
            target["enabled"] = True
        self._save_state()
        total = len(target.get("words") or []) + len(target.get("rules") or [])
        return {
            "ok": True,
            "id": target["id"],
            "name": target["name"],
            "count": total,
            "added": total - before,
        }

    def save_rule(
        self,
        *,
        rule_id: str = "",
        category_id: str = "",
        name: str = "",
        pattern: str = "",
        description: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        pattern = str(pattern or "").strip()
        if not pattern:
            raise ValueError("正则表达式不能为空")
        if len(pattern) > MAX_PATTERN_LENGTH:
            raise ValueError(f"正则表达式不能超过 {MAX_PATTERN_LENGTH} 个字符")
        if not _valid_pattern(pattern):
            raise ValueError("正则表达式格式不正确")
        found = self._find_rule(rule_id) if rule_id else None
        if found is not None:
            category, rule = found
            if category_id and category_id != category.get("id"):
                self._rules_of(category).remove(rule)
                new_category = self._category(category_id)
                if new_category is None:
                    raise ValueError("目标词库不存在")
                new_category["rules"].append(rule)
            rule["name"] = _clean_text(name, 40) or "未命名规则"
            rule["pattern"] = pattern
            rule["description"] = _clean_text(description, 120)
            rule["enabled"] = bool(enabled)
            self._save_state()
            return {"ok": True, "id": rule["id"]}
        category = self._category(category_id) or self._categories()[0]
        if category is None:
            raise ValueError("请先创建词库")
        rule = self._new_rule(name, pattern, description, enabled)
        category["rules"].append(rule)
        category["enabled"] = True
        self._save_state()
        return {"ok": True, "id": rule["id"]}

    def delete(self, category_id: str) -> bool:
        category = self._category(category_id)
        if category is not None and category.get("builtin"):
            raise ValueError("内置词库不能删除")
        before = len(self._categories())
        self.state["categories"] = [
            item for item in self._categories() if str(item.get("id")) != category_id
        ]
        self._save_state()
        return len(self.state["categories"]) != before

    def delete_rule(self, rule_id: str) -> bool:
        found = self._find_rule(rule_id)
        if found is None:
            return False
        category, rule = found
        category["rules"] = [
            item for item in self._rules_of(category) if item is not rule
        ]
        self._save_state()
        return True

    # ---------- 导出/匹配 ----------

    def export(self, category_id: str) -> str:
        category = self._category(category_id)
        if category is None:
            raise ValueError("词库不存在")
        if category.get("builtin"):
            raise ValueError("内置词库不能导出")
        return json.dumps(
            {
                "name": category.get("name"),
                "description": category.get("description"),
                "words": _clean_words(category.get("words") or []),
                "disabled_words": sorted(self._disabled_words(category)),
                "regex": [
                    str(rule.get("pattern"))
                    for rule in self._rules_of(category)
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    def match(self, text: str) -> bool:
        source = str(text or "")
        if not source:
            return False
        for category in self._categories():
            if not category.get("enabled", False):
                continue
            disabled = self._disabled_words(category)
            for word in _clean_words(category.get("words") or []):
                if word and word not in disabled and word in source:
                    return True
            for rule in self._rules_of(category):
                if not rule.get("enabled", True):
                    continue
                compiled = self._compiled(str(rule.get("pattern") or ""))
                if compiled is not None and compiled.search(source):
                    return True
        return False

    def test(self, text: str, include_disabled: bool = False) -> dict[str, Any]:
        """返回命中位置；不在界面展示命中的具体词。"""
        source = str(text or "")
        hits: list[dict[str, Any]] = []
        for category in self._categories():
            category_enabled = bool(category.get("enabled", False))
            if not include_disabled and not category_enabled:
                continue
            disabled = self._disabled_words(category)
            for word in _clean_words(category.get("words") or []):
                if not include_disabled and word in disabled:
                    continue
                start = source.find(word)
                if start >= 0:
                    hits.append(
                        {
                            "lexicon": category.get("name") or "未命名词库",
                            "kind": "literal",
                            "length": len(word),
                            "start": start,
                            "end": start + len(word),
                        }
                    )
            for rule in self._rules_of(category):
                if not include_disabled and not rule.get("enabled", True):
                    continue
                compiled = self._compiled(str(rule.get("pattern") or ""))
                if compiled is None:
                    continue
                match = compiled.search(source)
                if match:
                    hits.append(
                        {
                            "lexicon": f"{category.get('name') or '未命名词库'} / {rule.get('name') or '正则'}",
                            "kind": "regex",
                            "length": len(match.group(0)),
                            "start": match.start(),
                            "end": match.end(),
                        }
                    )
        return {"count": len(hits), "hits": hits[:100]}
