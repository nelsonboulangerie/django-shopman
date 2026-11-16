"""FOOD benefit evidence is visible without changing prices or payment status."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shopman.backstage.projections.ifood import operation_summary, total_lines
from shopman.shop.services import ifood_ingest, ifood_orders


def _raw():
    return {"id": "benefit-order", "merchant": {"id": "merchant"},
            "items": [{"id": "bread", "name": "Pão", "quantity": 1, "unitPrice": 20, "totalPrice": 20}],
            "total": {"subTotal": 20, "benefits": 10, "orderAmount": 10},
            "benefits": [{"value": 10, "target": "CART", "campaign": {"id": "campaign"},
                          "sponsorshipValues": [{"name": "IFOOD", "value": 6}, {"name": "MERCHANT", "value": 4}]}]}


def _order(payload, channel="ifood"):
    return SimpleNamespace(channel_ref=channel, data={"ifood": payload})


def _lines(order):
    return [(line.label, line.amount_display) for line in total_lines(order)]


def test_shared_coupon_preserves_raw_and_displays_each_subsidy_without_repricing():
    raw = _raw()
    original = deepcopy(raw)
    payload = ifood_orders.map_order(raw)
    benefit = payload["benefits"][0]
    assert benefit["raw"] == original["benefits"][0]
    assert benefit["value_q"] == 1000
    assert [s["value_q"] for s in benefit["sponsorships"]] == [600, 400]
    # A conta do total mostra cada desconto com quem paga.
    assert _lines(_order(payload)) == [("Desconto do iFood", "−R$ 6,00"), ("Desconto da loja", "−R$ 4,00")]
    assert payload["items"][0]["line_total_q"] == 2000
    assert payload["totals"]["order_amount_q"] == 1000
    assert raw == original
    raw["benefits"][0]["campaign"]["id"] = "changed"
    assert benefit["raw"]["campaign"]["id"] == "campaign"


@pytest.mark.parametrize("sponsor,label", [("IFOOD", "Desconto do iFood"), ("MERCHANT", "Desconto da loja"), ("EXTERNAL", "Desconto do iFood"), ("CHAIN", "Desconto do iFood")])
def test_cart_discount_is_explained_with_who_pays(sponsor, label):
    raw = _raw()
    raw["benefits"] = [{"value": 4.99, "target": "ITEM", "targetId": "2", "sponsorshipValues": [{"name": sponsor, "value": 4.99}]}]
    payload = ifood_orders.map_order(raw)
    assert payload["benefits"][0]["target_id"] == "2"
    assert _lines(_order(payload)) == [(label, "−R$ 4,99")]


def test_free_delivery_paid_by_ifood_and_fee_explain_the_real_order_3417():
    """Pedido real 3417: itens R$ 48,00, entrega grátis (iFood), total R$ 49,20."""
    raw = {**_raw(), "items": [{"id": "q", "name": "Queijo", "quantity": 1, "unitPrice": 48, "totalPrice": 48}],
           "total": {"subTotal": 48, "deliveryFee": 9.99, "benefits": 9.99, "additionalFees": 1.2, "orderAmount": 49.2},
           "benefits": [{"value": 9.99, "target": "DELIVERY_FEE", "sponsorshipValues": [{"name": "IFOOD", "value": 9.99}, {"name": "MERCHANT", "value": 0}]}],
           "additionalFees": [{"type": "SMALL_ORDER_FEE", "value": 1.2, "liabilities": [{"name": "IFOOD", "percentage": 100}]}]}
    payload = ifood_orders.map_order(raw)
    assert payload["additional_fees"][0]["value_q"] == 120
    assert _lines(_order(payload)) == [("Taxa de pedido mínimo do iFood", "+R$ 1,20")]


def test_fee_without_detail_still_explains_the_difference():
    payload = {"totals": {"subtotal_q": 4800, "delivery_fee_q": 999, "benefits_q": 999, "additional_fees_q": 120, "order_amount_q": 4920},
               "benefits": [{"value_q": 999, "target": "DELIVERY_FEE", "sponsorships": [{"sponsor": "IFOOD", "value_q": 999}]}]}
    assert _lines(_order(payload)) == [("Taxa do iFood paga pelo cliente", "+R$ 1,20")]


def test_paid_delivery_is_a_line_of_the_total():
    payload = {"totals": {"delivery_fee_q": 799}, "benefits": []}
    assert _lines(_order(payload)) == [("Taxa de entrega", "+R$ 7,99")]


def test_unknown_sponsor_and_legacy_totals_never_assume_who_pays():
    payload = ifood_orders.map_order({**_raw(), "benefits": [{"value": 10, "target": "CART"}]})
    assert _lines(_order(payload)) == [("Desconto (responsável não informado pelo iFood)", "−R$ 10,00")]
    historical = _order({"totals": {"benefits_q": 1234}})
    assert _lines(historical) == [("Desconto (responsável não informado pelo iFood)", "−R$ 12,34")]
    assert total_lines(_order(payload, channel="web")) == ()


@pytest.mark.parametrize("value", [None, "invalid", "NaN", "Infinity", -1])
def test_invalid_amount_remains_unknown_with_raw_evidence(value):
    payload = ifood_orders.map_order({**_raw(), "benefits": [{"value": value, "target": "CART"}]})
    assert payload["benefits"][0]["value_q"] is None
    assert payload["benefits"][0]["raw"]["value"] == value
    assert payload["benefits"][0]["value_q"] is None
    assert total_lines(_order(payload)) == ()  # sem valor não há linha a somar


def test_pickup_code_is_visible_only_when_present():
    assert operation_summary(_order({"pickup_code": "0012"})) == ("Código de retirada: 0012",)
    assert operation_summary(_order({})) == ()
    assert operation_summary(_order({"pickup_code": "0012"}, channel="web")) == ()


@pytest.mark.django_db
def test_ingest_keeps_benefits_in_snapshot_without_duplicate_discount_or_payment():
    from shopman.shop.models import Channel
    Channel.objects.create(ref="ifood", name="iFood")
    payload = ifood_orders.map_order(_raw())
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest(payload)
    assert order.data["ifood"]["benefits"] == payload["benefits"]
    assert order.snapshot["data"]["ifood"]["benefits"] == payload["benefits"]
    assert order.total_q == 1000
    assert order.items.get().line_total_q == 2000
    assert order.data["payment"] == {"method": "external", "gateway": "ifood", "status": "unknown"}
