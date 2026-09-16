from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.projections.ifood import operation_summary
from shopman.shop.services import operator_orders

pytestmark = pytest.mark.django_db


def make_order(*, provider="IFOOD", status="ready", facts=None):
    return Order.objects.create(
        ref="IFOOD-TEST-GATE", channel_ref="ifood", external_ref="test-remote-order",
        status=status, total_q=2700,
        data={"fulfillment_type": "delivery", "payment": {"method": "external", "gateway": "ifood"},
              "ifood": {"delivered_by": provider, "order_timing": "IMMEDIATE", **(facts or {})}},
    )


@pytest.mark.parametrize("provider,block", [
    ("IFOOD", operator_orders.AdvanceBlock.IFOOD_WAITING_PICKUP),
    ("", operator_orders.AdvanceBlock.IFOOD_DELIVERY_UNKNOWN),
    ("OTHER", operator_orders.AdvanceBlock.IFOOD_DELIVERY_UNKNOWN),
])
def test_operator_cannot_mark_ifood_pickup_before_remote_evidence(provider, block):
    order = make_order(provider=provider)
    with patch.object(operator_orders.payment_gate, "payment_blocks_transition", return_value=False):
        assert operator_orders.advance_block(order) == block
        with pytest.raises(ValueError):
            operator_orders.advance_order(order, actor="operator:test")
    order.refresh_from_db()
    assert order.status == "ready"
    assert not order.events.exists()


def test_remote_dispatch_evidence_releases_only_the_delivery_guard():
    order = make_order(facts={"remote_dispatched": {"event_id": "dsp-test"}})
    with patch.object(operator_orders.payment_gate, "payment_blocks_transition", return_value=False), patch(
        "shopman.shop.adapters.delivery_devices.needs_card_machine", return_value=False,
    ):
        assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE
    with patch.object(operator_orders.payment_gate, "payment_blocks_transition", return_value=True):
        assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED


def test_same_day_scheduled_order_cannot_start_early():
    future = timezone.now() + timedelta(minutes=30)
    order = make_order(provider="MERCHANT", status="accepted", facts={
        "order_timing": "SCHEDULED", "schedule": {"preparation_start_at": future.isoformat()},
    })
    with patch.object(operator_orders.payment_gate, "payment_blocks_transition", return_value=False):
        assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.IFOOD_SCHEDULE_BLOCKED
        with pytest.raises(ValueError):
            operator_orders.advance_order(order, actor="operator:test")
    order.refresh_from_db()
    assert order.status == "accepted"
    assert not order.events.exists()
    lines = operation_summary(order)
    assert "Entrega própria da loja" in lines
    assert "Pedido agendado no iFood" in lines
    assert any("Início do preparo:" in line for line in lines)


def test_missing_scheduled_time_is_visible_and_blocked():
    order = make_order(status="accepted", facts={"order_timing": "SCHEDULED"})
    with patch.object(operator_orders.payment_gate, "payment_blocks_transition", return_value=False):
        assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.IFOOD_SCHEDULE_BLOCKED
    assert any("horário" in line.lower() for line in operation_summary(order))


@pytest.mark.parametrize("state,retryable", [("queued", False), ("sent", False), ("error", True)])
def test_scheduled_wakeup_waits_without_exhausting_attempts_then_resumes(state, retryable):
    from shopman.orderman.models import Directive

    from shopman.shop.handlers.preorder import PreorderActivateHandler

    order = make_order(status="accepted", facts={
        "order_timing": "SCHEDULED", "schedule": {"preparation_start_at": (timezone.now() - timedelta(minutes=1)).isoformat()},
    })
    order.data["ifood_cancellation_request"] = {"id": "cancel-test", "state": state, "retryable": retryable}
    order.save(update_fields=["data"])
    message = Directive.objects.create(topic="preorder.activate", status="running", attempts=20, payload={"order_ref": order.ref})
    handler = PreorderActivateHandler()
    with patch("shopman.shop.lifecycle.activate_preorder") as activate:
        handler.handle(message=message, ctx={})
        activate.assert_not_called()
    message.refresh_from_db()
    assert message.status == "queued"
    assert message.attempts == 19
    assert message.available_at > timezone.now()
    assert Directive.objects.filter(topic="preorder.activate").count() == 1

    # A definitive rejection releases the same wakeup, without another row.
    order.data["ifood_cancellation_request"].update(state="error", retryable=False)
    order.save(update_fields=["data"])
    with patch("shopman.shop.lifecycle.activate_preorder") as activate:
        handler.handle(message=message, ctx={})
        activate.assert_called_once()
