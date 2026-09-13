"""Official Order workflow: store dispatch, iFood logistics, and remote echoes."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.ifood_status import IFoodStatusCallbackHandler, on_order_status_changed
from shopman.shop.services import ifood_callbacks, ifood_events


@pytest.mark.parametrize(("status", "fulfillment", "owner", "expected"), [
    ("ready", "pickup", "", "readyToPickup"),
    ("ready", "TAKEOUT", "", "readyToPickup"),
    ("ready", "DINE_IN", "", "readyToPickup"),
    ("ready", "delivery", "IFOOD", "readyToPickup"),
    ("ready", "delivery", "MERCHANT", None),
    ("ready", "delivery", "", None),
    ("ready", "delivery", "UNKNOWN", None),
    ("ready", "", "MERCHANT", None),
    ("dispatched", "delivery", "MERCHANT", "dispatch"),
    ("dispatched", "delivery", "IFOOD", None),
    ("dispatched", "delivery", "", None),
    ("dispatched", "delivery", "UNKNOWN", None),
    ("dispatched", "pickup", "MERCHANT", None),
    ("dispatched", "DINE_IN", "MERCHANT", None),
    ("dispatched", "", "MERCHANT", None),
    ("accepted", "", "", "confirm"),
])
def test_send_follows_fulfillment_and_explicit_delivery_owner(status, fulfillment, owner, expected):
    with patch.object(ifood_callbacks, "send_action") as send:
        sent = ifood_callbacks.send_for_status(
            "ifood-order", status, fulfillment_type=fulfillment, delivered_by=owner,
        )
    assert sent is bool(expected)
    if expected:
        send.assert_called_once_with("ifood-order", expected)
    else:
        send.assert_not_called()


@pytest.mark.parametrize("status", ["ready", "dispatched"])
def test_bare_status_does_not_send_logistics_without_context(status):
    with patch.object(ifood_callbacks, "send_action") as send:
        assert ifood_callbacks.send_for_status("ifood-order", status) is False
    send.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(("status", "owner", "expected"), [
    ("ready", "IFOOD", "readyToPickup"),
    ("ready", "MERCHANT", None),
    ("dispatched", "MERCHANT", "dispatch"),
    ("dispatched", "IFOOD", None),
    ("dispatched", "", None),
])
def test_legacy_directive_recovers_order_workflow_even_without_order_ref(status, owner, expected):
    Order.objects.create(
        ref="OLD-IFD", channel_ref="ifood", external_ref="ifood-order", status=status,
        data={"delivery_method": "delivery", "ifood": {"delivered_by": owner}},
    )
    message = SimpleNamespace(payload={"ifood_order_id": "ifood-order", "status": status})
    with patch.object(ifood_callbacks, "send_action") as send:
        IFoodStatusCallbackHandler().handle(message=message, ctx={})
    if expected:
        send.assert_called_once_with("ifood-order", expected)
    else:
        send.assert_not_called()


@pytest.mark.django_db
def test_current_order_owner_overrides_stale_queued_merchant_context():
    order = Order.objects.create(
        ref="OLD-IFD", channel_ref="ifood", external_ref="ifood-order", status="ready",
        data={"fulfillment_type": "delivery", "ifood": {"delivered_by": "IFOOD"}},
    )
    message = SimpleNamespace(payload={
        "order_ref": order.ref, "ifood_order_id": order.external_ref, "status": "dispatched",
        "fulfillment_type": "delivery", "delivered_by": "MERCHANT",
    })
    with patch.object(ifood_callbacks, "send_action") as send:
        IFoodStatusCallbackHandler().handle(message=message, ctx={})
    send.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(("status", "marker"), [
    ("accepted", "remote_confirmed"),
    ("accepted", "remote_dispatched"),
    ("ready", "remote_dispatched"),
    ("dispatched", "remote_dispatched"),
])
def test_remote_evidence_suppresses_already_queued_callback(status, marker):
    order = Order.objects.create(
        ref="REMOTE-IFD", channel_ref="ifood", external_ref="ifood-order", status=status,
        data={"fulfillment_type": "delivery", "ifood": {
            "delivered_by": "MERCHANT", marker: {"event_id": "remote-1", "observed_at": "2026-09-13"},
        }},
    )
    message = SimpleNamespace(payload={"ifood_order_id": order.external_ref, "status": status})
    with patch.object(ifood_callbacks, "send_for_status") as send:
        IFoodStatusCallbackHandler().handle(message=message, ctx={})
    send.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(("status", "actor"), [("accepted", "system:ifood:CFM"), ("dispatched", "system:ifood:DSP")])
def test_remote_actor_does_not_enqueue_echo(status, actor):
    order = Order.objects.create(
        ref="REMOTE-IFD", channel_ref="ifood", external_ref="ifood-order", status=status,
        data={"fulfillment_type": "delivery", "ifood": {"delivered_by": "MERCHANT"}},
    )
    on_order_status_changed(sender=None, order=order, event_type="status_changed", actor=actor)
    assert not Directive.objects.filter(topic="ifood.status_callback").exists()


@pytest.mark.django_db
@pytest.mark.parametrize(("status", "fulfillment", "owner", "queued"), [
    ("ready", "pickup", "", True),
    ("ready", "delivery", "IFOOD", True),
    ("ready", "delivery", "MERCHANT", False),
    ("dispatched", "delivery", "MERCHANT", True),
    ("dispatched", "delivery", "IFOOD", False),
    ("dispatched", "delivery", "", False),
])
def test_signal_queues_only_valid_workflow_and_captures_context(status, fulfillment, owner, queued):
    order = Order.objects.create(
        ref="LOCAL-IFD", channel_ref="ifood", external_ref="ifood-order", status=status,
        data={"fulfillment_type": fulfillment, "ifood": {"delivered_by": owner}},
    )
    on_order_status_changed(sender=None, order=order, event_type="status_changed", actor="operator:a")
    directive = Directive.objects.filter(topic="ifood.status_callback").first()
    assert bool(directive) is queued
    if directive:
        assert directive.payload["fulfillment_type"] == fulfillment
        assert directive.payload["delivered_by"] == owner


@pytest.mark.django_db
def test_simulation_keeps_external_callbacks_inert():
    order = Order.objects.create(
        ref="SIM-IFD", channel_ref="ifood", external_ref="IFOOD-SIM-123", status="accepted",
        data={"fulfillment_type": "delivery", "ifood": {}},
    )
    on_order_status_changed(sender=None, order=order, event_type="status_changed", actor="operator:a")
    assert not Directive.objects.filter(topic="ifood.status_callback").exists()
    with patch.object(ifood_callbacks, "send_action") as send:
        assert ifood_callbacks.send_for_status(order.external_ref, "accepted") is False
    send.assert_not_called()


@pytest.mark.django_db
def test_pickup_conclusion_suppresses_previously_queued_ready_callback():
    order = Order.objects.create(
        ref="PICKUP-CON", channel_ref="ifood", external_ref="pickup-order", status="ready",
        data={"fulfillment_type": "pickup", "payment": {"method": "external", "status": "paid"}},
    )
    on_order_status_changed(sender=None, order=order, event_type="status_changed", actor="operator:a")
    directive = Directive.objects.get(topic="ifood.status_callback", payload__order_ref=order.ref)
    assert directive.payload["status"] == "ready"
    with patch.object(ifood_events, "acknowledge", return_value=True):
        assert ifood_events.process_events([{
            "id": "con-pickup", "code": "CON", "orderId": order.external_ref,
        }])["ingested"] == 1
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED
    assert not ifood_callbacks.remote_status_observed(order, "ready")
    with patch.object(ifood_callbacks, "send_action") as send:
        IFoodStatusCallbackHandler().handle(message=directive, ctx={})
    send.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("terminal", [Order.Status.COMPLETED, Order.Status.RETURNED, Order.Status.CANCELLED])
@pytest.mark.parametrize("callback_status", ["accepted", "ready", "dispatched"])
def test_delayed_progress_callbacks_are_inert_after_terminal_state(terminal, callback_status):
    order = Order.objects.create(
        ref="TERMINAL-IFD", channel_ref="ifood", external_ref="terminal-order", status=terminal,
        data={"fulfillment_type": "delivery", "ifood": {"delivered_by": "MERCHANT"}},
    )
    message = SimpleNamespace(payload={"ifood_order_id": order.external_ref, "status": callback_status})
    with patch.object(ifood_callbacks, "send_for_status") as send:
        IFoodStatusCallbackHandler().handle(message=message, ctx={})
    send.assert_not_called()
