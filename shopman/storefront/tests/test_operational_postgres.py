"""Independent connections; SQLite must never count as evidence of row locks."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connection, connections

requires_postgres = pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires independent PostgreSQL connections")

pytestmark = [
    pytest.mark.django_db(transaction=True),
    requires_postgres,
]


def test_concurrent_local_intention_produces_one_effect_and_two_equal_receipts():
    from shopman.orderman.models import Order

    from shopman.shop.services.remote_mutations import run_idempotent_mutation

    barrier = Barrier(2)

    def run():
        try:
            barrier.wait(timeout=10)

            def effect():
                Order.objects.create(ref="PG-INTENTION", channel_ref="web")
                return {"order_ref": "PG-INTENTION"}, 201

            return run_idempotent_mutation(
                scope="pg-local-proof", key="one", payload={"qty": 1}, execute=effect, local_atomic=True
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run) for _ in range(2)]
        results = [job.result(timeout=30) for job in jobs]
    assert Order.objects.filter(ref="PG-INTENTION").count() == 1
    assert [result.response_code for result in results] == [201, 201]
    assert sum(result.replayed for result in results) == 1
    assert results[0].response_body == results[1].response_body


def test_concurrent_cart_metadata_preserves_untouched_fields_and_both_choices():
    from shopman.orderman.models import Session

    from shopman.shop.services.cart import set_delivery_draft, set_loyalty_redeem
    from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

    _seed_surface()
    cart = Session.objects.create(
        session_key="PG-CONTEXT", channel_ref="web", data={"order_notes": "Preserve this choice"}
    )
    barrier = Barrier(2)

    def run(effect):
        try:
            barrier.wait(timeout=10)
            effect()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [
            pool.submit(
                run,
                lambda: set_delivery_draft(session_key=cart.session_key, channel_ref="web", fulfillment_type="pickup"),
            ),
            pool.submit(run, lambda: set_loyalty_redeem(session_key=cart.session_key, channel_ref="web", redeem_q=10)),
        ]
        for job in jobs:
            job.result(timeout=30)
    cart.refresh_from_db()
    assert cart.data["order_notes"] == "Preserve this choice"
    assert cart.data["fulfillment_type"] == "pickup"
    assert cart.data["loyalty"]["redeem_points_q"] == 10
    assert cart.rev == 2
