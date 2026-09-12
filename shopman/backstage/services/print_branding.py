"""Marca de impressão monocromática; arquivo do deployment, sem buscar URL externa."""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


def logo_bytes(*, centered: bool = True) -> bytes:
    """Raster GS v 0, limitado a 24 x 8 mm no cabeçote de 203 dpi.

    PNG dedicado evita tentar imprimir branco/dourado do logo de tela. Sem
    configuração ou arquivo legível, o compositor mantém o nome em texto.
    """
    path = str(getattr(settings, "SHOPMAN_PRINT_LOGO_PATH", "") or "")
    if not path:
        return b""
    try:
        with Image.open(Path(path)) as original:
            original.thumbnail((192, 64))
            rgba = original.convert("RGBA")
            image = Image.new("RGBA", rgba.size, "white")
            image.alpha_composite(rgba)
            gray = image.convert("L")
            # Pixels escuros são 1 no protocolo, oposto do modo 1 do Pillow.
            ink = ImageOps.invert(gray).point(lambda pixel: 255 if pixel > 127 else 0, mode="1")
            width_bytes = (ink.width + 7) // 8
            data = ink.tobytes()
            return (
                bytes([0x1B, ord("a"), int(centered)])
                + b"\x1dv0\x00"
                + width_bytes.to_bytes(2, "little")
                + ink.height.to_bytes(2, "little")
                + data
                + b"\x1ba\x00"
            )
    except (OSError, ValueError):
        logger.warning("print_logo_unavailable")
        return b""
