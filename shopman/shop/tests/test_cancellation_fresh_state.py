"""Cancellation must preserve concurrent context and the payment timeout boundary."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.shop.models import Channel
from shopman.shop.services import cancellation, customer_orders, payment

pytestmark = pytest.mark.django_db


def test_cancellation_preserves_concurrently_saved_note():
    order = Order.objects.create(ref="CANCEL-FRESH", status="accepted", data={})
    stale = Order.objects.get(pk=order.pk)
    order.data = {"kitchen_note": "Contexto novo", "payment": {"method": "cash"}}
    order.save(update_fields=["data"])
    assert cancellation.cancel(stale, reason="Teste", actor="lab")
    order.refresh_from_db()
    assert order.data["kitchen_note"] == "Contexto novo"


def test_capture_after_gateway_read_prevents_timeout_cancellation():
    Channel.objects.create(ref="timeout-lab", name="Lab")
    intent = PaymentService.create_intent("TIMEOUT-CAPTURE", 5000, "pix", ref="TIMEOUT-INTENT")
    order = Order.objects.create(ref="TIMEOUT-CAPTURE", channel_ref="timeout-lab", status="accepted", total_q=5000,
        data={"payment": {"method": "pix", "intent_ref": intent.ref,
            "expires_at": (timezone.now() - timedelta(minutes=2)).isoformat()}})

    def capture_after_read(_order):
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        return "unpaid"  # stale gateway response, capture committed meanwhile

    with patch.object(payment, "settle_from_gateway", side_effect=capture_after_read):
        assert customer_orders.resolve_payment_timeout_if_due(order) is False
    order.refresh_from_db()
    assert order.status == "accepted"
    assert PaymentService.captured_total(intent.ref) == 5000
    assert not order.events.filter(type="status_changed").exists()


@pytest.mark.django_db(transaction=True)
def test_capture_in_other_connection_invalidates_timeout_read(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connection, connections

    if connection.vendor != "postgresql":
        pytest.skip("Independent capture requires PostgreSQL")
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *a: None)
    Channel.objects.create(ref="concurrent-timeout", name="Lab")
    intent = PaymentService.create_intent("CONCURRENT-TIMEOUT", 5000, "pix", ref="CONCURRENT-TIMEOUT-INTENT")
    order = Order.objects.create(ref="CONCURRENT-TIMEOUT", channel_ref="concurrent-timeout", status="accepted", total_q=5000,
        data={"payment": {"method": "pix", "intent_ref": intent.ref,
            "expires_at": (timezone.now() - timedelta(minutes=2)).isoformat()}})
    read, resume = Event(), Event()

    def stale_gateway(_order):
        read.set()
        assert resume.wait(10)
        return "unpaid"

    def timeout():
        try:
            return customer_orders.resolve_payment_timeout_if_due(Order.objects.get(pk=order.pk))
        finally:
            connections.close_all()

    monkeypatch.setattr(payment, "settle_from_gateway", stale_gateway)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(timeout)
        try:
            assert read.wait(10)
            PaymentService.authorize(intent.ref)
            PaymentService.capture(intent.ref)
        finally:
            resume.set()
        assert result.result(timeout=10) is False
    order.refresh_from_db()
    assert order.status == "accepted"
    assert PaymentService.captured_total(intent.ref) == 5000
    assert PaymentService.refunded_total(intent.ref) == 0
