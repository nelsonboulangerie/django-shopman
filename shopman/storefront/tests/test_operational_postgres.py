"""Independent connections; SQLite must never count as evidence of row locks."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connection, connections

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="Requires independent PostgreSQL connections"
)

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


def test_concurrent_stock_moves_create_one_occurrence_and_one_delivery():
    from shopman.shop.models import Channel
    from shopman.storefront.models import StockAlertDelivery, StockAlertOccurrence
    from shopman.storefront.services import stock_alerts

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})
    stock_alerts.subscribe("PG-STOCK-CYCLE", phone="+5543999990088", alert_type="stock_back")
    barrier = Barrier(2)

    def run(source_ref):
        try:
            barrier.wait(timeout=10)
            return stock_alerts._create_eligible_occurrence(
                sku="PG-STOCK-CYCLE",
                event_type="stock_back",
                channel_ref="web",
                source_ref=source_ref,
                available_qty=5,
            )
        finally:
            connections.close_all()

    # This test isolates the transactional occurrence/receipt graph. Provider IO
    # belongs to the directive worker tests and is intentionally absent here.
    with patch("shopman.shop.directives.create_persistently_deduped", return_value=None):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [job.result(timeout=30) for job in [pool.submit(run, "move-A"), pool.submit(run, "move-B")]]

    assert sorted(results) == [0, 1]
    assert StockAlertOccurrence.objects.filter(sku="PG-STOCK-CYCLE").count() == 1
    assert StockAlertDelivery.objects.filter(occurrence__sku="PG-STOCK-CYCLE").count() == 1


def test_concurrent_anonymous_subscribe_grants_new_browser_ownership_once():
    from shopman.shop.models import Channel
    from shopman.storefront.models import StockAlertSubscription
    from shopman.storefront.services import stock_alerts

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})
    barrier = Barrier(2)

    def run():
        try:
            barrier.wait(timeout=10)
            return stock_alerts.subscribe_with_outcome(
                "PG-SUBSCRIBE-OWNERSHIP",
                phone="+5543999990087",
                resume_existing=False,
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [job.result(timeout=30) for job in [pool.submit(run), pool.submit(run)]]

    assert sorted(outcome.created for outcome in outcomes) == [False, True]
    assert len({str(outcome.subscription.ref) for outcome in outcomes}) == 1
    assert StockAlertSubscription.objects.filter(sku="PG-SUBSCRIBE-OWNERSHIP").count() == 1


def test_concurrent_quality_review_releases_one_bake_delivery():
    from shopman.shop.models import Channel
    from shopman.storefront.models import StockAlertDelivery, StockAlertOccurrence
    from shopman.storefront.services import stock_alerts

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})
    stock_alerts.subscribe(
        "PG-QC-BAKE",
        phone="+5543999990089",
        alert_type="production_ready",
    )
    stock_alerts.record_bake_pending("PG-QC-BAKE", source_ref="WO-PG-QC")
    barrier = Barrier(2)

    def run():
        try:
            barrier.wait(timeout=10)
            return stock_alerts.review_bake_ready(
                "PG-QC-BAKE",
                source_ref="WO-PG-QC",
            )
        finally:
            connections.close_all()

    with (
        patch(
            "shopman.shop.services.quality.reviewed_saleable_quantity",
            return_value=Decimal("5"),
        ),
        patch(
            "shopman.storefront.services.sku_state.resolve",
            return_value=SimpleNamespace(
                can_add_to_cart=True,
                available_qty=Decimal("5"),
            ),
        ),
        patch("shopman.shop.directives.create_persistently_deduped", return_value=None),
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [job.result(timeout=30) for job in [pool.submit(run), pool.submit(run)]]

    assert sorted(results) == [0, 1]
    occurrence = StockAlertOccurrence.objects.get(sku="PG-QC-BAKE")
    assert occurrence.status == StockAlertOccurrence.Status.ELIGIBLE
    assert StockAlertDelivery.objects.filter(occurrence=occurrence).count() == 1


@pytest.mark.parametrize("control", ["pause", "cancel"])
def test_subscription_control_race_with_worker_has_one_documented_boundary(control):
    from shopman.shop.models import Channel
    from shopman.shop.protocols import NotificationResult
    from shopman.storefront.models import StockAlertDelivery
    from shopman.storefront.services import stock_alerts
    from shopman.storefront.stock_alert_delivery import StockAlertDeliveryHandler

    Channel.objects.get_or_create(ref="web", defaults={"name": "Web", "is_active": True})
    sub = stock_alerts.subscribe(
        f"PG-CONTROL-{control.upper()}",
        phone=f"+55439999900{91 if control == 'pause' else 92}",
        alert_type="stock_back",
    )
    with patch(
        "shopman.storefront.services.sku_state.resolve",
        return_value=SimpleNamespace(can_add_to_cart=True, available_qty=Decimal("5")),
    ):
        stock_alerts.notify_back_in_stock(sub.sku, source_ref=f"move-{control}")
    delivery = StockAlertDelivery.objects.get(subscription=sub)
    capability = stock_alerts.management_capability(sub)
    barrier = Barrier(2)

    def run_worker():
        try:
            barrier.wait(timeout=10)
            StockAlertDeliveryHandler().handle(
                message=SimpleNamespace(payload={"delivery_id": delivery.pk}),
                ctx={},
            )
        finally:
            connections.close_all()

    def run_control():
        try:
            barrier.wait(timeout=10)
            if control == "pause":
                return stock_alerts.set_paused_by_capability(capability, paused=True)
            return stock_alerts.revoke_by_capability(capability)
        finally:
            connections.close_all()

    with (
        patch(
            "shopman.storefront.services.sku_state.resolve",
            return_value=SimpleNamespace(can_add_to_cart=True, available_qty=Decimal("5")),
        ),
        patch(
            "shopman.shop.notifications.notify",
            return_value=NotificationResult(success=True, message_id="provider-accepted"),
        ) as notify,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        jobs = [pool.submit(run_worker), pool.submit(run_control)]
        for job in jobs:
            job.result(timeout=30)

    sub.refresh_from_db()
    delivery.refresh_from_db()
    if control == "pause":
        assert sub.paused_at is not None
    else:
        assert sub.revoked_at is not None
    assert delivery.status in {
        StockAlertDelivery.Status.ACCEPTED,
        StockAlertDelivery.Status.SUPPRESSED,
    }
    assert notify.call_count == (1 if delivery.status == StockAlertDelivery.Status.ACCEPTED else 0)
