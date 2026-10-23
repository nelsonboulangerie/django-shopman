# ruff: noqa
# Prova do laudo docs/reports/2026-10-23-laudo-adversarial-go-live.md: PASSA enquanto o defeito existe.
"""Simula a corrida de dois 'Devolvi em dinheiro': o 2º leu o saldo antes do 1º gravar."""
import pytest
from shopman.cashman import Entry
from shopman.orderman.models import Order
from shopman.payman.models import PaymentTransaction

from shopman.shop.services import payment as payment_service
from shopman.shop.tests.test_estorno_na_maquininha import _Balcao

pytestmark = pytest.mark.django_db


def test_stale_balance_second_refund_cash_writes_second_ledger_line(monkeypatch):
    balcao = _Balcao()
    order = balcao.vender(client_request_id="glr-race", items=[{"sku": "POS-ITEM", "name": "x", "qty": 1, "unit_price_q": 1200}], payment_method="cash", tendered_q=1200)
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    order.refresh_from_db()

    first = payment_service.refund_cash(order, shift=balcao.shift, actor=balcao.operator, approved_by=balcao.manager)
    assert first == 1200
    # 2º request: leu saldo E contagem de refunds antes do commit do 1º (sem lock)
    real_count = PaymentTransaction.objects.filter
    monkeypatch.setattr(payment_service, "_payman_refundable_amount", lambda ref: 1200)
    class _Q:
        def __init__(self, qs): self.qs = qs
        def count(self): return 0
    import shopman.payman.models as pm
    orig_filter = pm.PaymentTransaction.objects.filter
    monkeypatch.setattr(pm.PaymentTransaction.objects, "filter", lambda *a, **k: _Q(None) if k.get("type") == "refund" and "intent__ref" in k else orig_filter(*a, **k))
    second = payment_service.refund_cash(order, shift=balcao.shift, actor=balcao.operator, approved_by=balcao.manager)
    monkeypatch.undo()
    refunds = PaymentTransaction.objects.filter(intent__order_ref=order.ref, type="refund").count()
    lines = list(Entry.objects.filter(kind=Entry.Kind.REFUND, order_ref=order.ref).values_list("amount_q", flat=True))
    assert refunds == 1
    assert lines == [-1200, -1200]
