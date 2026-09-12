"""DANFE: dados do XML autorizado, nunca do pedido nem do cadastro mutável."""

from __future__ import annotations

from dataclasses import replace
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
        total_q=99999,
        data={
            "customer": {"name": "Outro cliente"},
            "fiscal": {"tax_id": "52998224725"},
            "payment": {"method": "card", "status": "pending"},
            "nfce_access_key": KEY,
            "nfce_number": 999,
            "nfce_series": "9",
            "nfce_protocol": "999",
            "nfce_xml_url": "https://api.focusnfe.com.br/fixture.xml",
            "nfce_status": "autorizado",
            "nfce_danfe_url": "https://api.focusnfe.com.br/fixture.pdf",
            "nfce_qrcode_url": "https://example.invalid/errado",
        },
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="TAXA", name="Taxa fora da nota", qty=1, unit_price_q=99999, line_total_q=99999
    )
    monkeypatch.setattr("shopman.shop.services.danfe_xml.read_authorized_xml", xml_for_key)
    return order


def test_authorized_values_ignore_mutable_order_shop_and_environment(emitted_order, settings):
    settings.SHOPMAN_FOCUS_NFE = {"environment": "producao"}
    d = build_danfe("WEB-1")
    assert d.source_verified and d.is_homolog
    assert d.shop_legal_name == "Padaria Exemplo Ltda"
    assert d.total_display == "R$ 50,00"
    assert d.item_count == 2 and d.items[0].sku == "PAO"
    assert d.items[0].unit_price_display == "R$ 18,00"
    assert d.customer_name == "Ana Exemplo" and d.customer_tax_id_display == "000.000.001-91"
    assert "entrada pela rua lateral" in d.customer_address
    assert d.issued_at == "12/09/2026 09:05:00" and d.authorized_at.endswith("09:05:03")
    assert d.number == "152" and d.series == "1"
    assert d.consult_url.endswith(f"{KEY}|3|2") and "<svg" in d.qr_svg
    assert d.payments == (("Dinheiro", "R$ 30,00"), ("PIX", "R$ 25,00"), ("Troco", "R$ 5,00"))
    assert ("Desconto", "R$ 3,00") in d.totals and ("Frete", "R$ 5,00") in d.totals
    paper = danfe_nfce(d).decode("cp860")
    for critical in ("R$ 50,00", "R$ 3,00", "R$ 5,00", "000.000.001-91", "141260000000152", "PAO", "SEM VALOR FISCAL"):
        assert critical in paper
    assert "Taxa fora da nota" not in paper and "Cadastro alterado" not in paper


def test_view_staff_and_no_unverified_fiscal_display(client, emitted_order, monkeypatch):
    user = User.objects.create_user("plain", is_staff=False)
    client.force_login(user)
    assert client.get("/fiscal/danfe/WEB-1/").status_code == 404
    user.is_staff = True
    user.save()
    client.force_login(user)
    response = client.get("/fiscal/danfe/WEB-1/")
    assert response.status_code == 200
    assert "SEM VALOR FISCAL" in response.content.decode() and "<svg" in response.content.decode()
    monkeypatch.setattr(
        "shopman.shop.services.danfe_xml.read_authorized_xml", Mock(side_effect=DanfeSourceError("XML indisponível"))
    )
    body = client.get("/fiscal/danfe/WEB-1/").content.decode()
    assert "XML indisponível" in body and "Ver no Focus" in body
    assert "999,99" not in body and "<svg" not in body
    assert "window.print" not in body


def test_cancelled_and_unavailable_do_not_print(emitted_order, monkeypatch):
    monkeypatch.setattr(
        "shopman.shop.services.danfe_xml.read_authorized_xml", Mock(side_effect=DanfeSourceError("Sem XML"))
    )
    d = build_danfe("WEB-1")
    assert not d.source_verified
    with pytest.raises(ValueError):
        danfe_nfce(d)
    emitted_order.data["nfce_cancelled"] = True
    emitted_order.save()
    assert build_danfe("WEB-1").status == "cancelada"


def test_missing_and_unemitted(db):
    assert build_danfe("missing") is None
    Order.objects.create(ref="empty", channel_ref="web")
    d = build_danfe("empty")
    assert not d.emitted and not d.source_verified
    assert d.qr_svg == ""


@pytest.mark.parametrize(
    "old,new",
    [
        (b"<mod>65</mod>", b"<mod>55</mod>"),
        (b"<cStat>100</cStat>", b"<cStat>101</cStat>"),
        (b"<nProt>141260000000152</nProt>", b""),
        (b"<urlChave>http://www.fazenda.pr.gov.br/nfce/consulta</urlChave>", b""),
    ],
)
def test_invalid_sources_rejected(old, new):
    with pytest.raises(DanfeSourceError):
        parse_authorized_xml(XML.replace(old, new), KEY)


