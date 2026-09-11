"""A payment observation must remain true until the local transition commits."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from threading import Event

import pytest
from django.db import connection, connections
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman.service import PaymentService

from shopman.shop.handlers.confirmation import ConfirmationTimeoutHandler
from shopman.shop.models import Channel
from shopman.shop.services import operator_orders, payment


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["confirm", "advance", "timeout"])
def test_refund_cannot_invalidate_payment_between_guard_and_transition(operation, monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Payment guard interleaving requires PostgreSQL")
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *args: None)
    Channel.objects.create(ref="guard-lock", name="Synthetic guard", config={"payment": {"timing": "at_commit"}})
    intent = PaymentService.create_intent("GUARD-LOCK", 1500, "pix")
    order = Order.objects.create(ref="GUARD-LOCK", status="accepted" if operation == "advance" else "new", channel_ref="guard-lock", total_q=1500,
        data={"payment": {"method": "pix", "intent_ref": intent.ref}, "availability_decision": {"approved": True, "decisions": []}})
    PaymentService.authorize(intent.ref)
    PaymentService.capture(intent.ref)
    directive = Directive.objects.create(topic="confirmation.timeout", payload={"order_ref": order.ref, "action": "confirm",
        "expires_at": (timezone.now() - timedelta(seconds=1)).isoformat()})
    evaluated, resume, refund_started = Event(), Event(), Event()
    funds_at_transition = []
    original = Order.transition_status

    def pause_before_transition(instance, target, *args, **kwargs):
        if kwargs.get("actor") in {"operator:guard", "confirmation.timeout"}:
            evaluated.set()
            assert resume.wait(10)
            funds_at_transition.append(payment.has_sufficient_captured_payment(instance))
        return original(instance, target, *args, **kwargs)

    monkeypatch.setattr(Order, "transition_status", pause_before_transition)

    def command():
        try:
            current = Order.objects.get(pk=order.pk)
            if operation == "confirm":
                operator_orders.confirm_order(current, actor="operator:guard")
            elif operation == "advance":
                operator_orders.advance_order(current, actor="operator:guard")
            else:
                ConfirmationTimeoutHandler().handle(message=Directive.objects.get(pk=directive.pk), ctx={})
        finally:
            connections.close_all()

    def refund():
        try:
            refund_started.set()
            PaymentService.refund(intent.ref, amount_q=1500)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        transition = pool.submit(command)
        try:
            assert evaluated.wait(10)
            returned = pool.submit(refund)
            assert refund_started.wait(10)
            try:
                returned.result(timeout=0.5)
            except TimeoutError:
                pass  # Refund may correctly wait until the command commits.
        finally:
            resume.set()
        transition.result(timeout=10)
        returned.result(timeout=10)
    assert funds_at_transition == [True]
    assert PaymentService.refunded_total(intent.ref) == 1500
