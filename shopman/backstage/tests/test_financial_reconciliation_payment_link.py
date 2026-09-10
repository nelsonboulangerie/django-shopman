"""Reconciliação diária × link de pagamento vencido.

O caminho normal do link vencido é a Directive ``payment.timeout`` cancelar o
pedido sozinha, depois de perguntar ao gateway. O check ``expired_payment_link``
é a rede para o que escapa dela — worker parado, gateway mudo por horas, pedido
que já estava além de ACCEPTED quando o prazo bateu. Severidade ``warning``: é
um pedido para alguém olhar no fechamento, não um erro de dinheiro.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman.models import PaymentIntent, PaymentTransaction

from shopman.backstage.models import DayClosing
from shopman.backstage.services.financial_reconciliation import build_financial_reconciliation

pytestmark = pytest.mark.django_db


def _closing():
    user = User.objects.create_user("finance-link", password="pw", is_staff=True)
    return DayClosing.objects.create(date=timezone.localdate(), closed_by=user, data={"items": []})


def _link_order(
    *,
    ref: str,
    expires_at,
    order_status=Order.Status.ACCEPTED,
    intent_status=PaymentIntent.Status.PENDING,
    captured: bool = False,
):
    intent_ref = f"PAY-{ref}"
    order = Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=order_status,
        total_q=6300,
        data={
            "origin_channel": "pos",
            "payment": {"method": "link", "intent_ref": intent_ref, "expires_at": expires_at.isoformat()},
        },
    )
    intent = PaymentIntent.objects.create(
        ref=intent_ref,
        order_ref=order.ref,
        method="link",
        status=intent_status,
        amount_q=6300,
        gateway="stripe",
        gateway_id=f"cs_{ref}",
        expires_at=expires_at,
    )
    if captured:
        PaymentTransaction.objects.create(
            intent=intent,
            type=PaymentTransaction.Type.CAPTURE,
            amount_q=6300,
            gateway_id=f"pi_{ref}",
        )
    return order, intent


def _codes(report) -> list[str]:
    return [issue.code for issue in report.issues]


def test_expired_unpaid_link_on_a_live_order_is_a_warning():
    _closing()
    order, intent = _link_order(ref="FIN-LINK-EXP", expires_at=timezone.now() - timedelta(hours=2))

    report = build_financial_reconciliation(reconciliation_date=timezone.localdate(), require_closing=True)

    issue = next(issue for issue in report.issues if issue.code == "expired_payment_link")
    assert issue.severity == "warning"
    assert issue.order_ref == order.ref
    assert issue.intent_ref == intent.ref
    assert issue.context["status"] == Order.Status.ACCEPTED
    assert issue.context["expires_at"] == intent.expires_at.isoformat()
    # Aviso, não erro: o fechamento não trava por um link vencido.
    assert report.has_errors is False


def test_a_link_that_still_stands_is_not_flagged():
    _closing()
    _link_order(ref="FIN-LINK-LIVE", expires_at=timezone.now() + timedelta(hours=20))

    report = build_financial_reconciliation(reconciliation_date=timezone.localdate(), require_closing=True)

    assert "expired_payment_link" not in _codes(report)


def test_the_cancelled_order_is_the_expected_outcome_and_stays_clean():
    """É o que o ``payment.timeout`` produz: link vencido, pedido cancelado, intent cancelado."""
    _closing()
    _link_order(
        ref="FIN-LINK-DONE",
        expires_at=timezone.now() - timedelta(hours=2),
        order_status=Order.Status.CANCELLED,
        intent_status=PaymentIntent.Status.CANCELLED,
    )

    report = build_financial_reconciliation(reconciliation_date=timezone.localdate(), require_closing=True)

    assert "expired_payment_link" not in _codes(report)


def test_a_paid_link_is_not_flagged_even_after_the_deadline():
    _closing()
    _link_order(
        ref="FIN-LINK-PAID",
        expires_at=timezone.now() - timedelta(hours=2),
        intent_status=PaymentIntent.Status.CAPTURED,
        captured=True,
    )

    report = build_financial_reconciliation(reconciliation_date=timezone.localdate(), require_closing=True)

    assert "expired_payment_link" not in _codes(report)


def test_an_intent_that_was_never_a_link_is_not_flagged():
    """O check é do LINK. O Pix vencido tem a própria máquina e o próprio vocabulário."""
    _closing()
    order = Order.objects.create(
        ref="FIN-PIX-EXP",
        channel_ref="web",
        status=Order.Status.NEW,
        total_q=1000,
        data={"payment": {"method": "pix", "intent_ref": "PAY-FIN-PIX-EXP"}},
    )
    PaymentIntent.objects.create(
        ref="PAY-FIN-PIX-EXP",
        order_ref=order.ref,
        method=PaymentIntent.Method.PIX,
        status=PaymentIntent.Status.PENDING,
        amount_q=1000,
        gateway="efi",
        expires_at=timezone.now() - timedelta(hours=2),
    )

    report = build_financial_reconciliation(reconciliation_date=timezone.localdate(), require_closing=True)

    assert "expired_payment_link" not in _codes(report)
