"""GTIN recusado pela SEFAZ: a nota sai de novo "SEM GTIN", e a venda não trava.

Decisão do dono (24/09/2026): o GTIN nunca pode travar a venda. Rejeição de
GTIN (``services.fiscal.SEFAZ_GTIN_REJECTION_CODES``) → reemite a mesma nota
com "SEM GTIN" no item culpado, marca o produto (``gtin_nf_rejected``) e alerta
o operador; dali em diante o produto sai "SEM GTIN" até alguém conferir o GTIN
no Catálogo (``backstage/tests/test_gtin_recusado_no_catalogo.py``).
"""

from __future__ import annotations

import copy

import pytest
from shopman.fiscalman.contracts import FiscalDocumentResult
from shopman.offerman.models import Product
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters.fiscal_focusnfe import _document_result
from shopman.shop.handlers.fiscal import NFCeEmitHandler
from shopman.shop.models import Channel
from shopman.shop.services import fiscal as fiscal_service

pytestmark = pytest.mark.django_db

GTIN_GELEIA = "3088542500285"  # St. Dalfour — dígito verificador válido
GTIN_AGUA = "7896064200011"

AUTHORIZED = FiscalDocumentResult(
    success=True, access_key="4125" + "0" * 40, document_number=7, status="authorized",
)


def _rejected(cstat: str, message: str) -> FiscalDocumentResult:
    return _document_result({
        "status": "erro_autorizacao", "status_sefaz": cstat, "mensagem_sefaz": message,
    })


class SequenceBackend:
    """Devolve os resultados na ordem e guarda os itens de cada POST."""

    def __init__(self, *results):
        self.results = list(results)
        self.sent_items: list[list[dict]] = []
        self.references: list[str] = []
        self.kwargs: list[dict] = []

    def emit(self, *, reference, items, **kwargs):
        self.references.append(reference)
        self.kwargs.append(kwargs)
        self.sent_items.append(copy.deepcopy(items))
        return self.results.pop(0)

    def query_status(self, *, reference):
        return FiscalDocumentResult(success=False, error_code="not_found")

    def cancel(self, *, reference, reason):
        raise NotImplementedError


@pytest.fixture
def order(db):
    Channel.objects.create(ref="pdv", name="PDV")
    for sku, name, gtin in (
        ("GELEIA-DALFOUR", "Geleia St. Dalfour", GTIN_GELEIA),
        ("AGUA-500", "Água 500 ml", GTIN_AGUA),
    ):
        Product.objects.create(sku=sku, name=name, metadata={"social": {"gtin": gtin}})
    return Order.objects.create(
        ref="ORD-GTIN-1", channel_ref="pdv", status=Order.Status.ACCEPTED, total_q=3000,
    )


def _directive(order, items):
    return Directive.objects.create(
        topic="fiscal.emit_nfce",
        payload={
            "order_ref": order.ref, "items": items,
            "payment": {"method": "cash", "amount_q": 3000},
        },
        attempts=1,
    )


def _items():
    return [
        {"sku": "GELEIA-DALFOUR", "name": "Geleia St. Dalfour", "gtin": GTIN_GELEIA, "total_q": 2000},
        {"sku": "AGUA-500", "name": "Água 500 ml", "gtin": GTIN_AGUA, "total_q": 1000},
    ]


def _alerts(order):
    return OperatorAlert.objects.filter(type=fiscal_service.GTIN_REJECTED_ALERT_TYPE, order_ref=order.ref)


def test_focus_rejection_carries_the_sefaz_code():
    result = _rejected("890", "Rejeicao: GTIN inexistente no CCG [nItem:1]")
    assert result.success is False
    assert result.error_code == "sefaz_890"
    assert fiscal_service.sefaz_gtin_rejection_code(result.error_code) == "890"
    # 889 é de GTIN, mas "SEM GTIN" é a própria causa: não reemite.
    assert fiscal_service.sefaz_gtin_rejection_code("sefaz_889") == ""
    assert fiscal_service.sefaz_gtin_rejection_code("sefaz_704") == ""


