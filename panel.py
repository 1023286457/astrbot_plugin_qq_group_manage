"""QQ 群管面板的按钮、图片存储和回调数据契约。"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any

PANEL_IMAGE_KEYS = {
    "features": "功能列表",
    "guide": "使用指南",
    "help": "获取帮助",
}
PANEL_BUTTON_RE = re.compile(
    r"^qqpanel:(features|guide|help|manage|audit|verify|noop)(?::(on|off))?$"
)
PANEL_IMAGE_MAX_BYTES = 5 * 1024 * 1024
_MIME_SUFFIX = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg"}


def _button(
    label: str,
    data: str,
    *,
    admin_only: bool = False,
    label_like: bool = False,
) -> dict[str, Any]:
    action: dict[str, Any] = {
        "type": 1,
        "data": data,
        "unsupport_tips": "请更新 QQ 客户端后点击按钮",
    }
    if admin_only:
        action["permission"] = {"type": 1}
    else:
        action["permission"] = {"type": 2}
    safe_label = re.sub(r"[^0-9A-Za-z_-]+", "-", label).strip("-")
    if not safe_label:
        safe_label = hashlib.sha1(label.encode("utf-8")).hexdigest()[:8]
    return {
        "id": f"qqpanel-{safe_label}-{data.replace(':', '-')}",
        "render_data": {
            "label": label,
            "visited_label": label,
            "style": 0 if label_like else 1,
        },
        "action": action,
    }


def main_keyboard() -> dict[str, Any]:
    return {
        "content": {
            "rows": [
                {
                    "buttons": [
                        _button("功能列表", "qqpanel:features"),
                        _button("群管面板", "qqpanel:manage", admin_only=True),
                    ]
                },
                {
                    "buttons": [
                        _button("使用指南", "qqpanel:guide"),
                        _button("获取帮助", "qqpanel:help"),
                    ]
                },
            ]
        }
    }


def manage_keyboard(group_openid: str) -> dict[str, Any]:
    return {
        "content": {
            "rows": [
                {
                    "buttons": [
                        _button("入群审核申请", "qqpanel:noop", label_like=True),
                    ]
                },
                {
                    "buttons": [
                        _button("开", "qqpanel:audit:on", admin_only=True),
                        _button("关", "qqpanel:audit:off", admin_only=True),
                    ]
                },
                {
                    "buttons": [
                        _button("入群人机验证", "qqpanel:noop", label_like=True),
                    ]
                },
                {
                    "buttons": [
                        _button("开", "qqpanel:verify:on", admin_only=True),
                        _button("关", "qqpanel:verify:off", admin_only=True),
                    ]
                },
            ]
        }
    }


def toggle_keyboard(action: str) -> dict[str, Any]:
    return {
        "content": {
            "rows": [
                {
                    "buttons": [
                        _button("开", f"qqpanel:{action}:on", admin_only=True),
                        _button("关", f"qqpanel:{action}:off", admin_only=True),
                    ]
                }
            ]
        }
    }


def parse_button(data: str) -> re.Match[str] | None:
    return PANEL_BUTTON_RE.fullmatch(str(data or ""))


def image_dir(storage: Any) -> Path:
    return Path(storage.path).parent / "panel-images"


def _meta_path(storage: Any) -> Path:
    return image_dir(storage) / "metadata.json"


def image_meta(storage: Any) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(_meta_path(storage).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_image(
    storage: Any,
    key: str,
    raw: bytes,
    mime: str,
    name: str,
) -> dict[str, Any]:
    if key not in PANEL_IMAGE_KEYS:
        raise ValueError("不支持的图片类型")
    mime = str(mime or "").strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in _MIME_SUFFIX:
        raise ValueError("只支持 PNG 或 JPG 图片")
    if not raw:
        raise ValueError("图片内容为空")
    if len(raw) > PANEL_IMAGE_MAX_BYTES:
        raise ValueError("图片不能超过 5MB")
    directory = image_dir(storage)
    directory.mkdir(parents=True, exist_ok=True)
    suffix = _MIME_SUFFIX[mime]
    path = directory / f"{key}{suffix}"
    for old in directory.glob(f"{key}.*"):
        if old.suffix in {".png", ".jpg", ".jpeg"} and old != path:
            old.unlink(missing_ok=True)
    path.write_bytes(raw)
    meta = image_meta(storage)
    meta[key] = {
        "name": str(name or f"{key}{suffix}")[:160],
        "mime": mime,
        "size": len(raw),
        "file": path.name,
    }
    _meta_path(storage).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta[key]


def load_image(storage: Any, key: str) -> tuple[bytes, str, str] | None:
    meta = image_meta(storage).get(key)
    if not isinstance(meta, dict):
        return None
    path = image_dir(storage) / str(meta.get("file") or "")
    if not path.is_file():
        return None
    mime = str(meta.get("mime") or "image/png")
    name = str(meta.get("name") or path.name)
    return path.read_bytes(), mime, name


def delete_image(storage: Any, key: str) -> bool:
    meta = image_meta(storage)
    item = meta.pop(key, None)
    if not isinstance(item, dict):
        return False
    path = image_dir(storage) / str(item.get("file") or "")
    path.unlink(missing_ok=True)
    _meta_path(storage).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


def image_data_url(storage: Any, key: str) -> str:
    loaded = load_image(storage, key)
    if loaded is None:
        return ""
    raw, mime, _ = loaded
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
