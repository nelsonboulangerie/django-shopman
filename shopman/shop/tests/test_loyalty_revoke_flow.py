"""Estorno de pontos: cancelou/devolveu a venda, os pontos creditados voltam.

Com o counter_handoff a venda de balcão nasce ``completed`` (o earn credita) e
pode ser cancelada na janela do PIN gerencial — sem o revoke, os pontos ficavam.
O estorno espelha o earn: Directive ``loyalty.revoke``, idempotente pela
transação ``adjust`` com a mesma ``reference="order:{ref}"``, e estorna o que a
transação ``earn`` registrou — nunca um recálculo pela config atual.
"""

from __future__ import annotations

import pytest
from shopman.guestman.contrib.loyalty.service import LoyaltyService
from shopman.guestman.models import Customer
from shopman.orderman.exceptions import DirectiveTransientError
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.loyalty import LoyaltyEarnHandler, LoyaltyRevokeHandler
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

CUSTOMER_REF = "CUST-REVOKE-1"


@pytest.fixture
def customer(db):
    customer = Customer.objects.create(
        ref=CUSTOMER_REF, first_name="Ana", phone="+5543999990001"
    )
    LoyaltyService.enroll(CUSTOMER_REF)
    return customer


def _make_order(status=Order.Status.COMPLETED, total_q=5000, ref="ORD-REV-1"):
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=status,
        total_q=total_q,
        data={"customer_ref": CUSTOMER_REF},
    )


def _force_status(order, status):
    """Coloca o pedido no status-alvo sem passar pelo grafo de transições.

    completed→cancelled só existe no lifecycle do canal pdv (janela do PIN
    gerencial) — aqui o assunto é o estorno, não o grafo.
    """
    Order.objects.filter(pk=order.pk).update(status=status)
    order.refresh_from_db()


def _earn_directive(order, status="queued"):
    return Directive.objects.create(
        topic="loyalty.earn", payload={"order_ref": order.ref}, status=status
    )


def _revoke_directive(order, reason="cancelled"):
    return Directive.objects.create(
        topic="loyalty.revoke", payload={"order_ref": order.ref, "reason": reason}
    )


def _run_earn(order):
    directive = _earn_directive(order)
    LoyaltyEarnHandler().handle(message=directive, ctx={})
    directive.status = "done"
    directive.save(update_fields=["status"])
    return directive


def test_cancel_after_earn_reverses_points(customer):
    order = _make_order()
    _run_earn(order)
    assert LoyaltyService.get_balance(CUSTOMER_REF) == 50

    _force_status(order, Order.Status.CANCELLED)

    LoyaltyRevokeHandler().handle(message=_revoke_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 0
    adjust = LoyaltyService.get_transactions(CUSTOMER_REF)[0]
    assert adjust.transaction_type == "adjust"
    assert adjust.points == -50
    assert adjust.reference == f"order:{order.ref}"
    assert "cancelado" in adjust.description


def test_return_reverses_points(customer):
    order = _make_order()
    _run_earn(order)

    _force_status(order, Order.Status.RETURNED)

    LoyaltyRevokeHandler().handle(
        message=_revoke_directive(order, reason="returned"), ctx={}
    )

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 0
    adjust = LoyaltyService.get_transactions(CUSTOMER_REF)[0]
    assert "devolvido" in adjust.description


def test_revoke_is_idempotent_on_retry(customer):
    """Dois revokes (retry at-least-once ou directive duplicada) = um estorno."""
    order = _make_order()
    _run_earn(order)
    _force_status(order, Order.Status.CANCELLED)

    handler = LoyaltyRevokeHandler()
    handler.handle(message=_revoke_directive(order), ctx={})
    handler.handle(message=_revoke_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 0


def test_cancel_before_earn_processes_leaves_no_points(customer):
    """Earn ainda na fila quando o cancel chega: o revoke re-agenda; o earn
    atrasado vê o pedido cancelado e não credita; o revoke seguinte é no-op."""
    order = _make_order()
    earn_directive = _earn_directive(order)  # queued, worker ainda não passou

    _force_status(order, Order.Status.CANCELLED)

    revoke = LoyaltyRevokeHandler()
    with pytest.raises(DirectiveTransientError):
        revoke.handle(message=_revoke_directive(order), ctx={})

    # O worker finalmente processa o earn — o guard de status não credita.
    LoyaltyEarnHandler().handle(message=earn_directive, ctx={})
    earn_directive.status = "done"
    earn_directive.save(update_fields=["status"])
    assert LoyaltyService.get_balance(CUSTOMER_REF) == 0

    # O retry do revoke agora assenta: nada creditado, nada a estornar.
    revoke.handle(message=_revoke_directive(order), ctx={})
    assert LoyaltyService.get_balance(CUSTOMER_REF) == 0
    assert not LoyaltyService.get_transactions(CUSTOMER_REF)


def test_revoke_noop_when_never_earned(customer):
    """Pedido cancelado sem nunca completar: sem earn, o revoke não faz nada."""
    order = _make_order(status=Order.Status.CANCELLED)

    LoyaltyRevokeHandler().handle(message=_revoke_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 0
    assert not LoyaltyService.get_transactions(CUSTOMER_REF)


def test_revoke_uses_earn_transaction_not_current_config(customer):
    """A taxa mudou entre o crédito e o estorno: estorna o que foi creditado."""
    shop = Shop.objects.create(
        name="Loja", defaults={"loyalty": {"points_per_real": 2}}
    )
    order = _make_order()
    _run_earn(order)
    assert LoyaltyService.get_balance(CUSTOMER_REF) == 100

    shop.defaults = {"loyalty": {"points_per_real": 1}}
    shop.save(update_fields=["defaults"])
    _force_status(order, Order.Status.CANCELLED)

    LoyaltyRevokeHandler().handle(message=_revoke_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 0


def test_revoke_allows_negative_balance(customer):
    """Cliente já gastou os pontos: o estorno registra a dívida, não falha."""
    order = _make_order()
    _run_earn(order)
    LoyaltyService.redeem_points(
        CUSTOMER_REF, points=30, description="resgate", reference="outro-pedido"
    )
    _force_status(order, Order.Status.CANCELLED)

    LoyaltyRevokeHandler().handle(message=_revoke_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == -30


def test_earn_skips_cancelled_order(customer):
    """Guard do earn: pedido cancelado nunca credita, mesmo sem revoke no meio."""
    order = _make_order(status=Order.Status.CANCELLED)

    LoyaltyEarnHandler().handle(message=_earn_directive(order), ctx={})

    assert LoyaltyService.get_balance(CUSTOMER_REF) == 0