def test_wrong_key_and_entities_rejected():
    with pytest.raises(DanfeSourceError):
        parse_authorized_xml(XML, "9" * 44)
    with pytest.raises(DanfeSourceError):
        parse_authorized_xml(b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>', KEY)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.focusnfe.com.br/a",
        "https://localhost/a",
        "https://api.focusnfe.com.br.evil.test/a",
        "https://secret@api.focusnfe.com.br/a",
    ],
)
def test_no_arbitrary_fetch(url, settings):
    settings.SHOPMAN_FOCUS_NFE = {}
    with patch("requests.get") as request, pytest.raises(DanfeSourceError):
        read_authorized_xml(url, KEY)
    request.assert_not_called()


def test_cnpj_label_and_complete_long_name(emitted_order, monkeypatch):
    xml = XML.replace(b"<CPF>00000000191</CPF>", b"<CNPJ>00000000000191</CNPJ>")
    name = "Empresa com nome muito extenso para conferir fidelidade do destinatário até o final"
    xml = xml.replace(b"Ana Exemplo", name.encode())
    monkeypatch.setattr(
        "shopman.shop.services.danfe_xml.read_authorized_xml", lambda *_: parse_authorized_xml(xml, KEY)
    )
    d = build_danfe("WEB-1")
    assert d.customer_tax_id_label == "CNPJ"
    assert "até o final" in danfe_nfce(d).decode("cp860")
    assert b"2a VIA" in danfe_nfce(d, reprint=True)
    with pytest.raises(ValueError):
        danfe_nfce(replace(d, source_verified=False))


def test_unavailable_source_does_not_stamp_first_print(client, emitted_order, monkeypatch):
    user = User.objects.create_superuser("printer", "", "pw")
    client.force_login(user)
    monkeypatch.setattr(
        "shopman.shop.services.danfe_xml.read_authorized_xml", Mock(side_effect=DanfeSourceError("XML indisponível"))
    )
    response = client.get("/api/v1/backstage/pos/orders/WEB-1/danfe-escpos/")
    assert response.status_code == 409
    assert response.json()["danfe_url"].endswith("fixture.pdf")
    assert "payload_b64" not in response.json()
    emitted_order.refresh_from_db()
    assert "danfe_printed_at" not in emitted_order.data


def test_source_fetch_is_bounded_and_cached():
    from unittest.mock import MagicMock

    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.iter_content.return_value = iter([XML[:100], XML[100:]])
    with (
        patch("shopman.shop.services.danfe_xml.cache") as cache,
        patch("requests.get", return_value=response) as request,
    ):
        cache.get.return_value = None
        root = read_authorized_xml("https://api.focusnfe.com.br/fixture.xml", KEY)
        assert root.tag.endswith("nfeProc")
        request.assert_called_once_with(
            "https://api.focusnfe.com.br/fixture.xml", timeout=(3, 8), stream=True, allow_redirects=False
        )
        assert cache.set.call_args.args[1] == XML
        cache.get.return_value = XML
        read_authorized_xml("https://api.focusnfe.com.br/fixture.xml", KEY)
        assert request.call_count == 1


@pytest.mark.parametrize("status,chunks", [(302, []), (500, []), (200, [b"x" * 2_000_001])])
def test_fetch_redirect_failure_and_oversize_rejected(status, chunks):
    from unittest.mock import MagicMock

    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = status
    response.iter_content.return_value = iter(chunks)
    with (
        patch("shopman.shop.services.danfe_xml.cache") as cache,
        patch("requests.get", return_value=response),
        pytest.raises(DanfeSourceError),
    ):
        cache.get.return_value = None
        read_authorized_xml("https://api.focusnfe.com.br/fixture.xml", KEY)
    cache.set.assert_not_called()


def test_foreign_qr_and_unsupported_rtc_are_not_silently_printed():
    with pytest.raises(DanfeSourceError, match="QR Code"):
        parse_authorized_xml(XML.replace(b"|3|2", b"|3|1"), KEY)
    with pytest.raises(DanfeSourceError, match="RTC"):
        parse_authorized_xml(
            XML.replace(b"</total>", b"<IBSCBSTot><vBCIBSCBS>48.00</vBCIBSCBS></IBSCBSTot></total>"), KEY
        )


def test_unrepresentable_fiscal_text_never_becomes_question_marks(emitted_order):
    d = replace(build_danfe("WEB-1"), customer_name="例示")
    with pytest.raises(ValueError, match="caracteres fiscais"):
        danfe_nfce(d)


def test_cancelled_note_does_not_offer_authorized_recovery(client, emitted_order):
    user = User.objects.create_superuser("cancelled-printer", "", "pw")
    client.force_login(user)
    emitted_order.data["nfce_cancelled"] = True
    emitted_order.save()
    response = client.get("/api/v1/backstage/pos/orders/WEB-1/danfe-escpos/")
    assert response.status_code == 409
    assert response.json()["danfe_url"] == ""
    assert "cancelada" in response.json()["detail"]
