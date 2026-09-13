"""KDS actions cannot bypass the iFood guard already displayed on their cards."""

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance
from shopman.backstage.projections.kds import build_kds_board
from shopman.shop.models import Channel, Shop
from shopman.shop.services import kds, operator_orders


@pytest.fixture
def expedition(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="ifood", name="iFood", config={"payment": {"method": "external", "timing": "external"}})
    return KDSInstance.objects.create(ref="ifood-expedition", name="Expedição", type="expedition")


def order_with(facts, *, data=None, external_ref="official-order"):
    return Order.objects.create(
        ref="IFD-EXP", channel_ref="ifood", external_ref=external_ref, status="ready", total_q=1000,
        data={"fulfillment_type": "delivery", "payment": {"method": "external", "gateway": "ifood"}, "ifood": facts, **(data or {})},
    )


@pytest.mark.django_db
@pytest.mark.parametrize("scenario", ["ifood_driver", "unknown_driver", "cancellation", "future", "invalid_schedule"])
def test_projected_guard_also_blocks_direct_expedition_action(expedition, scenario):
    facts = {"delivered_by": "MERCHANT"}
    data = {}
    if scenario == "ifood_driver":
        facts["delivered_by"] = "IFOOD"
    elif scenario == "unknown_driver":
        facts["delivered_by"] = ""
    elif scenario == "cancellation":
        data["ifood_cancellation_request"] = {"state": "sent"}
    elif scenario == "future":
        facts.update(order_timing="SCHEDULED", schedule={"preparation_start_at": (timezone.now() + timedelta(hours=1)).isoformat()})
    elif scenario == "invalid_schedule":
        facts.update(order_timing="SCHEDULED", schedule={})
    order = order_with(facts, data=data)
    projected = next(card for card in build_kds_board(expedition.ref).tickets if card.order_ref == order.ref)
    expected = operator_orders.advance_block_reason(order)
    assert expected
    assert projected.advance_block_reason == expected
    assert kds.expedition_block_reason(order, action="dispatch") == expected
    with pytest.raises(ValueError) as raised:
        kds.expedition_action_by_order_id(order.pk, action="dispatch", actor="kds:operator")
    assert str(raised.value) == expected
    order.refresh_from_db()
    assert order.status == "ready"


@pytest.mark.django_db
@pytest.mark.parametrize(("facts", "external_ref"), [
    ({"delivered_by": "MERCHANT"}, "official-order"),
    ({"delivered_by": "IFOOD", "remote_dispatched": {"event_id": "dsp-1"}}, "official-order"),
    ({}, "IFOOD-SIM-123"),
])
def test_permitted_ifood_paths_remain_available(expedition, facts, external_ref):
    order = order_with(facts, external_ref=external_ref)
    assert kds.expedition_block_reason(order, action="dispatch") == ""
    assert kds.expedition_action_by_order_id(order.pk, action="dispatch", actor="kds:operator") == "dispatched"
    order.refresh_from_db()
    assert order.status == "dispatched"
