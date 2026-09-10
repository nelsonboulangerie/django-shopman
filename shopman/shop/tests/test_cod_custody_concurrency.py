"""Synthetic custody witnesses: PostgreSQL books, no physical money or adapter."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth.models import User
from django.db import connection, connections
from shopman.cashman import services as cash
from shopman.cashman.models import Entry, Terminal
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent

from shopman.shop.services import operator_orders


def setup_delivery():
    user = User.objects.create_user(username="custody-lab")
    shifts = [cash.open_shift(operator=user, terminal=Terminal.objects.create(ref=f"lab-{i}", label=f"Lab {i}")) for i in range(2)]
    order = Order.objects.create(ref="COD-LAB", status="dispatched", total_q=1200,
        data={"fulfillment_type": "delivery", "payment": {"method": "cash", "collection": "on_delivery"}})
    return user, shifts, order


@pytest.mark.django_db(transaction=True)
def test_two_custodies_cannot_collect_the_same_delivery():
    if connection.vendor != "postgresql":
        pytest.skip("Independent PostgreSQL connections and row locks required")
    user, shifts, order = setup_delivery()
    barrier = Barrier(2)

    def collect(shift):
        try:
            stale = Order.objects.get(pk=order.pk)
            barrier.wait(timeout=5)
            try:
                operator_orders.settle_delivery_cash(stale, cash_shift=shift, actor=f"operator:{user.username}")
                return "applied"
            except ValueError as exc:
                assert "já foi acertado" in str(exc)
                return "refused"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(collect, shifts))
    assert sorted(results) == ["applied", "refused"]
    assert Entry.objects.filter(order_ref=order.ref, kind="cod_settled").count() == 1
    assert PaymentIntent.objects.filter(order_ref=order.ref, status="captured").count() == 1
    assert order.events.filter(type="payment_collected").count() == 1


@pytest.mark.django_db
def test_stale_order_does_not_duplicate_collection_or_erase_context():
    user, shifts, order = setup_delivery()
    stale = Order.objects.get(pk=order.pk)
    operator_orders.save_kitchen_note(order, notes="Contexto preservado")
    operator_orders.settle_delivery_cash(stale, cash_shift=shifts[0], actor=f"operator:{user.username}")
    order.refresh_from_db()
    assert order.data["kitchen_note"] == "Contexto preservado"
    with pytest.raises(ValueError, match="já foi acertado"):
        operator_orders.settle_delivery_cash(stale, cash_shift=shifts[1], actor=f"operator:{user.username}")
    assert Entry.objects.filter(order_ref=order.ref, kind="cod_settled").count() == 1


@pytest.mark.django_db
def test_closed_custody_refuses_stale_shift_without_payment():
    user, shifts, order = setup_delivery()
    cash.close_shift(shifts[0], counted_q=0, actor=user)
    with pytest.raises(ValueError, match="Abra um turno"):
        operator_orders.settle_delivery_cash(order, cash_shift=shifts[0], actor=f"operator:{user.username}")
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()
    assert not Entry.objects.filter(order_ref=order.ref).exists()


@pytest.mark.django_db
def test_ledger_failure_rolls_back_payment_and_order():
    from unittest.mock import patch

    user, shifts, order = setup_delivery()
    with patch.object(cash, "record", side_effect=RuntimeError("synthetic ledger fault")):
        with pytest.raises(RuntimeError, match="synthetic"):
            operator_orders.settle_delivery_cash(order, cash_shift=shifts[0], actor=f"operator:{user.username}")
    order.refresh_from_db()
    assert "cod_settled_at" not in order.data["payment"]
    assert not PaymentIntent.objects.filter(order_ref=order.ref).exists()
    assert not order.events.filter(type="payment_collected").exists()
