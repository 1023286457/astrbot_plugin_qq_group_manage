"""二维码图片识别，依赖可选的 zxing-cpp 与 Pillow。"""

from __future__ import annotations

import asyncio
import importlib
import logging
from typing import Any

logger = logging.getLogger("astrbot")

_DECODER: tuple[Any, Any] | None = None
_IMPORT_ERROR: Exception | None = None
_INSTALL_LOCK = asyncio.Lock()
_INSTALL_ATTEMPTED = False

REQUIREMENT = "zxing-cpp>=2.2.0"


def _load_decoder() -> tuple[Any, Any] | None:
    """Import the decoder once and cache the result (including failures)."""
    global _DECODER, _IMPORT_ERROR
    if _DECODER is not None or _IMPORT_ERROR is not None:
        return _DECODER
    try:
        import zxingcpp
        from PIL import Image
    except Exception as exc:  # pragma: no cover - depends on host environment
        _IMPORT_ERROR = exc
        logger.warning("[QQ官机群管] 二维码识别依赖不可用：%s", exc)
        return None
    _DECODER = (zxingcpp, Image)
    return _DECODER


def decoder_available() -> bool:
    return _load_decoder() is not None


async def ensure_decoder(timeout: float = 180.0) -> bool:
    """Auto-install zxing-cpp when missing, then import it again."""
    global _IMPORT_ERROR, _INSTALL_ATTEMPTED
    if _load_decoder() is not None:
        return True
    async with _INSTALL_LOCK:
        if _load_decoder() is not None:
            return True
        try:
            from astrbot.core import pip_installer
        except Exception:
            pip_installer = None
        if pip_installer is None:
            _INSTALL_ATTEMPTED = True
            return False
        logger.info("[QQ官机群管] 正在自动安装二维码识别依赖 %s ...", REQUIREMENT)
        try:
            await asyncio.wait_for(
                pip_installer.install(REQUIREMENT), timeout=timeout
            )
        except Exception as exc:
            logger.warning("[QQ官机群管] 二维码识别依赖自动安装失败：%s", exc)
        finally:
            _INSTALL_ATTEMPTED = True
            _IMPORT_ERROR = None
            importlib.invalidate_caches()
        return _load_decoder() is not None


def is_qr_code(path: str) -> bool:
    """Return True when the image at ``path`` contains a QR code."""
    decoder = _load_decoder()
    if decoder is None:
        return False
    zxingcpp, image_module = decoder
    try:
        with image_module.open(path) as image:
            image.load()
            try:
                results = zxingcpp.read_barcodes(
                    image, formats=zxingcpp.BarcodeFormat.QRCode
                )
            except (TypeError, AttributeError):
                results = zxingcpp.read_barcodes(image)
    except Exception:
        return False
    for result in results or []:
        fmt = str(getattr(result, "format", "")).upper()
        if "QR" in fmt:
            return True
    return False