def test_rejection_890_pointing_one_item_reemits_that_item_without_gtin(order):
    backend = SequenceBackend(
        _rejected("890", "Rejeicao: GTIN inexistente no Cadastro Centralizado de GTIN (CCG) [nItem:2]"),
        AUTHORIZED,
    )
    directive = _directive(order, _items())

    NFCeEmitHandler(backend).handle(message=directive, ctx={})

    # A venda não travou: a nota saiu na mesma referência.
    order.refresh_from_db()
    assert order.data["nfce_access_key"] == AUTHORIZED.access_key
    assert backend.references == [order.ref, order.ref]
    # Só o item apontado perdeu o GTIN; a geleia manteve o dela.
    resent = {item["sku"]: item["gtin"] for item in backend.sent_items[1]}
    assert resent == {"GELEIA-DALFOUR": GTIN_GELEIA, "AGUA-500": ""}
    # O payload da directive foi regravado: um retry também sai SEM GTIN.
    directive.refresh_from_db()
    assert {i["sku"]: i["gtin"] for i in directive.payload["items"]}["AGUA-500"] == ""

    water = Product.objects.get(sku="AGUA-500")
    mark = water.metadata["gtin_nf_rejected"]
    assert mark["code"] == "890"
    assert mark["gtin"] == GTIN_AGUA
    assert mark["order_ref"] == order.ref
    assert "CCG" in mark["reason"]
    assert mark["at"]
    assert "gtin_nf_rejected" not in Product.objects.get(sku="GELEIA-DALFOUR").metadata

    alert = _alerts(order).get()
    assert "AGUA-500" in alert.message and "890" in alert.message
    assert "GELEIA-DALFOUR" not in alert.message
    assert "A nota saiu de novo sem GTIN e foi autorizada." in alert.message
    assert "Catálogo" in alert.message and "gtin_nf_rejected" not in alert.message
    assert "—" not in alert.message
    assert fiscal_service.gtin_rejected_alert_sku(alert.message) == "AGUA-500"


def test_rejection_611_without_item_number_strips_every_gtin(order):
    backend = SequenceBackend(_rejected("611", "Rejeicao: GTIN (cEAN) invalido"), AUTHORIZED)

    NFCeEmitHandler(backend).handle(message=_directive(order, _items()), ctx={})

    assert [item["gtin"] for item in backend.sent_items[1]] == ["", ""]
    for sku in ("GELEIA-DALFOUR", "AGUA-500"):
        assert Product.objects.get(sku=sku).metadata["gtin_nf_rejected"]["code"] == "611"
    order.refresh_from_db()
    assert order.data["nfce_access_key"] == AUTHORIZED.access_key
    # Um alerta por produto: cada um tem o seu gesto no Catálogo e fecha sozinho.
    assert sorted(fiscal_service.gtin_rejected_alert_sku(a.message) for a in _alerts(order)) == [
        "AGUA-500", "GELEIA-DALFOUR",
    ]


def test_sefaz_pointing_items_one_at_a_time_reemits_until_authorized(order):
    backend = SequenceBackend(
        _rejected("890", "Rejeicao: GTIN inexistente no CCG [nItem:1]"),
        _rejected("891", "Rejeicao: GTIN incompativel com a NCM [nItem: 2]"),
        AUTHORIZED,
    )

    NFCeEmitHandler(backend).handle(message=_directive(order, _items()), ctx={})

    assert len(backend.sent_items) == 3
    assert [item["gtin"] for item in backend.sent_items[2]] == ["", ""]
    assert Product.objects.get(sku="GELEIA-DALFOUR").metadata["gtin_nf_rejected"]["code"] == "890"
    assert Product.objects.get(sku="AGUA-500").metadata["gtin_nf_rejected"]["code"] == "891"
    assert sorted(fiscal_service.gtin_rejected_alert_sku(a.message) for a in _alerts(order)) == [
        "AGUA-500", "GELEIA-DALFOUR",
    ]


def test_item_number_skips_the_delivery_fee_line(order):
    items = [
        {"sku": "__DELIVERY_FEE__", "name": "Taxa de entrega", "gtin": "", "meta": {"type": "delivery_fee"}},
        *_items(),
    ]
    backend = SequenceBackend(_rejected("890", "Rejeicao: GTIN inexistente no CCG [nItem:1]"), AUTHORIZED)

    NFCeEmitHandler(backend).handle(message=_directive(order, items), ctx={})

    resent = {item["sku"]: item["gtin"] for item in backend.sent_items[1]}
    assert resent["GELEIA-DALFOUR"] == ""
    assert resent["AGUA-500"] == GTIN_AGUA


