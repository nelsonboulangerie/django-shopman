"""Dados críticos chegam ao backend gráfico; raster preserva pontos e QR."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from PIL import Image, ImageChops

from shopman.backstage.services.print_layout import RasterLayout, font, raster_bytes
from shopman.backstage.services.receipt_escpos import danfe_nfce, order_ticket
from shopman.shop.services.danfe_xml import parse_authorized_xml
from shopman.shop.tests.danfe_fixtures import KEY, XML
from shopman.shop.views.fiscal_danfe import DanfeDocument, document_from_xml


def decode_raster(payload):
    assert payload.startswith(b"\x1b@\x1ba\x00")
    i, strips = 5, []
    while payload[i : i + 4] == b"\x1dv0\x00":
        width = int.from_bytes(payload[i + 4 : i + 6], "little")
        height = int.from_bytes(payload[i + 6 : i + 8], "little")
        assert width == 72 and 0 < height <= 128
        raw = payload[i + 8 : i + 8 + width * height]
        strips.append(Image.frombytes("1", (width * 8, height), bytes(v ^ 255 for v in raw)))
        i += 8 + width * height
    assert payload[i:] == b"\x1bd\x04\x1dV\x01"
    result = Image.new("1", (576, sum(s.height for s in strips)), 1)
    y = 0
    for strip in strips:
        result.paste(strip, (0, y))
        y += strip.height
    return result


@pytest.fixture
def capture(settings, monkeypatch):
    settings.SHOPMAN_PRINT_RENDERER = "raster"
    settings.SHOPMAN_PRINT_LOGO_PATH = ""
    layouts = []
    original = RasterLayout.finish

    def finish(self):
        layouts.append(self)
        return original(self)

    monkeypatch.setattr(RasterLayout, "finish", finish)
    return layouts


def example(payment):
    return SimpleNamespace(
        ref="FICTICIO-104",
        total_q=3600,
        created_at=timezone.now(),
        data={
            "customer": {"name": "Ana Exemplo"},
            "fulfillment_type": "delivery",
            "payment": payment,
            "order_notes": "Sem cortar; conferir embalagem.",
        },
        items=SimpleNamespace(all=lambda: [SimpleNamespace(qty=Decimal("2"), name="Pão natural", line_total_q=3600)]),
    )


def content(layout):
    return "\n".join(" ".join(pair) for pair in layout.texts)


def test_cash_change_is_main_instruction(capture):
    payload = order_ticket(example({"method": "cash", "collection": "on_delivery", "change_for_q": 10000}))
    text = content(capture[0])
    assert "TROCO PARA R$ 100,00" in text
    assert "Levar de troco R$ 64,00" in text
    assert "Valor a cobrar R$ 36,00" in text
    assert text.index("TROCO PARA") < text.index("Valor a cobrar")
    assert "Sem cortar; conferir embalagem." in text
    assert decode_raster(payload).height > 0


def test_paid_delivery_never_collects(capture):
    order_ticket(example({"method": "cash", "status": "captured", "collection": "on_delivery", "change_for_q": 10000}))
    text = content(capture[0])
    assert "PAGO - NÃO COBRAR" in text
    assert "TROCO PARA" not in text and "A COBRAR" not in text


def test_card_and_mixed_keep_each_amount(capture):
    order_ticket(
        example(
            {
                "method": "mixed",
                "collection": "on_delivery",
                "change_for_q": 10000,
                "tenders": [{"method": "cash", "amount_q": 2000}, {"method": "credit", "amount_q": 1600}],
            }
        )
    )
    text = content(capture[0])
    assert "A COBRAR R$ 36,00" in text
    assert "R$ 16,00" in text and "R$ 20,00" in text
    assert "LEVAR MAQUININHA" in text and "Levar de troco R$ 80,00" in text


def test_fiscal_fields_and_qr_survive_graphic_backend(capture):
    doc = document_from_xml(
        DanfeDocument(
            order_ref="DEMO",
            emitted=True,
            is_homolog=True,
            environment_label="Homologação",
            status="autorizado",
            shop_name="",
            shop_legal_name="",
            shop_cnpj="",
            shop_address="",
            number="",
            series="",
            key=KEY,
            chave_grouped="",
            protocol="",
        ),
        parse_authorized_xml(XML, KEY),
    )
    payload = danfe_nfce(doc)
    text = content(capture[0])
    for value in [
        doc.protocol,
        doc.chave_grouped,
        doc.query_url,
        doc.customer_address,
        doc.issued_at,
        doc.authorized_at,
        doc.total_display,
    ]:
        assert value in text
    for label, amount in doc.payments:
        assert label + " " + amount in text
    expected = capture[0].image().point(lambda p: 255 if p >= 160 else 0, mode="1")
    assert ImageChops.difference(expected, decode_raster(payload)).getbbox() is None


def test_raster_strips_preserve_every_pixel():
    im = Image.new("1", (576, 301), 255)
    for y in range(301):
        im.putpixel((y % 576, y), 0)
    assert ImageChops.difference(im, decode_raster(raster_bytes(im))).getbbox() is None


def test_long_identifiers_wrap_without_losing_characters():
    layout = RasterLayout()
    value = "ABC123" * 60
    lines = layout._lines(value, font(24), 220)
    assert "".join(part.strip() for part in lines) == value
    assert all(font(24).getlength(part.strip()) <= 220 for part in lines)
