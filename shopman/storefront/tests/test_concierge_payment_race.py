"""Table 8.2: real PostgreSQL PIX callback / unpaid timeout overlap."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import connection, connections
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Channel
from shopman.shop.services import cancellation, pix_confirmation

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="Requires independent PostgreSQL connections"
)

pytestmark = requires_postgres


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("winner", ["callback", "cancel"])
def test_pix_callback_and_unpaid_cancel_preserve_money_and_terminal_truth(winner, monkeypatch):
    assert connection.vendor == "postgresql", "This proof requires PostgreSQL"
    Channel.objects.create(ref="race-pix", name="Synthetic PIX race")
    intent = PaymentService.create_intent("PIX-RACE", 1000, "pix", gateway="mock", gateway_id="synthetic-pix-race")
    order = Order.objects.create(ref="PIX-RACE", channel_ref="race-pix", status="new", total_q=1000,
        data={"payment": {"method": "pix", "intent_ref": intent.ref}})
    PaymentService.authorize(intent.ref, gateway_id=intent.gateway_id)
    paused, resume = Event(), Event()
    capture = pix_confirmation._capture_charge

    def capture_at_barrier(*args, **kwargs):
        if winner == "callback":
            result = capture(*args, **kwargs)
        paused.set()
        assert resume.wait(10)
        return result if winner == "callback" else capture(*args, **kwargs)

    monkeypatch.setattr(pix_confirmation, "_capture_charge", capture_at_barrier)

    def callback():
        try:
            pix_confirmation.confirm_pix(txid=intent.gateway_id, e2e_id="synthetic-e2e", amount="10.00")
        finally:
            connections.close_all()

    def cancel():
        try:
            return cancellation.cancel(Order.objects.get(pk=order.pk), "pix_timeout", actor="synthetic-timeout",
                expected_unpaid_intent_ref=intent.ref)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        paid = pool.submit(callback)
        try:
            assert paused.wait(10)
            cancelled = pool.submit(cancel).result(timeout=10)
        finally:
            resume.set()
        paid.result(timeout=10)
    # The identical provider event must never account for a second payment.
    pix_confirmation.confirm_pix(txid=intent.gateway_id, e2e_id="synthetic-e2e", amount="10.00")
    order.refresh_from_db()
    intents = PaymentService.get_by_order(order.ref)
    assert sum(PaymentService.captured_total(item.ref) for item in intents) == 1000
    assert order.data["payment"]["pix_receipts"] == {"synthetic-e2e": 1000}
    assert cancelled is (winner == "cancel")
    if winner == "cancel":
        assert order.status == "cancelled"
        assert sum(PaymentService.refunded_total(item.ref) for item in intents) == 1000
        assert OperatorAlert.objects.filter(order_ref=order.ref, type="payment_after_cancel").exists()
    else:
        assert order.status == "new"
        assert sum(PaymentService.refunded_total(item.ref) for item in intents) == 0
    assert not OperatorAlert.objects.filter(order_ref=order.ref, type="payment_insufficient").exists()


@pytest.mark.django_db(transaction=True)
def test_late_pix_replay_recovers_booked_money_after_interrupted_settlement(monkeypatch):
    from shopman.shop import lifecycle

    assert connection.vendor == "postgresql"
    Channel.objects.create(ref="late-pix", name="Synthetic late PIX")
    intent = PaymentService.create_intent("PIX-LATE", 1000, "pix", gateway="mock", gateway_id="synthetic-pix-late")
    order = Order.objects.create(ref="PIX-LATE", channel_ref="late-pix", status="new", total_q=1000,
        data={"payment": {"method": "pix", "intent_ref": intent.ref}})
    assert cancellation.cancel(order, "pix_timeout", expected_unpaid_intent_ref=intent.ref)
    dispatch = lifecycle.dispatch

    def interrupt_settlement(current, phase):
        if phase == "on_paid":
            raise RuntimeError("synthetic interruption after booking")
        return dispatch(current, phase)

    monkeypatch.setattr(lifecycle, "dispatch", interrupt_settlement)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        pix_confirmation.confirm_pix(txid=intent.gateway_id, e2e_id="synthetic-late", amount="10.00")
    intents = list(PaymentService.get_by_order(order.ref))
    assert sum(PaymentService.captured_total(item.ref) for item in intents) == 1000
    assert sum(PaymentService.refunded_total(item.ref) for item in intents) == 0
    monkeypatch.setattr(lifecycle, "dispatch", dispatch)
    for _ in range(2):
        pix_confirmation.confirm_pix(txid=intent.gateway_id, e2e_id="synthetic-late", amount="10.00")
    assert PaymentService.get_by_order(order.ref).count() == 2
    assert sum(PaymentService.captured_total(item.ref) for item in intents) == 1000
    assert sum(PaymentService.refunded_total(item.ref) for item in intents) == 1000
    assert OperatorAlert.objects.filter(order_ref=order.ref, type="payment_after_cancel").count() == 1
    order.refresh_from_db()
    assert order.status == "cancelled"
