"""Out-of-order iFood cancellations remain retryable until PLACED arrives."""

from unittest.mock import patch

import pytest
from django.test import override_settings
from shopman.orderman.models import IdempotencyKey, Order

from shopman.shop.services import cancellation, ifood_events, webhook_idempotency


def _claim_record(event_id):
    return IdempotencyKey.objects.get(
        scope="webhook:ifood",
        key=f"event:{webhook_idempotency.stable_webhook_key(event_id)}",
    )


@pytest.mark.django_db
@override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"})
def test_unknown_order_cancellation_remains_retryable_without_ack():
    event = {"id": "can-missing", "code": "CAN", "orderId": "missing", "merchantId": "test-store"}
    with patch.object(ifood_events, "acknowledge") as acknowledge:
        for _ in range(2):
            summary = ifood_events.process_events([event])
            assert summary["failed"] == 1
            assert summary["ingested"] == summary["deduped"] == 0
            assert _claim_record("can-missing").status == "failed"
    acknowledge.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("same_batch", [True, False])
@override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"})
def test_can_before_placed_cancels_on_redelivery_and_dedupes_replay(same_batch):
    can = {"id": "can-first", "code": "CAN", "orderId": "order-1", "merchantId": "test-store"}
    placed = {"id": "placed-later", "code": "PLC", "orderId": "order-1", "merchantId": "test-store"}

    def materialize_order(payload):
        # Keep real event claims and order persistence; isolate stock/customer
        # lifecycle work and remote fetch from this event-ordering regression.
        return Order.objects.create(
            ref="IFOOD-ORDERING", channel_ref="ifood", external_ref=payload["order_code"],
            status=Order.Status.NEW, data={},
        )

    def apply_cancellation(order, **kwargs):
        order.status = Order.Status.CANCELLED
        order.data.update(kwargs["extra_data"])
        order.save(update_fields=["status", "data"])
        return True

    with (
        patch.object(ifood_events.ifood_orders, "fetch_order", return_value={"id": "order-1"}) as fetch,
        patch.object(ifood_events.ifood_ingest, "ingest", side_effect=materialize_order),
        patch.object(cancellation, "cancel", side_effect=apply_cancellation) as cancel,
        patch.object(ifood_events, "acknowledge", return_value=True) as acknowledge,
    ):
        if same_batch:
            first = ifood_events.process_events([can, placed])
            assert first["failed"] == first["ingested"] == 1
        else:
            assert ifood_events.process_events([can])["failed"] == 1
            acknowledge.assert_not_called()
            assert ifood_events.process_events([placed])["ingested"] == 1

        acknowledge.assert_called_once_with(["placed-later"])
        assert _claim_record("can-first").status == "failed"
        assert Order.objects.get(external_ref="order-1").status == Order.Status.NEW

        acknowledge.reset_mock()
        assert ifood_events.process_events([can])["ingested"] == 1
        acknowledge.assert_called_once_with(["can-first"])
        order = Order.objects.get(external_ref="order-1")
        assert order.status == Order.Status.CANCELLED
        assert order.data["ifood_cancelled"] is True
        assert _claim_record("can-first").status == "done"

        acknowledge.reset_mock()
        replay = ifood_events.process_events([can, placed])
        assert replay["deduped"] == 2
        assert replay["failed"] == 0
        acknowledge.assert_called_once_with(["can-first", "placed-later"])
        assert Order.objects.filter(external_ref="order-1").count() == 1
        cancel.assert_called_once()
        fetch.assert_called_once_with("order-1")