def test_reemission_keeps_the_rest_of_the_note(order):
    intermediary = {"cnpj": "14380200000121", "id_cadastro": "loja-1"}
    directive = _directive(order, _items())
    directive.payload["intermediary"] = intermediary
    directive.save(update_fields=["payload"])
    backend = SequenceBackend(_rejected("890", "Rejeicao: GTIN inexistente no CCG [nItem:2]"), AUTHORIZED)

    NFCeEmitHandler(backend).handle(message=directive, ctx={})

    assert [call["intermediary"] for call in backend.kwargs] == [intermediary, intermediary]
    assert backend.kwargs[0]["payment"] == backend.kwargs[1]["payment"]


def test_rejection_that_is_not_about_gtin_keeps_current_behaviour(order):
    backend = SequenceBackend(_rejected("704", "Rejeicao: NFC-e com Data-Hora de emissao atrasada"))

    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(backend).handle(message=_directive(order, _items()), ctx={})

    assert len(backend.sent_items) == 1
    for sku in ("GELEIA-DALFOUR", "AGUA-500"):
        assert "gtin_nf_rejected" not in Product.objects.get(sku=sku).metadata
    assert not _alerts(order).exists()


def test_gtin_rejection_with_no_gtin_left_on_the_note_does_not_loop(order):
    items = [{**item, "gtin": ""} for item in _items()]
    backend = SequenceBackend(_rejected("890", "Rejeicao: GTIN inexistente no CCG [nItem:1]"))

    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(backend).handle(message=_directive(order, items), ctx={})

    assert len(backend.sent_items) == 1
    assert not _alerts(order).exists()


def test_reemission_that_fails_for_another_reason_still_marks_and_alerts(order):
    backend = SequenceBackend(
        _rejected("890", "Rejeicao: GTIN inexistente no CCG [nItem:2]"),
        _rejected("704", "Rejeicao: NFC-e com Data-Hora de emissao atrasada"),
    )

    with pytest.raises(DirectiveTerminalError):
        NFCeEmitHandler(backend).handle(message=_directive(order, _items()), ctx={})

    assert Product.objects.get(sku="AGUA-500").metadata["gtin_nf_rejected"]["code"] == "890"
    assert "ainda não foi autorizada" in _alerts(order).get().message


def test_marked_product_goes_out_without_gtin_on_the_next_notes(order):
    fiscal_service.mark_gtin_rejected(
        "AGUA-500", gtin=GTIN_AGUA, code="890", reason="GTIN inexistente no CCG", order_ref="ORD-OLD",
    )
    water = Product.objects.get(sku="AGUA-500")
    jam = Product.objects.get(sku="GELEIA-DALFOUR")

    assert fiscal_service._trusted_gtin(water.metadata) == ""
    assert fiscal_service._trusted_gtin(jam.metadata) == GTIN_GELEIA

    # Limpar a marca (depois de conferir a embalagem) devolve o GTIN à nota.
    metadata = dict(water.metadata)
    metadata.pop("gtin_nf_rejected")
    assert fiscal_service._trusted_gtin(metadata) == GTIN_AGUA


def test_marked_product_leaves_the_built_items_without_gtin(order):
    fiscal_service.mark_gtin_rejected(
        "AGUA-500", gtin=GTIN_AGUA, code="890", reason="x", order_ref="ORD-OLD",
    )
    order.items.create(line_id="1", sku="AGUA-500", name="Água 500 ml", qty=1, unit_price_q=1000, line_total_q=1000)
    order.items.create(line_id="2", sku="GELEIA-DALFOUR", name="Geleia", qty=1, unit_price_q=2000, line_total_q=2000)

    built = {item["sku"]: item["gtin"] for item in fiscal_service._build_fiscal_items(order)}

    assert built == {"AGUA-500": "", "GELEIA-DALFOUR": GTIN_GELEIA}
