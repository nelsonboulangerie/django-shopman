"""Devolução do resgate: cancelou/devolveu a venda, os pontos resgatados voltam.

O cliente paga parte do pedido com pontos (LoyaltyRedeemModifier no commit +
Directive ``loyalty.redeem`` debita) — sem o restore, o cancelamento devolvia o
dinheiro e engolia os pontos. A devolução espelha o redeem: Directive
``loyalty.restore``, idempotente pela transação ``adjust`` com
``reference="order:{ref}:restore"`` (reference própria — o revoke do mesmo
pedido deduplica por ``adjust`` na reference original), e devolve o que a
transação ``redeem`` registrou — nunca o payload nem a config.
"""

from __future__ import annotations

import pytest
from shopman.guestman.contrib.loyalty.service import LoyaltyService
from shopman.guestman.models import Customer
from shopman.orderman.exceptions import DirectiveTransientError
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.loyalty import (
    LoyaltyEarnHandler,
    LoyaltyRedeemHandler,
    LoyaltyRestoreHandler,
    LoyaltyRevokeHandler,
)

pytestmark = pytest.mark.django_db

CUSTOMER_REF = "CUST-RESTORE-1"


@pytest.fixture
def customer(db):
    customer = Customer.objects.create(
        ref=CUSTOMER_REF, first_name="Bia", phone="+5543999990002"
    )
    LoyaltyService.enroll(CUSTOMER_REF)
    # Saldo prévio de outra compra — é dele que o resgate sai.
    LoyaltyService.earn_points(
        CUSTOMER_REF, points=100, description="compra anterior", reference="order:ORD-PREV"
    )
    return customer


def _make_order(status=Order.Status.COMPLETED, total_q=5000, ref="ORD-RES-1", redeemed_q=40):
    data = {"customer_ref": CUSTOMER_REF}
    if redeemed_q:
        data["loyalty"] = {"applied_discount_q": redeemed_q}
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=status,
        total_q=total_q,
        data=data,
    )


def _force_status(order, status):
    """Coloca o pedido no status-alvo sem passar pelo grafo de transições.

    completed→cancelled só existe no lifecycle do canal pdv (janela do PIN
    gerencial) — aqui o assunto é a devolução, não o grafo.
    """
    Order.objects.filter(pk=order.pk).update(status=status)
    order.refresh_from_db()


def _redeem_directive(order, points=40, status="queued"):
    return Directive.objects.create(
        topic="loyalty.redeem",
        payload={"order_ref": order.ref, "points": points},
        status=status,
    )


def _restore_directive(order, reason="cancelled"):
    return Directive.objects.create(
        topic="loyalty.restore", payload={"order_ref": order.ref, "reason": reason}
    )


def _run_redeem(order, points=40):
    directive = _redeem_directive(order, points=points)
    LoyaltyRedeemHandler().handle(message=directive, ctx={})
    directive.status = "done"
    directive.save(update_fields=["status"])
    return directive


