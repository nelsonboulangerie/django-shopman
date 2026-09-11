"""Independent-connection witnesses for H03, using synthetic local state only."""
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
from shopman.shop.services import customer_orders, operator_orders


@pytest.mark.django_db
@pytest.mark.parametrize("intervening", ["captured", "preparing"])
def test_self_cancel_revalidates_the_canonical_policy_after_the_surface_read(intervening):
    intent = PaymentService.create_intent("SELF-CANCEL-RACE", 1500, "pix")
    order = Order.objects.create(ref="SELF-CANCEL-RACE", status="accepted", total_q=1500,
        data={"payment": {"method": "pix", "intent_ref": intent.ref}})
    assert customer_orders.can_cancel(order)
    if intervening == "captured":
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
    else:
        Order.objects.filter(pk=order.pk).update(status="preparing")
    customer_orders.cancel(order)
    order.refresh_from_db()
    assert order.status == ("accepted" if intervening == "captured" else "preparing")
    assert not order.events.filter(type="status_changed").exists()


@pytest.mark.django_db(transaction=True)
def test_successful_operator_confirmation_cannot_be_overruled_by_stale_timeout(monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Independent row locks require PostgreSQL")
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *args: None)
    Channel.objects.create(ref="h03-confirm", name="Synthetic confirmation", config={"payment": {"timing": "external"}})
    order = Order.objects.create(ref="CONFIRM-TIMEOUT-RACE", status="new", channel_ref="h03-confirm", total_q=1500,
        data={"payment": {"method": "cash"}, "availability_decision": {"approved": True, "decisions": []}})
    directive = Directive.objects.create(topic="confirmation.timeout", payload={"order_ref": order.ref, "action": "cancel",
        "expires_at": (timezone.now() - timedelta(seconds=1)).isoformat()})
    evaluated, resume = Event(), Event()
    transition = Order.transition_status

    def pause_timeout(instance, status, *args, **kwargs):
        if kwargs.get("actor") == "confirmation.timeout":
            evaluated.set()
            assert resume.wait(10)
        return transition(instance, status, *args, **kwargs)

    monkeypatch.setattr(Order, "transition_status", pause_timeout)

    def timeout():
        try:
            ConfirmationTimeoutHandler().handle(message=Directive.objects.get(pk=directive.pk), ctx={})
        finally:
            connections.close_all()

    def confirm():
        try:
            try:
                operator_orders.confirm_order(Order.objects.get(pk=order.pk), actor="operator:h03")
                return True
            except (ValueError, operator_orders.OrderStateConflict):
                return False
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        automatic = pool.submit(timeout)
        try:
            assert evaluated.wait(10)
            explicit = pool.submit(confirm)
            try:
                explicit.result(timeout=0.5)
            except TimeoutError:
                pass  # A serialized timeout is allowed to win before the operator.
        finally:
            resume.set()
        automatic.result(timeout=10)
        accepted = explicit.result(timeout=10)
    order.refresh_from_db()
    # Either decision can win the lock. A reported operator success must persist.
    assert order.status == ("accepted" if accepted else "cancelled")
    assert order.events.filter(type="status_changed").count() == 1


@pytest.mark.django_db
def test_customer_api_reports_refusal_when_capture_wins_after_its_read(client, monkeypatch):
    from shopman.storefront.services import orders as surface_orders

    intent = PaymentService.create_intent("CUSTOMER-API-RACE", 1500, "pix")
    order = Order.objects.create(ref="CUSTOMER-API-RACE", status="accepted", total_q=1500,
        data={"payment": {"method": "pix", "intent_ref": intent.ref}})
    session = client.session
    session[customer_orders.ORDER_ACCESS_SESSION_KEY] = [order.ref]
    session.save()
    original = surface_orders.can_cancel

    def capture_after_read(current):
        allowed = original(current)
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        return allowed

    monkeypatch.setattr(surface_orders, "can_cancel", capture_after_read)
    response = client.post(f"/api/v1/orders/{order.ref}/cancel/", {}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="customer-race")
    assert response.status_code == 409, response.content
    assert response.json()["error_code"] == "order_not_cancellable"
    order.refresh_from_db()
    assert order.status == "accepted"
    assert not order.events.filter(type="status_changed").exists()
