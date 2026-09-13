"""Remote CFM/DSP reconcile legal steps once, without manufacturing preparation."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from shopman.orderman.models import Directive, Fulfillment, IdempotencyKey, Order

from shopman.shop import lifecycle
from shopman.shop.config import ChannelConfig
from shopman.shop.services import ifood_cancellation, ifood_events, operator_orders, webhook_idempotency

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def external_channel():
    config = ChannelConfig(
        payment=ChannelConfig.Payment(method="external", timing="external"),
        fulfillment=ChannelConfig.Fulfillment(prep_start="operator"),
    )
    with (
        override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"}),
        patch.object(ChannelConfig, "for_channel", return_value=config),
    ):
        yield


def _order(status="new", fulfillment_type="delivery"):
    return Order.objects.create(
        ref="IFD-PROGRESS", channel_ref="ifood", external_ref="remote-order", status=status,
        data={"fulfillment_type": fulfillment_type, "ifood": {"delivered_by": "IFOOD"},
              "payment": {"method": "external", "gateway": "ifood", "status": "paid"}},
    )


def _event(code, event_id=None):
    return {"id": event_id or f"event-{code}", "code": code, "orderId": "remote-order", "merchantId": "test-store"}


def _claim_status(event):
    return IdempotencyKey.objects.get(
        scope="webhook:ifood", key=f"event:{webhook_idempotency.stable_webhook_key(event['id'])}",
    ).status


@pytest.mark.parametrize("code,target,initial,marker", [
    ("CFM", "accepted", "new", "remote_confirmed"),
    ("CONFIRMED", "accepted", "new", "remote_confirmed"),
    ("DSP", "dispatched", "ready", "remote_dispatched"),
    ("DISPATCHED", "dispatched", "ready", "remote_dispatched"),
])
def test_remote_step_uses_canonical_transition_and_dedupes_without_echo(code, target, initial, marker):
    order = _order(initial)
    event = _event(code)
    with (
        patch.object(ifood_events, "acknowledge", return_value=True) as ack,
        patch.object(operator_orders, "confirm_order", wraps=operator_orders.confirm_order) as confirm,
        patch.object(operator_orders, "advance_order", wraps=operator_orders.advance_order) as advance,
    ):
        assert ifood_events.process_events([event])["ingested"] == 1
        ack.assert_called_once_with([event["id"]])
        order.refresh_from_db()
        assert order.status == target
        evidence = order.data["ifood"][marker]
        assert evidence["event_id"] == event["id"]
        assert evidence["observed_at"]
        assert _claim_status(event) == "done"
        transitions = list(order.events.filter(type="status_changed").values_list("payload", flat=True))
        assert [change["new_status"] for change in transitions] == [target]
        assert not Directive.objects.filter(topic="ifood.status_callback").exists()
        if target == "dispatched":
            assert order.fulfillments.get().status == Fulfillment.Status.DISPATCHED
        assert ifood_events.process_events([event])["deduped"] == 1
        assert ifood_events.process_events([_event(code, "different-id")])["deduped"] == 1
        assert order.events.filter(type="status_changed").count() == 1
        order.refresh_from_db()
        assert order.data["ifood"][marker] == evidence
        assert confirm.call_count == (1 if target == "accepted" else 0)
        assert advance.call_count == (1 if target == "dispatched" else 0)


@pytest.mark.parametrize("code,initial,target", [("CFM", "new", "accepted"), ("DSP", "ready", "dispatched")])
def test_remote_event_before_placed_can_retry_after_materialization(code, initial, target):
    event = _event(code)
    with patch.object(ifood_events, "acknowledge", return_value=True) as ack:
        assert ifood_events.process_events([event])["failed"] == 1
        ack.assert_not_called()
        assert _claim_status(event) == "failed"
        order = _order(initial)
        assert ifood_events.process_events([event])["ingested"] == 1
        ack.assert_called_once_with([event["id"]])
        order.refresh_from_db()
        assert order.status == target


@pytest.mark.parametrize("initial", ["new", "accepted", "preparing"])
def test_dsp_before_local_readiness_does_not_invent_preparation(initial):
    order = _order(initial)
    event = _event("DSP")
    with patch.object(ifood_events, "acknowledge") as ack:
        assert ifood_events.process_events([event])["failed"] == 1
    ack.assert_not_called()
    order.refresh_from_db()
    assert order.status == initial
    assert "remote_dispatched" not in order.data["ifood"]
    assert not order.events.exists()
    assert not order.fulfillments.exists()
    assert _claim_status(event) == "failed"


def test_dsp_for_pickup_is_not_acknowledged_as_dispatch():
    order = _order("ready", "pickup")
    with patch.object(ifood_events, "acknowledge") as ack:
        assert ifood_events.process_events([_event("DSP")])["failed"] == 1
    ack.assert_not_called()
    order.refresh_from_db()
    assert order.status == "ready"


@pytest.mark.parametrize("code,status", [("CFM", "preparing"), ("DSP", "delivered"), ("CFM", "cancelled"), ("DSP", "completed")])
def test_late_event_does_not_regress_status_and_retains_evidence(code, status):
    order = _order(status)
    with patch.object(ifood_events, "acknowledge", return_value=True):
        assert ifood_events.process_events([_event(code)])["deduped"] == 1
    order.refresh_from_db()
    assert order.status == status
    assert order.data["ifood"]["remote_confirmed" if code == "CFM" else "remote_dispatched"]
    assert not order.events.exists()


@pytest.mark.parametrize("code,initial,service", [("CFM", "new", "confirm_order"), ("DSP", "ready", "advance_order")])
def test_service_failure_rolls_back_remote_marker_state_and_allows_retry(code, initial, service):
    order = _order(initial)
    event = _event(code)
    original = getattr(operator_orders, service)

    def fail_after_transition(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("transient failure after transition")

    with (
        patch.object(ifood_events, "acknowledge") as ack,
        patch.object(operator_orders, service, side_effect=fail_after_transition),
    ):
        assert ifood_events.process_events([event])["failed"] == 1
    ack.assert_not_called()
    order.refresh_from_db()
    assert order.status == initial
    assert order.data["ifood"] == {"delivered_by": "IFOOD"}
    assert not order.events.exists()
    assert not order.fulfillments.exists()
    assert _claim_status(event) == "failed"
    with patch.object(ifood_events, "acknowledge", return_value=True):
        assert ifood_events.process_events([event])["ingested"] == 1


def test_pending_cancellation_keeps_cfm_retryable():
    order = _order()
    order.data[ifood_cancellation.KEY] = {"state": "sent"}
    order.save(update_fields=["data"])
    with patch.object(ifood_events, "acknowledge") as ack:
        assert ifood_events.process_events([_event("CFM")])["failed"] == 1
    ack.assert_not_called()
    order.refresh_from_db()
    assert order.status == "new"
    assert "remote_confirmed" not in order.data["ifood"]


def test_ifood_delivery_concludes_after_remote_dispatch():
    order = _order("ready")
    with patch.object(ifood_events, "acknowledge", return_value=True) as ack:
        assert ifood_events.process_events([_event("DSP"), _event("CON")])["ingested"] == 2
    ack.assert_called_once_with(["event-DSP", "event-CON"])
    order.refresh_from_db()
    assert order.status == "completed"
    assert order.fulfillments.get().status == Fulfillment.Status.DELIVERED
    assert not Directive.objects.filter(topic="ifood.status_callback").exists()


def test_confirmation_schedules_accepted_lifecycle_once_without_fabricated_preparation(django_capture_on_commit_callbacks):
    order = _order()
    accepted_phase = MagicMock()
    # Keep the real signal/on_commit wiring and intercept only the phase's
    # downstream work, proving duplicate CFM does not dispatch the phase twice.
    with (
        patch.object(ifood_events, "acknowledge", return_value=True),
        patch.dict(lifecycle._PHASE_HANDLERS, {"on_accepted": accepted_phase}),
        patch.object(lifecycle, "_dispatch_physical_work") as kitchen,
        django_capture_on_commit_callbacks(execute=True),
    ):
        assert ifood_events.process_events([_event("CFM"), _event("CFM", "cfm-2")])["deduped"] == 1
    order.refresh_from_db()
    assert order.status == "accepted"
    accepted_phase.assert_called_once()
    kitchen.assert_not_called()
    assert order.events.filter(type="status_changed").count() == 1
