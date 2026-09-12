"""Remote conclusions honor legal handoff transitions and durable replay."""

from unittest.mock import patch

import pytest
from django.test import override_settings
from shopman.orderman.models import Directive, Fulfillment, IdempotencyKey, Order

from shopman.shop.services import ifood_events, operator_orders, webhook_idempotency

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_ifood_config():
    with override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"}):
        yield


def _event(code="CON", event_id="con-1"):
    return {"id": event_id, "code": code, "orderId": "order-1", "merchantId": "test-store"}


def _order(status, fulfillment_type="delivery"):
    return Order.objects.create(
        ref="IFOOD-CON", channel_ref="ifood", external_ref="order-1", status=status,
        data={"fulfillment_type": fulfillment_type, "payment": {"method": "external", "status": "paid"}},
    )


def _claim_status():
    return IdempotencyKey.objects.get(
        scope="webhook:ifood", key=f"event:{webhook_idempotency.stable_webhook_key('con-1')}",
    ).status


@pytest.mark.parametrize("code", ["CON", "CONCLUDED"])
@pytest.mark.parametrize("status,fulfillment_type", [
    (Order.Status.DISPATCHED, "delivery"),
    (Order.Status.DELIVERED, "delivery"),
    (Order.Status.READY, "pickup"),
])
def test_concludes_via_canonical_services_without_outbound_echo(status, fulfillment_type, code):
    order = _order(status, fulfillment_type)
    with (
        patch.object(ifood_events, "acknowledge", return_value=True) as ack,
        patch.object(operator_orders, "confirm_received", wraps=operator_orders.confirm_received) as received,
        patch.object(operator_orders, "advance_order", wraps=operator_orders.advance_order) as advance,
    ):
        assert ifood_events.process_events([_event(code)])["ingested"] == 1
        ack.assert_called_once_with(["con-1"])
        assert received.call_count == (1 if status == Order.Status.DISPATCHED else 0)
        advance.assert_called_once()
        order.refresh_from_db()
        assert order.status == Order.Status.COMPLETED
        assert _claim_status() == "done"
        if status == Order.Status.DISPATCHED:
            assert order.fulfillments.get().status == Fulfillment.Status.DELIVERED
        transitions = list(order.events.filter(type="status_changed").values_list("payload", flat=True))
        assert [e["new_status"] for e in transitions] == (
            ["delivered", "completed"] if status == Order.Status.DISPATCHED else ["completed"]
        )
        assert not Directive.objects.filter(topic="ifood.status_callback").exists()
        event_count = order.events.count()
        assert ifood_events.process_events([_event(code)])["deduped"] == 1
        assert ifood_events.process_events([_event(code, "con-another")])["deduped"] == 1
        assert order.events.count() == event_count
        advance.assert_called_once()


@pytest.mark.parametrize("status,fulfillment_type", [
    (Order.Status.NEW, "delivery"),
    (Order.Status.ACCEPTED, "delivery"),
    (Order.Status.PREPARING, "delivery"),
    (Order.Status.READY, "delivery"),
    (Order.Status.PREPARING, "pickup"),
    (Order.Status.READY, ""),
])
def test_early_conclusion_does_not_manufacture_preparation_or_dispatch(status, fulfillment_type):
    order = _order(status, fulfillment_type)
    with patch.object(ifood_events, "acknowledge") as ack:
        assert ifood_events.process_events([_event()])["failed"] == 1
    ack.assert_not_called()
    order.refresh_from_db()
    assert order.status == status
    assert _claim_status() == "failed"
    assert not order.events.exists()
    assert not Directive.objects.filter(topic="ifood.status_callback").exists()


def test_con_before_placed_retries_after_order_arrives_and_becomes_ready():
    with patch.object(ifood_events, "acknowledge", return_value=True) as ack:
        assert ifood_events.process_events([_event()])["failed"] == 1
        assert _claim_status() == "failed"
        ack.assert_not_called()
        order = _order(Order.Status.PREPARING, "pickup")
        assert ifood_events.process_events([_event()])["failed"] == 1
        ack.assert_not_called()
        order.transition_status(Order.Status.READY, actor="operator")
        assert ifood_events.process_events([_event()])["ingested"] == 1
        ack.assert_called_once_with(["con-1"])
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED


@pytest.mark.parametrize("status", [Order.Status.CANCELLED, Order.Status.RETURNED, Order.Status.COMPLETED])
def test_terminal_order_is_not_reopened(status):
    order = _order(status)
    with patch.object(ifood_events, "acknowledge", return_value=True) as ack:
        assert ifood_events.process_events([_event()])["deduped"] == 1
    ack.assert_called_once_with(["con-1"])
    order.refresh_from_db()
    assert order.status == status
    assert not order.events.exists()


def test_failure_after_delivery_rolls_back_order_fulfillment_and_events_for_retry():
    order = _order(Order.Status.DISPATCHED)
    with (
        patch.object(ifood_events, "acknowledge") as ack,
        patch.object(operator_orders, "advance_order", side_effect=RuntimeError("temporary failure")),
    ):
        assert ifood_events.process_events([_event()])["failed"] == 1
    ack.assert_not_called()
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    assert not order.fulfillments.exists()
    assert not order.events.exists()
    assert _claim_status() == "failed"
    with patch.object(ifood_events, "acknowledge", return_value=True):
        assert ifood_events.process_events([_event()])["ingested"] == 1
