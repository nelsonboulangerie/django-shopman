"""FOOD benefit evidence is visible without changing prices or payment status."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shopman.backstage.projections.ifood import benefits_summary, operation_summary, payment_summary
from shopman.shop.services import ifood_ingest, ifood_orders


def _raw():
    return {"id": "benefit-order", "merchant": {"id": "merchant"},
            "items": [{"id": "bread", "name": "Pão", "quantity": 1, "unitPrice": 20, "totalPrice": 20}],
            "total": {"subTotal": 20, "benefits": 10, "orderAmount": 10},
            "benefits": [{"value": 10, "target": "CART", "campaign": {"id": "campaign"},
                          "sponsorshipValues": [{"name": "IFOOD", "value": 6}, {"name": "MERCHANT", "value": 4}]}]}


def _order(payload, channel="ifood"):
    return SimpleNamespace(channel_ref=channel, data={"ifood": payload})


def test_shared_coupon_preserves_raw_and_displays_each_subsidy_without_repricing():
    raw = _raw()
    original = deepcopy(raw)
    payload = ifood_orders.map_order(raw)
    benefit = payload["benefits"][0]
    assert benefit["raw"] == original["benefits"][0]
    assert benefit["value_q"] == 1000
    assert [s["value_q"] for s in benefit["sponsorships"]] == [600, 400]
    assert benefits_summary(_order(payload)) == ("Desconto (carrinho): R$ 10,00; iFood: R$ 6,00; Loja: R$ 4,00",)
    assert payload["items"][0]["line_total_q"] == 2000
    assert payload["totals"]["order_amount_q"] == 1000
    assert raw == original
    raw["benefits"][0]["campaign"]["id"] = "changed"
    assert benefit["raw"]["campaign"]["id"] == "campaign"


@pytest.mark.parametrize("target", ["DELIVERY_FEE", "ITEM", "PROGRESSIVE_DISCOUNT_ITEM"])
@pytest.mark.parametrize("sponsor,label", [("IFOOD", "iFood"), ("MERCHANT", "Loja"), ("EXTERNAL", "Parceiro externo"), ("CHAIN", "Rede"), ("FUTURE", "FUTURE")])
def test_targets_and_sponsors_preserve_authority(target, sponsor, label):
    raw = _raw()
    raw["benefits"] = [{"value": 4.99, "target": target, "targetId": "2", "sponsorshipValues": [{"name": sponsor, "value": 4.99}]}]
    payload = ifood_orders.map_order(raw)
    assert payload["benefits"][0]["target_id"] == "2"
    assert f"{label}: R$ 4,99" in benefits_summary(_order(payload))[0]
    assert "#2" in benefits_summary(_order(payload))[0]


def test_unknown_sponsor_and_legacy_totals_never_assume_store_pays():
    payload = ifood_orders.map_order({**_raw(), "benefits": [{"value": 10, "target": "CART"}]})
    assert "responsável não informado" in payment_summary(_order(payload))[-1]
    assert "Loja" not in payment_summary(_order(payload))[-1]
    historical = _order({"totals": {"benefits_q": 1234}})
    assert payment_summary(historical)[-1] == "Desconto: R$ 12,34; responsável não informado pelo iFood"
    assert benefits_summary(_order(payload, channel="web")) == ()


@pytest.mark.parametrize("value", [None, "invalid", "NaN", "Infinity", -1])
def test_invalid_amount_remains_unknown_with_raw_evidence(value):
    payload = ifood_orders.map_order({**_raw(), "benefits": [{"value": value, "target": "CART"}]})
    assert payload["benefits"][0]["value_q"] is None
    assert payload["benefits"][0]["raw"]["value"] == value
    assert "valor não informado" in benefits_summary(_order(payload))[0]


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
