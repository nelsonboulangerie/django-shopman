"""Composição proporcional em pontos nativos: bobina 80 mm / cabeça 576 dots.

Os mesmos compositores e dados alimentam os dois modos. Este backend mede texto
com a fonte distribuída no projeto; não depende de browser, SO ou fontes remotas.
"""

from functools import lru_cache
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parents[1] / "assets/print"
WIDTH = 576


@lru_cache(maxsize=32)
def font(size, bold=False):
    name = "BarlowSemiCondensed-Bold.ttf" if bold else "BarlowSemiCondensed-Medium.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


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
        self.box_start = None
        self.inset = 0

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
        inset = max(inset, self.inset)
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

    def brand_header(self, name, details=()):
        # Texto fiscal vem do XML; a marca é a única imagem configurada.
        offset = 0
        logo_image = None
        path = getattr(settings, "SHOPMAN_PRINT_LOGO_PATH", "")
        if path:
            try:
                with Image.open(path) as source:
                    logo_image = source.convert("RGBA")
                    logo_image.thumbnail((96, 96), Image.Resampling.LANCZOS)
                    offset = 118
            except (OSError, ValueError):
                pass
        lines = []
        for text, size, bold in [(name, 29, True)] + [(text, 21, False) for text in details if text]:
            self.texts.append((str(text), ""))
            lines.extend((part, size, bold) for part in self._lines(text, font(size, bold), WIDTH - offset - 4))
        height = max(100 if logo_image else 0, sum(size + 5 for _, size, _ in lines))
        block = Image.new("L", (WIDTH, height + 12), 255)
        if logo_image:
            block.paste(logo_image.convert("L"), (0, 4), logo_image.getchannel("A"))
        draw = ImageDraw.Draw(block)
        y = 4
        for text, size, bold in lines:
            draw.text((offset, y), text, font=font(size, bold), fill=0, anchor="lt")
            y += size + 5
        self.blocks.append(block)
        return b""

    def begin_box(self):
        if self.box_start is not None:
            raise ValueError("Caixas não podem ser aninhadas.")
        self.box_start = len(self.blocks)
        self.inset = 16
        self.space(12)
        return b""

    def end_box(self):
        if self.box_start is None:
            return b""
        self.space(10)
        parts = self.blocks[self.box_start :]
        del self.blocks[self.box_start :]
        block = Image.new("L", (WIDTH, sum(part.height for part in parts)), 255)
        y = 0
        for part in parts:
            block.paste(part, (0, y))
            y += part.height
        ImageDraw.Draw(block).rounded_rectangle((1, 1, WIDTH - 2, block.height - 2), radius=12, outline=0, width=2)
        self.blocks.append(block)
        self.box_start = None
        self.inset = 0
        self.space(12)
        return b""

    def header(self, ref, commitment, name, phone, shop_name, reprint):
        self.brand_header(shop_name or "Ficha do pedido", ("FICHA DO PEDIDO",))
        self.begin_box()
        self.texts.extend([(str(ref), ""), (commitment, "")])
        left = [("PEDIDO" + (" · 2ª VIA" if reprint else ""), 20, True)]
        left.extend((part, 36, True) for part in self._lines(ref, font(36, True), 240))
        segments = commitment.split(" | ")
        right = [(segments[0], 28, True)]
        right.extend((part, 24, True) for segment in segments[1:] for part in self._lines(segment, font(24, True), 264))
        height = max(sum(size + 5 for _, size, _ in left), sum(size + 5 for _, size, _ in right))
        block = Image.new("L", (WIDTH, height + 6), 255)
        draw = ImageDraw.Draw(block)
        for x, lines in [(16, left), (296, right)]:
            y = 2
            for text, size, bold in lines:
                draw.text((x, y), text, font=font(size, bold), fill=0, anchor="lt")
                y += size + 5
        draw.line((278, 3, 278, height - 3), fill=0, width=2)
        self.blocks.append(block)
        self.end_box()
        self.text(name, right=phone, size=27, bold=True)
        return b""

    def cash_metrics(self, change, due):
        self.texts.extend([("Levar de troco", change), ("Valor a cobrar", due)])
        block = Image.new("L", (WIDTH, 65), 255)
        draw = ImageDraw.Draw(block)
        for x, label, value in [(16, "LEVAR DE TROCO", change), (296, "VALOR A COBRAR", due)]:
            draw.text((x, 2), label, font=font(20), fill=0, anchor="lt")
            if font(30, True).getlength(value) > 248:
                # Valores extraordinariamente longos usam a quebra normal.
                self.pair("Levar de troco", change)
                self.pair("Valor a cobrar", due)
                return b""
            draw.text((x, 29), value, font=font(30, True), fill=0, anchor="lt")
        draw.line((278, 4, 278, 58), fill=0, width=2)
        self.blocks.append(block)
        return b""

    def emphasis(self, text, *, tall=False):
        text = str(text).strip("* ")
        if str(text).startswith("PEDIDO "):
            self.space(10)
            return self.text(text, size=40, bold=True)
        if tall:
            self.space(6)
            return self.text(text, size=36, bold=True)
        return self.text(text, size=23 if self.fiscal else 25, bold=True)

    def rule(self, columns=48):
        return self.space(10)

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
        if self.box_start is not None:
            raise ValueError("Caixa de impressão não foi encerrada.")
        return raster_bytes(self.image())


def bindings(*, fiscal=False):
    from . import receipt_escpos as native

    layout = RasterLayout(fiscal=fiscal) if getattr(settings, "SHOPMAN_PRINT_RENDERER", "native") == "raster" else None
    methods = ("line", "pair", "emphasis", "centered", "rule", "wrap", "qr")
    return layout, tuple(getattr(layout, name) if layout else getattr(native, "_" + name) for name in methods)
