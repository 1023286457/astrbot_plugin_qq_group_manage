"""Server status sampling, history, events and daily summaries.

The original status-card plugin is OneBot-oriented.  This module keeps the
platform-independent server metrics and exposes them to the group-management
WebUI.  QQ official has no friend list, member-count or protocol APIs, so the
bot block only exposes the platform online state and the known-group count.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import platform
import shutil
import socket
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from astrbot.api import logger

PLUGIN_NAME = "astrbot_plugin_qq_group_manage"

try:
    import psutil
except Exception:  # pragma: no cover - reported in the UI
    psutil = None  # type: ignore[assignment]

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "sample_seconds": 30,
    "history_days": 7,
    "glass_opacity": 75,
    "glass_blur": 12,
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
_IMAGE_MIME = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg"}
_SAMPLE_LIMIT = 20000
_EVENT_LIMIT = 500
_EVENT_COOLDOWN = 300.0


def _bytes_text(value: float | int | None) -> str:
    if value is None:
        return "--"
    number = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while number >= 1024 and index < len(units) - 1:
        number /= 1024
        index += 1
    return f"{number:.1f} {units[index]}"


def _duration_text(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--"
    total = int(seconds)
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}天 {hours}小时"
    if hours:
        return f"{hours}小时 {minutes}分"
    return f"{minutes}分钟"


def _iso(timestamp: float | None = None) -> str:
    return datetime.fromtimestamp(timestamp or time.time()).astimezone().isoformat(
        timespec="seconds"
    )


class ServerStatusService:
    def __init__(self, data_dir: Path, plugin: Any) -> None:
        self.data_dir = Path(data_dir)
        self.plugin = plugin
        self.path = self.data_dir / "server-status.json"
        self.image_dir = self.data_dir / "server-status-image"
        self.image_meta_path = self.image_dir / "metadata.json"
        self.samples: deque[dict[str, Any]] = deque(maxlen=_SAMPLE_LIMIT)
        self.events: deque[dict[str, Any]] = deque(maxlen=_EVENT_LIMIT)
        self.config: dict[str, Any] = dict(DEFAULT_CONFIG)
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._last_net: tuple[float, int, int] | None = None
        self._last_event: dict[str, float] = {}
        self._last_sample_ts = 0.0
        self._load()
        if psutil is not None:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception:
            logger.warning("[%s] 服务器状态历史文件损坏，已忽略", PLUGIN_NAME)
            return
        if not isinstance(raw, dict):
            return
        config = raw.get("config")
        if isinstance(config, dict):
            self.config.update(
                {key: config[key] for key in DEFAULT_CONFIG if key in config}
            )
        samples = raw.get("samples")
        if isinstance(samples, list):
            self.samples.extend(
                item for item in samples if isinstance(item, dict)
            )
        events = raw.get("events")
        if isinstance(events, list):
            self.events.extend(item for item in events if isinstance(item, dict))

    def _save(self) -> None:
        payload = {
            "config": self.config,
            "samples": list(self.samples),
            "events": list(self.events),
        }
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except Exception:
            logger.exception("[%s] 保存服务器状态历史失败", PLUGIN_NAME)

    # ------------------------------------------------------------------
    # config
    # ------------------------------------------------------------------
    def get_config(self) -> dict[str, Any]:
        self._sync_from_plugin()
        return dict(self.config)

    def _sync_from_plugin(self) -> None:
        """Keep the page switches aligned with the native plugin config."""
        try:
            section = self.plugin.config.get("server_status_settings")
        except Exception:
            section = None
        if not isinstance(section, dict):
            return
        mapping = {
            "enable_server_status": "enabled",
            "server_sample_seconds": "sample_seconds",
            "server_glass_opacity": "glass_opacity",
            "server_glass_blur": "glass_blur",
        }
        for source, target in mapping.items():
            if source in section:
                self.config[target] = section[source]

    def _save_plugin_config(self) -> None:
        try:
            section = self.plugin.config.get("server_status_settings")
            if not isinstance(section, dict):
                section = {}
                self.plugin.config["server_status_settings"] = section
            section.update(
                {
                    "enable_server_status": bool(self.config["enabled"]),
                    "server_sample_seconds": int(self.config["sample_seconds"]),
                    "server_glass_opacity": int(self.config["glass_opacity"]),
                    "server_glass_blur": int(self.config["glass_blur"]),
                }
            )
            save = getattr(self.plugin.config, "save_config", None)
            if callable(save):
                save()
        except Exception:
            logger.warning("[%s] 同步服务器状态到插件配置失败", PLUGIN_NAME)

    def _int_config(self, key: str, low: int, high: int) -> int:
        try:
            value = int(self.config.get(key, DEFAULT_CONFIG[key]))
        except (TypeError, ValueError):
            value = int(DEFAULT_CONFIG[key])
        return max(low, min(high, value))

    def save_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        if "enabled" in updates:
            self.config["enabled"] = bool(updates["enabled"])
        for key in ("sample_seconds", "glass_opacity", "glass_blur"):
            if key in updates:
                try:
                    self.config[key] = int(updates[key])
                except (TypeError, ValueError):
                    raise ValueError(f"{key} 必须是整数")
        self.config["sample_seconds"] = self._int_config("sample_seconds", 15, 300)
        self.config["glass_opacity"] = self._int_config("glass_opacity", 20, 100)
        self.config["glass_blur"] = self._int_config("glass_blur", 0, 30)
        self._save()
        self._save_plugin_config()
        return self.get_config()

    # ------------------------------------------------------------------
    # sampling
    # ------------------------------------------------------------------
    def _known_groups(self) -> int:
        try:
            seen = self.plugin.storage.data.get("seen_groups", {})
            profiles = (
                self.plugin.config.get("group_management", {})
                .get("groups", [])
            )
            umos = set(seen) if isinstance(seen, dict) else set()
            for item in profiles if isinstance(profiles, list) else []:
                if isinstance(item, dict) and item.get("umo"):
                    umos.add(str(item["umo"]))
            return len(umos)
        except Exception:
            return 0

    def _platform_state(self) -> tuple[bool, int]:
        try:
            platforms = self.plugin.dashboard._platforms()
        except Exception:
            platforms = []
        return any(bool(item.get("online")) for item in platforms), len(platforms)

    def _record_event(
        self, kind: str, level: str, message: str, value: Any = None
    ) -> None:
        now = time.time()
        if now - self._last_event.get(kind, 0) < _EVENT_COOLDOWN:
            return
        self._last_event[kind] = now
        self.events.appendleft(
            {
                "ts": now,
                "time": _iso(now),
                "kind": kind,
                "level": level,
                "message": message,
                "value": value,
            }
        )

    def _sample(self) -> dict[str, Any] | None:
        if psutil is None or not self.config.get("enabled", True):
            return None
        now = time.time()
        try:
            cpu = float(psutil.cpu_percent(interval=None) or 0.0)
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disk_path = self.data_dir.anchor or os.sep
            disk = psutil.disk_usage(disk_path)
            net = psutil.net_io_counters()
            boot = psutil.boot_time()
            processes = self._processes()
        except Exception:
            logger.exception("[%s] 采集服务器状态失败", PLUGIN_NAME)
            return None
        up_speed = down_speed = 0.0
        if self._last_net is not None:
            elapsed = max(0.001, now - self._last_net[0])
            up_speed = max(0.0, (net.bytes_sent - self._last_net[1]) / elapsed)
            down_speed = max(0.0, (net.bytes_recv - self._last_net[2]) / elapsed)
        self._last_net = (now, net.bytes_sent, net.bytes_recv)
        online, platform_count = self._platform_state()
        item = {
            "ts": now,
            "time": _iso(now),
            "cpu": round(cpu, 1),
            "memory": round(float(memory.percent), 1),
            "memory_used": int(memory.used),
            "memory_total": int(memory.total),
            "swap": round(float(swap.percent), 1),
            "disk": round(float(disk.percent), 1),
            "disk_used": int(disk.used),
            "disk_total": int(disk.total),
            "net_up": round(up_speed, 1),
            "net_down": round(down_speed, 1),
            "bot_online": online,
            "platform_count": platform_count,
            "processes": processes,
        }
        self.samples.append(item)
        self._last_sample_ts = now
        self._save()
        return item

    def _processes(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
                try:
                    info = proc.info
                    memory = info.get("memory_info")
                    rows.append(
                        {
                            "pid": int(info.get("pid") or 0),
                            "name": str(info.get("name") or "unknown")[:80],
                            "cpu": round(float(info.get("cpu_percent") or 0.0), 1),
                            "memory": int(getattr(memory, "rss", 0) or 0),
                        }
                    )
                except Exception:
                    continue
        except Exception:
            return []
        rows.sort(key=lambda row: (row["cpu"], row["memory"]), reverse=True)
        return rows[:6]

    def _collect_live(self) -> dict[str, Any]:
        now = time.time()
        if psutil is None:
            return {
                "ok": False,
                "error": "psutil 不可用，请安装 requirements.txt 中的 psutil",
                "config": self.get_config(),
                "ts": _iso(now),
            }
        try:
            cpu = float(psutil.cpu_percent(interval=None) or 0.0)
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disk = psutil.disk_usage(self.data_dir.anchor or os.sep)
            net = psutil.net_io_counters()
            boot = psutil.boot_time()
            processes = self._processes()
        except Exception as exc:
            return {
                "ok": False,
                "error": f"采集服务器状态失败：{exc}",
                "config": self.get_config(),
                "ts": _iso(now),
            }
        up_speed = down_speed = 0.0
        if self._last_net is not None:
            elapsed = max(0.001, now - self._last_net[0])
            up_speed = max(0.0, (net.bytes_sent - self._last_net[1]) / elapsed)
            down_speed = max(0.0, (net.bytes_recv - self._last_net[2]) / elapsed)
        self._last_net = (now, net.bytes_sent, net.bytes_recv)
        online, platform_count = self._platform_state()
        try:
            load1 = float(psutil.getloadavg()[0])
        except (AttributeError, OSError):
            try:
                logical = psutil.cpu_count(logical=True) or 1
                load1 = round(cpu / 100 * logical, 2)
            except Exception:
                load1 = None
        return {
            "ok": True,
            "ts": _iso(now),
            "timestamp": now,
            "enabled": bool(self.config.get("enabled", True)),
            "sample_seconds": self._int_config("sample_seconds", 15, 300),
            "bot": {
                "online": online,
                "platforms": platform_count,
            },
            "known_groups": self._known_groups(),
            "cpu": round(cpu, 1),
            "memory": {
                "percent": round(float(memory.percent), 1),
                "used": int(memory.used),
                "total": int(memory.total),
                "text": f"{_bytes_text(memory.used)} / {_bytes_text(memory.total)}",
            },
            "swap": {
                "percent": round(float(swap.percent), 1),
                "used": int(swap.used),
                "total": int(swap.total),
            },
            "disk": {
                "percent": round(float(disk.percent), 1),
                "used": int(disk.used),
                "total": int(disk.total),
                "text": f"{_bytes_text(disk.used)} / {_bytes_text(disk.total)}",
                "path": self.data_dir.anchor or os.sep,
            },
            "network": {
                "up": round(up_speed, 1),
                "down": round(down_speed, 1),
                "up_text": f"{_bytes_text(up_speed)}/s",
                "down_text": f"{_bytes_text(down_speed)}/s",
                "total_sent": int(net.bytes_sent),
                "total_recv": int(net.bytes_recv),
            },
            "system": {
                "hostname": socket.gethostname(),
                "platform": f"{platform.system()} {platform.release()}",
                "uptime": _duration_text(now - boot),
                "processes": len(psutil.pids()),
                "load1": load1,
            },
            "processes": [
                {
                    **row,
                    "memory_text": _bytes_text(row["memory"]),
                }
                for row in processes
            ],
            "history": [
                {
                    "ts": item.get("ts"),
                    "time": item.get("time"),
                    "cpu": item.get("cpu"),
                    "memory": item.get("memory"),
                }
                for item in list(self.samples)[-60:]
            ],
            "recent_events": list(self.events)[:5],
            "config": self.get_config(),
        }

    def overview(self) -> dict[str, Any]:
        data = self._collect_live()
        data["image"] = self.image_info()
        return data

    # ------------------------------------------------------------------
    # history / events / reports
    # ------------------------------------------------------------------
    def history(self, range_key: str = "24h") -> dict[str, Any]:
        seconds = {"24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}.get(
            range_key, 86400
        )
        cutoff = time.time() - seconds
        rows = [item for item in self.samples if float(item.get("ts") or 0) >= cutoff]
        return {
            "range": range_key if range_key in {"24h", "7d", "30d"} else "24h",
            "points": rows,
            "sample_seconds": self._int_config("sample_seconds", 15, 300),
        }

    def events(self, days: int = 1) -> dict[str, Any]:
        days = max(1, min(30, int(days)))
        cutoff = time.time() - days * 86400
        rows = [
            item
            for item in self.events
            if float(item.get("ts") or 0) >= cutoff
        ]
        return {"days": days, "items": rows[:200]}

    def reports(self, days: int = 14) -> dict[str, Any]:
        days = max(1, min(60, int(days)))
        today = datetime.now().astimezone().date()
        start = today - timedelta(days=days - 1)
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in self.samples:
            try:
                day = datetime.fromtimestamp(float(item["ts"])).astimezone().date()
            except Exception:
                continue
            if day < start:
                continue
            groups.setdefault(day.isoformat(), []).append(item)
        event_counts: dict[str, int] = {}
        for event in self.events:
            try:
                day = datetime.fromtimestamp(float(event["ts"])).astimezone().date()
            except Exception:
                continue
            key = day.isoformat()
            event_counts[key] = event_counts.get(key, 0) + 1
        rows: list[dict[str, Any]] = []
        for key in sorted(groups, reverse=True):
            values = groups[key]
            rows.append(
                {
                    "date": key,
                    "samples": len(values),
                    "cpu_avg": round(
                        sum(float(item.get("cpu") or 0) for item in values)
                        / len(values),
                        1,
                    ),
                    "cpu_max": round(
                        max(float(item.get("cpu") or 0) for item in values), 1
                    ),
                    "memory_avg": round(
                        sum(float(item.get("memory") or 0) for item in values)
                        / len(values),
                        1,
                    ),
                    "memory_max": round(
                        max(float(item.get("memory") or 0) for item in values), 1
                    ),
                    "events": event_counts.get(key, 0),
                }
            )
        return {"days": days, "items": rows}

    # ------------------------------------------------------------------
    # uploaded status image
    # ------------------------------------------------------------------
    def image_info(self) -> dict[str, Any]:
        meta = self._image_meta()
        path = self.image_dir / str(meta.get("file") or "")
        if not meta or not path.is_file():
            return {"exists": False}
        return {
            "exists": True,
            "name": str(meta.get("name") or path.name),
            "mime": str(meta.get("mime") or "image/png"),
            "size": path.stat().st_size,
        }

    def _image_meta(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.image_meta_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    def image_preview(self) -> str:
        meta = self._image_meta()
        path = self.image_dir / str(meta.get("file") or "")
        if not meta or not path.is_file():
            return ""
        try:
            raw = path.read_bytes()
            return f"data:{meta.get('mime') or 'image/png'};base64,{base64.b64encode(raw).decode('ascii')}"
        except Exception:
            return ""

    def save_image(self, name: str, mime: str, raw: bytes) -> dict[str, Any]:
        mime = str(mime or "").strip().lower()
        if mime == "image/jpg":
            mime = "image/jpeg"
        if mime not in _IMAGE_MIME:
            raise ValueError("只支持 PNG 或 JPG 图片")
        if not raw:
            raise ValueError("图片内容为空")
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("图片不能超过 5MB")
        self.image_dir.mkdir(parents=True, exist_ok=True)
        filename = f"status-{uuid4().hex[:12]}{_IMAGE_MIME[mime]}"
        path = self.image_dir / filename
        path.write_bytes(raw)
        old = self._image_meta()
        if old.get("file") and old.get("file") != filename:
            try:
                (self.image_dir / str(old["file"])).unlink()
            except OSError:
                pass
        self.image_meta_path.write_text(
            json.dumps(
                {"file": filename, "name": str(name or filename)[:160], "mime": mime},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return self.image_info()

    def delete_image(self) -> bool:
        meta = self._image_meta()
        changed = False
        if meta.get("file"):
            try:
                (self.image_dir / str(meta["file"])).unlink()
                changed = True
            except OSError:
                pass
        try:
            self.image_meta_path.unlink()
            changed = True
        except OSError:
            pass
        return changed

    # ------------------------------------------------------------------
    # status card
    # ------------------------------------------------------------------
    def render_card(self) -> bytes:
        """Render a compact PNG card without relying on T2I/OneBot."""
        try:
            from io import BytesIO
            from PIL import Image, ImageDraw, ImageFilter, ImageFont
        except Exception:
            return b""
        data = self._collect_live()
        if not data.get("ok"):
            return b""
        width, height = 900, 760
        image = Image.new("RGB", (width, height), "#101522")
        draw = ImageDraw.Draw(image)
        # Uploaded background, if any.
        meta = self._image_meta()
        bg_path = self.image_dir / str(meta.get("file") or "")
        if meta and bg_path.is_file():
            try:
                with Image.open(bg_path) as raw_bg:
                    bg = raw_bg.convert("RGB")
                    ratio = max(width / bg.width, height / bg.height)
                    bg = bg.resize(
                        (max(1, int(bg.width * ratio)), max(1, int(bg.height * ratio))),
                        Image.Resampling.LANCZOS,
                    )
                    left = max(0, (bg.width - width) // 2)
                    top = max(0, (bg.height - height) // 2)
                    image = bg.crop((left, top, left + width, top + height))
                    overlay = Image.new("RGBA", (width, height), (8, 12, 22, 150))
                    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
                    draw = ImageDraw.Draw(image)
            except Exception:
                logger.debug("[%s] 状态卡背景读取失败，使用默认背景", PLUGIN_NAME)
        else:
            for y in range(height):
                shade = 18 + int(18 * y / height)
                draw.line((0, y, width, y), fill=(shade, shade + 5, shade + 16))

        def font(size: int, bold: bool = False):
            candidates = (
                r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
                r"C:\Windows\Fonts\simhei.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                if bold
                else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            )
            for path in candidates:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        accent = (124, 109, 252)
        green = (34, 197, 139)
        muted = (154, 164, 188)
        white = (244, 247, 255)
        glass_opacity = max(20, min(100, int(self.config.get("glass_opacity", 75)))) / 100
        glass_blur = max(0, min(30, int(self.config.get("glass_blur", 12))))

        def glass_panel(box, radius: int) -> None:
            """Blur the background behind a card and tint it like frosted glass."""
            nonlocal draw
            x0, y0, x1, y1 = [int(value) for value in box]
            panel_w, panel_h = max(1, x1 - x0), max(1, y1 - y0)
            region = image.crop((x0, y0, x1, y1)).convert("RGBA")
            if glass_blur:
                region = region.filter(ImageFilter.GaussianBlur(glass_blur))
            tint = Image.new(
                "RGBA", (panel_w, panel_h), (16, 23, 39, int(255 * glass_opacity))
            )
            region = Image.alpha_composite(region, tint)
            mask = Image.new("L", (panel_w, panel_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, panel_w - 1, panel_h - 1), radius, fill=255
            )
            image.paste(region.convert("RGB"), (x0, y0), mask)
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle(
                box, radius, outline=(112, 124, 150), width=1
            )

        glass_panel((38, 32, width - 38, 118), 18)
        draw.text((62, 49), "服务器运行状态", font=font(30, True), fill=white)
        draw.text((64, 88), "QQ 官方平台 · Bot服务器实时状态", font=font(15), fill=muted)
        online = bool(data.get("bot", {}).get("online"))
        draw.ellipse((width - 176, 62, width - 162, 76), fill=green if online else (239, 107, 115))
        draw.text((width - 152, 58), "官方平台在线" if online else "官方平台离线", font=font(14), fill=white)

        memory = data.get("memory", {})
        disk = data.get("disk", {})
        system = data.get("system", {})
        network = data.get("network", {})
        cards = [
            ("CPU", f"{float(data.get('cpu', 0)):.1f}%", accent),
            ("内存", f"{float(memory.get('percent', 0)):.1f}%", green),
            ("磁盘", f"{float(disk.get('percent', 0)):.1f}%", (240, 179, 91)),
            ("网络", "", (91, 180, 240)),
        ]
        card_y = 142
        card_w = (width - 76 - 3 * 12) // 4
        for index, (label, value, color) in enumerate(cards):
            x = 38 + index * (card_w + 12)
            glass_panel((x, card_y, x + card_w, card_y + 112), 14)
            draw.text((x + 16, card_y + 15), label, font=font(13), fill=muted)
            if label == "网络":
                draw.text((x + 16, card_y + 40), "上行", font=font(11), fill=muted)
                draw.text(
                    (x + 66, card_y + 37),
                    str(network.get("up_text") or "--"),
                    font=font(14, True),
                    fill=color,
                )
                draw.text((x + 16, card_y + 68), "下行", font=font(11), fill=muted)
                draw.text(
                    (x + 66, card_y + 65),
                    str(network.get("down_text") or "--"),
                    font=font(14, True),
                    fill=color,
                )
            else:
                draw.text((x + 16, card_y + 42), value, font=font(25, True), fill=color)

        bars = [
            ("CPU", float(data.get("cpu", 0)), accent),
            ("内存", float(memory.get("percent", 0)), green),
            ("磁盘", float(disk.get("percent", 0)), (240, 179, 91)),
        ]
        bar_y = 282
        for label, value, color in bars:
            draw.text((40, bar_y), label, font=font(14), fill=muted)
            draw.rounded_rectangle((100, bar_y + 2, width - 48, bar_y + 12), 5, fill=(40, 48, 67))
            draw.rounded_rectangle(
                (100, bar_y + 2, 100 + int((width - 148) * max(0, min(100, value)) / 100), bar_y + 12),
                5,
                fill=color,
            )
            bar_y += 35

        glass_panel((38, 410, width - 38, 652), 16)
        draw.text((62, 430), "系统信息", font=font(17, True), fill=white)
        info = [
            ("主机", str(system.get("hostname") or "--")),
            ("系统", str(system.get("platform") or "--")),
            ("运行时长", str(system.get("uptime") or "--")),
            ("进程数", str(system.get("processes", "--"))),
            ("已知群聊", str(data.get("known_groups", 0))),
            ("采样间隔", f"{data.get('sample_seconds', 30)} 秒"),
        ]
        for index, (label, value) in enumerate(info):
            col = index % 2
            row = index // 2
            x = 62 + col * 405
            y = 468 + row * 52
            draw.text((x, y), label, font=font(12), fill=muted)
            draw.text((x, y + 18), value, font=font(15), fill=white)
        draw.line((38, 682, width - 38, 682), fill=(48, 56, 78), width=1)
        draw.text((40, 700), "由 QQ官机群管 · 服务器运行状态生成", font=font(12), fill=muted)
        draw.text(
            (width - 270, 700),
            datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            font=font(12),
            fill=muted,
        )
        draw.text(
            (40, 724),
            "插件作者：简单么么熊 · QQ：1023286457",
            font=font(12),
            fill=muted,
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        try:
            await asyncio.to_thread(self._sample)
        except Exception:
            logger.exception("[%s] 服务器状态首次采样失败", PLUGIN_NAME)
        self._task = asyncio.create_task(self._loop(), name="qq-group-server-status")

    async def _loop(self) -> None:
        while not self._stopping:
            interval = self._int_config("sample_seconds", 15, 300)
            await asyncio.sleep(max(15, interval))
            if self._stopping:
                break
            try:
                await asyncio.to_thread(self._sample)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("[%s] 服务器状态采样失败", PLUGIN_NAME)

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