def test_cancel_after_redeem_restores_points(customer):
    order = _make_order()
    _run_redeem(order)
    assert LoyaltyService.get_balance(CUSTOMER_REF) == 60

    _force_status(order, Order.Status.CANCELLED)

    LoyaltyRestoreHandler().handle(message=_restore_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100
    adjust = LoyaltyService.get_transactions(CUSTOMER_REF)[0]
    assert adjust.transaction_type == "adjust"
    assert adjust.points == 40
    assert adjust.reference == f"order:{order.ref}:restore"
    assert "cancelado" in adjust.description


def test_return_restores_points(customer):
    order = _make_order()
    _run_redeem(order)

    _force_status(order, Order.Status.RETURNED)

    LoyaltyRestoreHandler().handle(
        message=_restore_directive(order, reason="returned"), ctx={}
    )

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100
    adjust = LoyaltyService.get_transactions(CUSTOMER_REF)[0]
    assert "devolvido" in adjust.description


def test_restore_is_idempotent_on_retry(customer):
    """Dois restores (retry at-least-once ou directive duplicada) = uma devolução."""
    order = _make_order()
    _run_redeem(order)
    _force_status(order, Order.Status.CANCELLED)

    handler = LoyaltyRestoreHandler()
    handler.handle(message=_restore_directive(order), ctx={})
    handler.handle(message=_restore_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100


def test_cancel_before_redeem_processes_leaves_balance_untouched(customer):
    """Redeem ainda na fila quando o cancel chega: o restore re-agenda; o redeem
    atrasado vê o pedido cancelado e não debita; o restore seguinte é no-op —
    sem crédito em dobro."""
    order = _make_order()
    redeem_directive = _redeem_directive(order)  # queued, worker ainda não passou

    _force_status(order, Order.Status.CANCELLED)

    restore = LoyaltyRestoreHandler()
    with pytest.raises(DirectiveTransientError):
        restore.handle(message=_restore_directive(order), ctx={})

    # O worker finalmente processa o redeem — o guard de status não debita.
    LoyaltyRedeemHandler().handle(message=redeem_directive, ctx={})
    redeem_directive.status = "done"
    redeem_directive.save(update_fields=["status"])
    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100

    # O retry do restore agora assenta: nada debitado, nada a devolver.
    restore.handle(message=_restore_directive(order), ctx={})
    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100
    assert not [
        tx
        for tx in LoyaltyService.get_transactions(CUSTOMER_REF)
        if tx.reference.startswith(f"order:{order.ref}")
    ]


def test_restore_noop_without_redemption(customer):
    """Pedido cancelado sem resgate: sem transação redeem, o restore não faz nada."""
    order = _make_order(status=Order.Status.CANCELLED, redeemed_q=0)

    LoyaltyRestoreHandler().handle(message=_restore_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100
    assert not [
        tx
        for tx in LoyaltyService.get_transactions(CUSTOMER_REF)
        if tx.reference.startswith(f"order:{order.ref}")
    ]


def test_restore_uses_redeem_transaction_not_payload(customer):
    """A transação redeem é a fonte da verdade — não o applied_discount_q."""
    order = _make_order(redeemed_q=40)
    _run_redeem(order, points=25)  # o débito real foi menor que o payload
    _force_status(order, Order.Status.CANCELLED)

    LoyaltyRestoreHandler().handle(message=_restore_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100


def test_revoke_and_restore_coexist_on_same_order(customer):
    """Venda completed com resgate, cancelada: o earn é estornado E o resgate é
    devolvido — cada dedupe na sua reference, nenhuma engole a outra."""
    order = _make_order()
    _run_redeem(order)  # -40 → 60
    earn_directive = Directive.objects.create(
        topic="loyalty.earn", payload={"order_ref": order.ref}
    )
    LoyaltyEarnHandler().handle(message=earn_directive, ctx={})  # +50 → 110
    earn_directive.status = "done"
    earn_directive.save(update_fields=["status"])
    assert LoyaltyService.get_balance(CUSTOMER_REF) == 110

    _force_status(order, Order.Status.CANCELLED)

    revoke_directive = Directive.objects.create(
        topic="loyalty.revoke", payload={"order_ref": order.ref, "reason": "cancelled"}
    )
    LoyaltyRevokeHandler().handle(message=revoke_directive, ctx={})  # -50 → 60
    LoyaltyRestoreHandler().handle(message=_restore_directive(order), ctx={})  # +40 → 100

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100
    adjusts = [
        tx
        for tx in LoyaltyService.get_transactions(CUSTOMER_REF)
        if tx.transaction_type == "adjust"
    ]
    assert {(tx.reference, tx.points) for tx in adjusts} == {
        (f"order:{order.ref}", -50),
        (f"order:{order.ref}:restore", 40),
    }

    # Re-execução dos dois (retry at-least-once) não muda o saldo.
    LoyaltyRevokeHandler().handle(
        message=Directive.objects.create(
            topic="loyalty.revoke", payload={"order_ref": order.ref, "reason": "cancelled"}
        ),
        ctx={},
    )
    LoyaltyRestoreHandler().handle(message=_restore_directive(order), ctx={})
    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100


def test_redeem_skips_cancelled_order(customer):
    """Guard do redeem: pedido cancelado nunca debita, mesmo sem restore no meio."""
    order = _make_order(status=Order.Status.CANCELLED)

    LoyaltyRedeemHandler().handle(message=_redeem_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100
