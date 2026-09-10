"""Batch reads retain the canonical fermata predicate and all competing holds."""
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.orderman.models import Order
from shopman.stockman.models import Hold

from shopman.backstage.projections.order_queue import build_order_queue, build_two_zone_queue
from shopman.shop.models import Shop
from shopman.shop.services import waitlist
from shopman.shop.tests.test_waitlist_lifecycle import _order_in_fermata, _planned_quant

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("build", [build_order_queue, build_two_zone_queue])
@pytest.mark.parametrize("status", ["ready", "accepted"])
def test_a_hundred_cards_read_holds_once(build, status):
    Shop.objects.create(name="Lab")
    Order.objects.bulk_create([Order(ref=f"BATCH-{i}", status=status, channel_ref="web", data={"payment": {"method": "cash"}}) for i in range(100)])
    with CaptureQueriesContext(connection) as queries:
        build()
    hold_queries = [query["sql"] for query in queries if "stockman_hold" in query["sql"].lower()]
    assert len(hold_queries) == 1


def test_batch_respects_other_orders_reserving_the_same_quant():
    quant = _planned_quant("3")
    visible = _order_in_fermata("VISIBLE", "2", quant=quant)
    hidden = _order_in_fermata("HIDDEN", "2", quant=quant)
    assert waitlist.state_for(visible) == waitlist.NONE
    with CaptureQueriesContext(connection) as queries:
        assert waitlist.states_for([visible]) == {visible.ref: waitlist.NONE}
    assert len(queries) == 1
    Hold.objects.filter(metadata__reference=f"order:{hidden.ref}").update(quantity=Decimal("1"))
    assert waitlist.states_for([visible]) == {visible.ref: waitlist.FERMATA}


def test_batch_agrees_with_single_read_for_stored_legacy_and_expired_states():
    from datetime import timedelta

    from django.utils import timezone

    orders = [_order_in_fermata(f"MIX-{i}", "1", quant=_planned_quant("20")) for i in range(5)]
    orders[0].data["waitlist"] = {"state": waitlist.CONFIRMING}
    orders[1].data["waitlist"] = {"state": waitlist.RELEASED}
    Hold.objects.filter(metadata__reference=f"order:{orders[2].ref}").update(metadata={"reference": f"order:{orders[2].ref}", "planned": True})
    Hold.objects.filter(metadata__reference=f"order:{orders[3].ref}").update(expires_at=timezone.now() - timedelta(seconds=1))
    expected = {order.ref: waitlist.state_for(order) for order in orders}
    with CaptureQueriesContext(connection) as queries:
        assert waitlist.states_for(orders) == expected
    assert len(queries) == 1
