"""External orders need a stable sealed identity for the canonical KDS ledger."""
from unittest.mock import patch

import pytest
from shopman.orderman.exceptions import ImmutabilityError
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.models import Channel
from shopman.shop.services import ifood_ingest, kds


def test_session_identity_is_stable_bounded_and_merchant_scoped():
    key = ifood_ingest.session_key_for_order("merchant", "external")
    assert key == ifood_ingest.session_key_for_order("merchant", "external")
    assert len(key) <= 64
    assert key.startswith("ifood:")
    assert key != ifood_ingest.session_key_for_order("other", "external")
    assert key != ifood_ingest.session_key_for_order("merchant", "other")
    assert ifood_ingest.session_key_for_order("a:b", "c") != ifood_ingest.session_key_for_order("a", "b:c")
    assert len(ifood_ingest.session_key_for_order("m" * 1000, "o" * 1000)) <= 64
    assert ifood_ingest.session_key_for_order(None, "simulation") == ifood_ingest.session_key_for_order("", "simulation")


@pytest.mark.django_db
@pytest.mark.parametrize("is_test", [False, True])
def test_ingest_dispatches_real_kds_and_repeat_dispatch_is_idempotent(is_test):
    Channel.objects.create(ref="ifood", name="iFood")
    KDSInstance.objects.create(ref="ifood-picking", name="Separação", type="picking")
    payload = {"order_code": "external-order", "merchant_id": "merchant", "is_test": is_test,
               "items": [{"sku": "BREAD", "name": "Pão", "qty": 2, "unit_price_q": 500}]}
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest(payload)
    order.refresh_from_db()
    assert order.session_key == ifood_ingest.session_key_for_order("merchant", "external-order")
    tickets = kds.dispatch(order)
    assert len(tickets) == 1
    assert tickets[0].session_key == order.session_key
    assert tickets[0].items[0]["sku"] == "BREAD"
    assert kds.dispatch(order) == []
    assert KDSTicket.objects.filter(session_key=order.session_key).count() == 1
    order.data["diagnostic"] = "normal mutable save remains valid"
    order.save(update_fields=["data", "updated_at"])
    assert Order.objects.get(pk=order.pk).session_key == order.session_key


@pytest.mark.django_db
def test_historical_empty_session_key_remains_sealed_and_untouched():
    historical = Order.objects.create(ref="IFOOD-HISTORICAL", channel_ref="ifood", session_key="")
    historical.data = {"diagnostic": "existing order"}
    historical.save(update_fields=["data", "updated_at"])
    historical.refresh_from_db()
    assert historical.session_key == ""
    historical.session_key = ifood_ingest.session_key_for_order("merchant", "historical")
    with pytest.raises(ImmutabilityError):
        historical.save(update_fields=["session_key"])
    assert Order.objects.get(pk=historical.pk).session_key == ""


@pytest.mark.django_db
def test_real_combo_observations_options_and_customizations_reach_kds():
    import json
    from pathlib import Path

    from shopman.shop.services import ifood_orders

    raw = json.loads((Path(__file__).parent / "fixtures" / "ifood_order_real.json").read_text())
    combo = raw["items"][1]
    combo["observations"] = "Sem cebola; molho à parte."
    combo["options"][0]["quantity"] = 2
    original = json.loads(json.dumps(raw))
    payload = ifood_orders.map_order(raw)
    Channel.objects.create(ref="ifood", name="iFood")
    KDSInstance.objects.create(ref="combo-picking", name="Separação", type="picking")
    with patch.object(ifood_ingest.order_changed, "send"):
        order = ifood_ingest.ingest(payload)
    ticket = kds.dispatch(order)[0]
    item = next(item for item in ticket.items if item["sku"] == combo["externalCode"])
    assert "Sem cebola; molho à parte." in item["notes"]
    assert "2× Complemento 1 - Segundo Nível" in item["notes"]
    for option in combo["options"]:
        assert option["name"] in item["notes"]
        assert option["groupName"] in item["notes"]
        for customization in option.get("customizations") or []:
            assert customization["name"] in item["notes"]
            assert customization["groupName"] in item["notes"]
    canonical_meta = payload["items"][1]["meta"]
    stored = order.items.get(sku=combo["externalCode"])
    assert stored.meta == canonical_meta
    assert stored.meta["observations"] == combo["observations"]
    assert len(stored.meta["options"][-1]["customizations"]) == 3
    assert raw == original  # presentation does not rewrite the source contract
    assert kds.dispatch(order) == []
