"""DANFE NFC-e: a fonte fiscal é o XML autorizado, nunca o pedido mutável."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.services.receipt_escpos import danfe_nfce
from shopman.shop.models import Shop
from shopman.shop.services.danfe_xml import DanfeSourceError, parse_authorized_xml, read_authorized_xml
from shopman.shop.tests.danfe_fixtures import KEY, XML, xml_for_key
from shopman.shop.views.fiscal_danfe import build_danfe


@pytest.fixture
def emitted_order(db, monkeypatch):
    Shop.objects.create(name="Cadastro alterado", legal_name="Razão alterada")
    order = Order.objects.create(
        ref="WEB-1",
        channel_ref="web",
        total_q=99_999,
        data={
            "customer": {"name": "Outro cliente"},
            "fiscal": {"tax_id": "52998224725"},
            "payment": {"method": "card", "status": "pending"},
            "nfce_access_key": KEY,
            "nfce_number": 999,
            "nfce_series": "9",
            "nfce_protocol": "999",
            "nfce_xml_url": "https://api.focusnfe.com.br/fixture.xml",
            "nfce_danfe_url": "https://api.focusnfe.com.br/fixture.pdf",
            "nfce_qrcode_url": "https://example.invalid/errado",
            "nfce_status": "autorizado",
        },
    )
    OrderItem.objects.create(
        order=order,
        line_id="1",
        sku="TAXA",
        name="Taxa fora da nota",
        qty=1,
        unit_price_q=99_999,
        line_total_q=99_999,
    )
    monkeypatch.setattr("shopman.shop.services.danfe_xml.read_authorized_xml", xml_for_key)
    return order


def test_authorized_values_ignore_mutable_order_shop_and_environment(emitted_order, settings):
    settings.SHOPMAN_FOCUS_NFE = {"environment": "producao"}
    document = build_danfe("WEB-1")

    assert document.source_verified and document.is_homolog
    assert document.shop_legal_name == "Padaria Exemplo Ltda"
    assert document.total_display == "R$ 50,00"
    assert document.item_count == 2 and document.items[0].sku == "PAO"
    assert document.items[0].unit_price_display == "R$ 18,00"
    assert document.customer_name == "Ana Exemplo"
    assert document.customer_tax_id_display == "000.000.001-91"
    assert "entrada pela rua lateral" in document.customer_address
    assert document.issued_at == "12/09/2026 09:05:00"
    assert document.authorized_at.endswith("09:05:03")
    assert document.number == "152" and document.series == "1"
    assert document.consult_url.endswith(f"{KEY}|3|2")
    assert document.payments == (("Dinheiro", "R$ 30,00"), ("PIX", "R$ 25,00"), ("Troco", "R$ 5,00"))
    assert ("Desconto", "R$ 3,00") in document.totals
    assert ("Frete", "R$ 5,00") in document.totals

    paper = danfe_nfce(document).decode("cp860")
    for critical in ("R$ 50,00", "R$ 3,00", "R$ 5,00", "000.000.001-91", "141260000000152", "PAO"):
        assert critical in paper
    assert "Taxa fora da nota" not in paper
    assert "Cadastro alterado" not in paper


def test_view_requires_staff_and_never_falls_back_to_mutable_data(client, emitted_order, monkeypatch):
    user = User.objects.create_user("plain", is_staff=False)
    client.force_login(user)
    assert client.get("/fiscal/danfe/WEB-1/").status_code == 404

    user.is_staff = True
    user.save()
    client.force_login(user)
    response = client.get("/fiscal/danfe/WEB-1/")
    assert response.status_code == 200
    assert "SEM VALOR FISCAL" in response.content.decode()

    monkeypatch.setattr(
        "shopman.shop.services.danfe_xml.read_authorized_xml",
        Mock(side_effect=DanfeSourceError("XML indisponível")),
    )
    body = client.get("/fiscal/danfe/WEB-1/").content.decode()
    assert "XML indisponível" in body
    assert "Ver no Focus" in body
    assert "999,99" not in body
    assert "Taxa fora da nota" not in body


def test_cancelled_unavailable_and_unemitted_documents_do_not_print(emitted_order, monkeypatch):
    monkeypatch.setattr(
        "shopman.shop.services.danfe_xml.read_authorized_xml",
        Mock(side_effect=DanfeSourceError("Sem XML")),
    )
    document = build_danfe("WEB-1")
    assert document.emitted and not document.source_verified
    with pytest.raises(ValueError, match="XML autorizado"):
        danfe_nfce(document)

    emitted_order.data["nfce_cancelled"] = True
    emitted_order.save(update_fields=["data"])
    cancelled = build_danfe("WEB-1")
    assert cancelled.status == "cancelada" and not cancelled.source_verified

    Order.objects.create(ref="EMPTY", channel_ref="web")
    empty = build_danfe("EMPTY")
    assert not empty.emitted and not empty.source_verified
    assert build_danfe("MISSING") is None


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"<mod>65</mod>", b"<mod>55</mod>"),
        (b"<cStat>100</cStat>", b"<cStat>101</cStat>"),
        (b"<nProt>141260000000152</nProt>", b""),
        (b"<urlChave>http://www.fazenda.pr.gov.br/nfce/consulta</urlChave>", b""),
    ],
)
def test_invalid_or_incomplete_sources_are_rejected(old, new):
    with pytest.raises(DanfeSourceError):
        parse_authorized_xml(XML.replace(old, new), KEY)


def test_wrong_key_entities_rtc_and_delivery_without_address_are_rejected():
    with pytest.raises(DanfeSourceError):
        parse_authorized_xml(XML, "9" * 44)
    with pytest.raises(DanfeSourceError):
        parse_authorized_xml(b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>', KEY)
    with pytest.raises(DanfeSourceError, match="RTC"):
        parse_authorized_xml(XML.replace(b"</ICMSTot>", b"</ICMSTot><IBSCBSTot/>", 1), KEY)
    without_address = XML.replace("<xLgr>Avenida das Araucárias</xLgr>".encode(), b"", 1)
    with pytest.raises(DanfeSourceError, match="endereço"):
        parse_authorized_xml(without_address, KEY)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.focusnfe.com.br/a",
        "https://localhost/a",
        "https://api.focusnfe.com.br.evil.test/a",
        "https://secret@api.focusnfe.com.br/a",
        "https://api.focusnfe.com.br:444/a",
    ],
)
def test_source_transport_rejects_untrusted_urls(url, settings):
    settings.SHOPMAN_FOCUS_NFE = {"base_url": "https://api.focusnfe.com.br"}
    with pytest.raises(DanfeSourceError, match="provedor configurado"):
        read_authorized_xml(url, KEY)


def test_source_transport_rejects_redirect_and_oversized_body(settings):
    settings.SHOPMAN_FOCUS_NFE = {"base_url": "https://api.focusnfe.com.br"}
    redirect = Mock(status_code=302)
    redirect.__enter__ = Mock(return_value=redirect)
    redirect.__exit__ = Mock(return_value=False)
    with patch("shopman.shop.services.danfe_xml.requests.get", return_value=redirect):
        with pytest.raises(DanfeSourceError, match="obter o XML"):
            read_authorized_xml("https://api.focusnfe.com.br/redirect.xml", KEY)

    oversized = Mock(status_code=200)
    oversized.iter_content.return_value = [b"x" * 1_100_000, b"y" * 1_100_000]
    oversized.__enter__ = Mock(return_value=oversized)
    oversized.__exit__ = Mock(return_value=False)
    with patch("shopman.shop.services.danfe_xml.requests.get", return_value=oversized):
        with pytest.raises(DanfeSourceError, match="excede"):
            read_authorized_xml("https://api.focusnfe.com.br/large.xml", KEY)
