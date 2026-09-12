"""Composição proporcional em pontos nativos: bobina 80 mm / cabeça 576 dots.

Os mesmos compositores e dados alimentam os dois modos. Este backend mede texto
com a fonte distribuída no projeto; não depende de browser, SO ou fontes remotas.
"""

from functools import lru_cache
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parents[1] / "assets/print/NotoSans.ttf"
WIDTH = 576


@lru_cache(maxsize=32)
def font(size, bold=False):
    result = ImageFont.truetype(str(FONT), size)
    result.set_variation_by_axes([700 if bold else 500, 100])
    return result


def raster_bytes(image):
    """Faixas de 128 linhas, sem reescala, dithering ou avanço entre faixas."""
    image = image.convert("L").point(lambda p: 255 if p >= 160 else 0, mode="1")
    if image.width != WIDTH:
        raise ValueError("Raster exige largura de 576 pontos.")
    out = bytearray(b"\x1b@\x1ba\x00")
    for y in range(0, image.height, 128):
        strip = image.crop((0, y, WIDTH, min(y + 128, image.height)))
        out += b"\x1dv0\x00" + (WIDTH // 8).to_bytes(2, "little") + strip.height.to_bytes(2, "little")
        out += bytes(value ^ 255 for value in strip.tobytes())
    out += b"\x1bd\x04\x1dV\x01"
    return bytes(out)


class RasterLayout:
    def __init__(self, *, fiscal=False):
        self.fiscal = fiscal
        self.blocks = []
        self.texts = []

    def space(self, height=10):
        self.blocks.append(Image.new("L", (WIDTH, height), 255))
        return b""

    def wrap(self, text, width):
        # O compositor nativo informa colunas; aqui a quebra é por pixels na linha.
        return [str(text)]

    def _lines(self, text, face, width):
        result, line = [], ""
        for word in str(text).split():
            if line and face.getlength(line + " " + word) > width:
                result.append(line)
                line = ""
            for char in word:
                if face.getlength(line + char) > width:
                    result.append(line)
                    line = ""
                line += char
            line += " "
        if line.strip():
            result.append(line.strip())
        return result or [""]

    def text(self, text, *, size=24, bold=False, center=False, right="", inset=0):
        text, right = str(text), str(right)
        self.texts.append((text, right))
        face = font(size, bold)
        available = WIDTH - 2 * inset
        right_width = face.getlength(right)
        if right and right_width > available * 0.48:
            self.text(text, size=size, bold=bold, inset=inset)
            return self.text(right, size=size, bold=bold, inset=inset)
        lines = self._lines(text, face, available - right_width - (16 if right else 0))
        line_height = size + 5
        block = Image.new("L", (WIDTH, len(lines) * line_height + 4), 255)
        draw = ImageDraw.Draw(block)
        for index, line in enumerate(lines):
            x = (WIDTH - face.getlength(line)) / 2 if center else inset
            draw.text((round(x), index * line_height + 2), line, font=face, fill=0, anchor="lt")
        if right:
            draw.text((round(WIDTH - inset - right_width), 2), right, font=face, fill=0, anchor="lt")
        self.blocks.append(block)
        return b""

    def line(self, text):
        if not text:
            return self.space(9)
        small = str(text).startswith(("Pedido registrado", "Este papel", "e não comprova"))
        return self.text(text, size=20 if small else 22 if self.fiscal else 24)

    def pair(self, left, right, columns=48):
        return self.text(left, right=right, size=22 if self.fiscal else 24)

    def centered(self, text, columns=48):
        if text == "DANFE NFC-e":
            self.space(8)
            return self.text(text, size=30, bold=True, center=True)
        return self.text(text, size=22, center=True)

    def header(self, ref, commitment, name, phone, shop_name, reprint):
        if self.logo(centered=False):
            logo = self.blocks.pop()
            logo = logo.crop((0, 0, 224, logo.height))
            logo.thumbnail((160, 60), Image.Resampling.LANCZOS)
            header = Image.new("L", (WIDTH, 76), 255)
            header.paste(logo, (0, 7))
            draw = ImageDraw.Draw(header)
            draw.text((WIDTH, 0), "PEDIDO", font=font(18, True), fill=0, anchor="rt")
            face = font(36, True)
            if face.getlength(ref) <= 390:
                draw.text((WIDTH, 27), ref, font=face, fill=0, anchor="rt")
                self.texts.append((ref, ""))
                self.blocks.append(header)
            else:
                self.blocks.append(header)
                self.text(ref, size=36, bold=True)
        else:
            self.text(shop_name or "Ficha do pedido", size=24, bold=True)
            self.text("PEDIDO " + ref, size=36, bold=True)
        self.rule()
        self.text(commitment, size=28, bold=True)
        if reprint:
            self.text("2ª VIA", size=24, bold=True)
        self.space(5)
        self.text(name, right=phone, size=25, bold=True)
        return b""

    def emphasis(self, text, *, tall=False):
        if str(text).startswith("PEDIDO "):
            self.space(10)
            return self.text(text, size=40, bold=True)
        if tall:
            self.space(6)
            return self.text(text, size=36, bold=True)
        return self.text(text, size=23 if self.fiscal else 25, bold=True)

    def rule(self, columns=48):
        block = Image.new("L", (WIDTH, 17), 255)
        ImageDraw.Draw(block).line((0, 8, WIDTH, 8), fill=0, width=2)
        self.blocks.append(block)
        return b""

    def logo(self, centered=True):
        path = getattr(settings, "SHOPMAN_PRINT_LOGO_PATH", "")
        if not path:
            return b""
        try:
            with Image.open(path) as source:
                logo = source.convert("RGBA")
                logo.thumbnail((224, 80), Image.Resampling.LANCZOS)
                block = Image.new("L", (WIDTH, logo.height + 8), 255)
                block.paste(logo.convert("L"), ((WIDTH - logo.width) // 2 if centered else 0, 0), logo.getchannel("A"))
                self.blocks.append(block)
        except (OSError, ValueError):
            return b""
        return b"logo"

    def qr(self, data, *, module=6):
        import qrcode

        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=module, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        image = qr.make_image().convert("L")
        if image.width > WIDTH:
            raise ValueError("QR excede a largura imprimível.")
        block = Image.new("L", (WIDTH, image.height), 255)
        block.paste(image, ((WIDTH - image.width) // 2, 0))
        self.blocks.append(block)
        return b""

    def image(self):
        height = sum(block.height for block in self.blocks)
        if height > 100000:
            raise ValueError("Impresso excede limite de composição.")
        image = Image.new("L", (WIDTH, max(height, 1)), 255)
        y = 0
        for block in self.blocks:
            image.paste(block, (0, y))
            y += block.height
        return image

    def finish(self):
        return raster_bytes(self.image())


def bindings(*, fiscal=False):
    from . import receipt_escpos as native

    layout = RasterLayout(fiscal=fiscal) if getattr(settings, "SHOPMAN_PRINT_RENDERER", "native") == "raster" else None
    methods = ("line", "pair", "emphasis", "centered", "rule", "wrap", "qr")
    return layout, tuple(getattr(layout, name) if layout else getattr(native, "_" + name) for name in methods)
