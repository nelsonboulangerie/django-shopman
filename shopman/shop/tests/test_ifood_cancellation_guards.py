"""Queued cancellation prevents timeout acceptance and stale callback echoes."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from shopman.orderman.exceptions import InvalidTransition
from shopman.orderman.models import Order

from shopman.shop.handlers.confirmation import _transition_if_still_new
from shopman.shop.handlers.ifood_status import IFoodStatusCallbackHandler
from shopman.shop.lifecycle import ensure_confirmable
from shopman.shop.services import ifood_callbacks, ifood_cancellation, ifood_events


@pytest.mark.parametrize("cancel_request", [
    {"state": "queued"}, {"state": "sent"}, {"state": "error", "retryable": True},
])
@pytest.mark.parametrize("approved", [False, True])
def test_pending_cancellation_blocks_availability_and_external_payment_bypasses(cancel_request, approved):
    order = SimpleNamespace(
        ref="IFD-GUARD", status="new", channel_ref="ifood",
        data={ifood_cancellation.KEY: cancel_request, "availability_decision": {"approved": approved, "decisions": []}},
    )
    config = SimpleNamespace(payment=SimpleNamespace(timing="external"))
    with pytest.raises(InvalidTransition) as raised:
        ensure_confirmable(order, channel_config=config)
    assert raised.value.code == "ifood_cancellation_pending"


def test_nonretryable_rejection_does_not_leave_confirmation_blocked():
    order = SimpleNamespace(
        ref="IFD-GUARD", status="new", channel_ref="ifood",
        data={ifood_cancellation.KEY: {"state": "error", "retryable": False}},
    )
    ensure_confirmable(order, channel_config=SimpleNamespace(payment=SimpleNamespace(timing="external")))


@pytest.mark.django_db
def test_timeout_rechecks_pending_cancellation_after_loading_stale_order():
    stale = Order.objects.create(ref="IFD-GUARD", channel_ref="ifood", external_ref="ifood-order", status="new")
    Order.objects.filter(pk=stale.pk).update(data={ifood_cancellation.KEY: {"state": "queued"}})
    with (
        patch("shopman.shop.lifecycle.ensure_payment_captured"),
        patch("shopman.shop.services.payment.lock_order_payment"),
        pytest.raises(InvalidTransition) as raised,
    ):
        _transition_if_still_new(stale, Order.Status.ACCEPTED)
    assert raised.value.code == "ifood_cancellation_pending"
    stale.refresh_from_db()
    assert stale.status == Order.Status.NEW
    assert not stale.events.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["accepted", "ready", "dispatched", "cancelled"])
def test_legacy_callback_queued_before_can_does_not_call_provider_after_can(status):
    order = Order.objects.create(
        ref="IFD-GUARD", channel_ref="ifood", external_ref="ifood-order", status="new", data={},
    )
    payload = {"order_ref": order.ref, "ifood_order_id": order.external_ref, "status": status}
    with patch.object(ifood_events, "acknowledge", return_value=True):
        summary = ifood_events.process_events([{"id": "can-guard", "code": "CAN", "orderId": order.external_ref}])
    assert summary["ingested"] == 1
    order.refresh_from_db()
    assert order.status == "cancelled"
    assert order.data["cancellation_reason"] == "Cancelamento confirmado pelo iFood"
    with patch.object(ifood_callbacks, "send_for_status") as send:
        IFoodStatusCallbackHandler().handle(message=SimpleNamespace(payload=payload), ctx={})
    send.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("confirmed_remotely", [False, True])
def test_legacy_cancellation_without_order_ref_preserves_local_cancellation_delivery(confirmed_remotely):
    Order.objects.create(
        ref="IFD-GUARD", channel_ref="ifood", external_ref="ifood-order", status="cancelled",
        data={"ifood_cancelled": confirmed_remotely},
    )
    payload = {"ifood_order_id": "ifood-order", "status": "cancelled"}
    with patch.object(ifood_callbacks, "send_for_status", return_value=True) as send:
        IFoodStatusCallbackHandler().handle(message=SimpleNamespace(payload=payload), ctx={})
    assert send.call_count == (0 if confirmed_remotely else 1)


@pytest.mark.django_db
def test_can_marks_already_cancelled_legacy_order_and_suppresses_queued_callback():
    order = Order.objects.create(
        ref="IFD-GUARD", channel_ref="ifood", external_ref="ifood-order", status="cancelled", data={},
    )
    with patch.object(ifood_events, "acknowledge", return_value=True):
        assert ifood_events.process_events([{
            "id": "can-legacy", "code": "CAN", "orderId": order.external_ref,
        }])["deduped"] == 1
    order.refresh_from_db()
    assert order.data["ifood_cancelled"] is True
    payload = {"order_ref": order.ref, "ifood_order_id": order.external_ref, "status": "cancelled"}
    with patch.object(ifood_callbacks, "send_for_status") as send:
        IFoodStatusCallbackHandler().handle(message=SimpleNamespace(payload=payload), ctx={})
    send.assert_not_called()
