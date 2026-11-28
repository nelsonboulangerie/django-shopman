"""Conciliação do dia × pedido não retirado (WP-G11).

Cancelado com saldo capturado é erro crítico (``terminal_order_with_captured_balance``):
dinheiro do cliente que não voltou. No "Não retirado" a loja RETÉM, por decisão
assinada, o valor das linhas que se perderam: saldo igual ao retido é o estado
certo. Qualquer outro saldo continua sendo erro.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.backstage.models import DayClosing
from shopman.backstage.services.financial_reconciliation import build_financial_reconciliation

pytestmark = pytest.mark.django_db

CODE = "terminal_order_with_captured_balance"


def _not_picked_up(ref: str, *, captured_q: int, refunded_q: int, retained_q: int | None) -> Order:
    data = {"payment": {"method": "pix", "intent_ref": f"PAY-{ref}"}}
    if retained_q is not None:
        data["cancellation_reason_key"] = "not_picked_up"
        data["no_show"] = {"paid_q": captured_q, "refund_q": captured_q - retained_q, "retained_q": retained_q}
    order = Order.objects.create(ref=ref, channel_ref="web", status=Order.Status.CANCELLED, total_q=captured_q, data=data)
    intent = PaymentIntent.objects.create(
        ref=f"PAY-{ref}", order_ref=ref, method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.REFUNDED if refunded_q else PaymentIntent.Status.CAPTURED,
        amount_q=captured_q, gateway="efi", gateway_id=f"gw-{ref}",
    )
    PaymentTransaction.objects.create(
        intent=intent, type=PaymentTransaction.Type.CAPTURE, amount_q=captured_q, gateway_id=f"gw-{ref}",
    )
    if refunded_q:
        PaymentTransaction.objects.create(
            intent=intent, type=PaymentTransaction.Type.REFUND, amount_q=refunded_q, gateway_id=f"rf-{ref}",
        )
    return order


def _codes(order: Order) -> list[str]:
    today = timezone.localdate()
    DayClosing.objects.get_or_create(
        date=today, defaults={"closed_by": User.objects.create_user(f"recon-{order.ref}", is_staff=True), "data": {"items": []}},
    )
    report = build_financial_reconciliation(reconciliation_date=today, require_closing=True)
    return [issue.code for issue in report.issues if issue.order_ref == order.ref]


def test_balance_equal_to_the_retained_amount_is_not_an_error():
    order = _not_picked_up("NS-RECON-OK", captured_q=4870, refunded_q=1870, retained_q=3000)

    assert CODE not in _codes(order)


def test_everything_retained_and_nothing_refunded_is_not_an_error():
    order = _not_picked_up("NS-RECON-TUDO", captured_q=3000, refunded_q=0, retained_q=3000)

    assert CODE not in _codes(order)


def test_refund_that_did_not_leave_yet_is_still_an_error():
    """O devolvível ainda está na casa: saldo maior que o retido."""
    order = _not_picked_up("NS-RECON-PENDENTE", captured_q=4870, refunded_q=0, retained_q=3000)

    assert CODE in _codes(order)


def test_balance_below_the_retained_amount_is_still_an_error():
    """Voltou dinheiro a mais: sobrou menos do que a loja devia reter."""
    order = _not_picked_up("NS-RECON-A-MAIS", captured_q=4870, refunded_q=3000, retained_q=3000)

    assert CODE in _codes(order)


def test_common_cancelled_order_with_balance_is_still_an_error():
    order = _not_picked_up("NS-RECON-COMUM", captured_q=4870, refunded_q=0, retained_q=None)

    assert CODE in _codes(order)
