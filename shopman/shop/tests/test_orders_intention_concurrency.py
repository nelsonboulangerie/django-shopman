"""PostgreSQL witnesses for distinct intentions against the same order base."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import connection, connections
from shopman.orderman.models import Order

from shopman.shop import lifecycle
from shopman.shop.models import Shop
from shopman.shop.services import operator_orders, remote_mutations


@pytest.mark.django_db(transaction=True)
def test_distinct_keys_cannot_advance_the_same_base_twice():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks and independent connections")
    Shop.objects.create(name="Lab")
    order = Order.objects.create(ref="SAME-BASE", status="accepted", channel_ref="web", data={"payment": {"method": "cash"}})
    base = operator_orders.operational_revision(order)
    barrier = Barrier(2)

    def worker(key):
        try:
            stale = Order.objects.get(pk=order.pk)
            barrier.wait(timeout=5)

            def execute():
                try:
                    operator_orders.advance_order(stale, actor="lab", expected_revision=base, target_status="preparing")
                except operator_orders.OrderStateConflict:
                    return {"outcome": "not_applied"}, 409
                return {"outcome": "applied"}, 200

            return remote_mutations.run_idempotent_mutation(scope="lab.distinct-intentions", key=key, fingerprint=base, execute=execute)
        finally:
            connections.close_all()

    # This assay proves local serialization, not downstream/provider delivery.
    with patch.dict(lifecycle._PHASE_HANDLERS, {"on_preparing": lambda *_: None}):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ["first", "second"]))
    assert sorted(result.response_code for result in results) == [200, 409]
    order.refresh_from_db()
    assert order.status == "preparing"
    assert order.events.filter(type="status_changed").count() == 1
