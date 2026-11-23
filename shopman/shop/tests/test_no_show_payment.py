"""O dinheiro do "Não retirado" (WP-G11): devolve só o que não ficou com a loja.

Um cancelado comum devolve tudo. Um cancelado com ``order.data["no_show"]``
devolve ``capturado − retido``, e a régua é uma só (``payment.retained_q``) para
as três formas de o dinheiro voltar:

- Pix e cartão online: estorno parcial no gateway, no valor certo;
- dinheiro: a pendência de "devolver em dinheiro" do PDV só tem o devolvível;
- maquininha: "estornar na maquininha" só tem o devolvível;
- não pago: nada.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.backstage.models import OperatorAlert
from shopman.shop.services import cancellation, no_show
from shopman.shop.services import payment as payment_service
from shopman.shop.tests import _no_show as world

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

_MOCK_ADAPTERS = override_settings(
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
        "cash": None,
        "external": None,
    }
)

#: Croissant (2 × R$ 9,35 = R$ 18,70) com estoque baixado: volta à venda.
#: Bolo (R$ 30,00) sem estoque baixado: perda. Total R$ 48,70.
CROIS_Q, BOLO_Q = 1870, 3000


@pytest.fixture(autouse=True)
def mundo():
    world.make_shop()
    world.product("CROIS", price_q=935)
    world.product("BOLO", price_q=3000)
    world.lot("CROIS")
    world.lot("BOLO")


@pytest.fixture
def fim_do_expediente(monkeypatch):
    """O relógio no corte do dia: o gesto está liberado para pedido pago."""
    moment = world.at(19, 5)
    monkeypatch.setattr(timezone, "now", lambda: moment)
    return moment


def _order(ref: str, *, back: bool = True, lost: bool = True) -> Order:
    """Pedido pronto. ``back``: a linha do croissant (volta). ``lost``: a do bolo (perda)."""
    lines = ([("CROIS", 2, 935)] if back else []) + ([("BOLO", 1, 3000)] if lost else [])
    # Pronto desde as 14h: no fim do expediente a tolerância do não pago também já passou.
    order = world.ready_order(ref, lines, held=False, ready_at=world.at(14))
    if back:
        order.data["hold_ids"] = [world.fulfilled_hold("CROIS", 2, order_ref=ref)]
        order.save(update_fields=["data", "updated_at"])
    return order


def _not_picked_up(order, capture) -> Order:
    with capture(execute=True):
        no_show.mark_not_picked_up(order, actor="ana", approved_by="gerente")
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    return order


def _net_q(intent_ref: str) -> int:
    return PaymentService.captured_total(intent_ref) - PaymentService.refunded_total(intent_ref)


# ── A régua ──────────────────────────────────────────────────────────────────


def test_retained_is_zero_without_the_block_and_there_is_no_ceiling():
    order = world.ready_order("RET-SEM-BLOCO", [("CROIS", 1, 935)])
    world.pay(order, "pix")

    assert payment_service.retained_q(order) == 0
    assert payment_service.refund_ceiling_q(order) is None


def test_ceiling_is_captured_minus_retained_and_shrinks_as_refunds_leave():
    order = world.ready_order("RET-TETO", [("CROIS", 2, 935), ("BOLO", 1, 3000)])
    intent = world.pay(order, "pix")
    order.data["no_show"] = {"retained_q": BOLO_Q}
    order.save(update_fields=["data", "updated_at"])

    assert payment_service.retained_q(order) == BOLO_Q
    assert payment_service.refund_ceiling_q(order) == CROIS_Q

    PaymentService.refund(intent, amount_q=CROIS_Q, reason="order_cancelled", gateway_id="r-1")
    assert payment_service.refund_ceiling_q(order) == 0


def test_ceiling_is_zero_when_the_payment_cannot_be_read(monkeypatch):
    order = world.ready_order("RET-MUDO", [("CROIS", 1, 935)])
    order.data["no_show"] = {"retained_q": 500}
    monkeypatch.setattr(payment_service, "captured_balance_q", lambda order, **kwargs: None)

    # Sem saber quanto entrou, não se devolve o que pode ser da loja.
    assert payment_service.refund_ceiling_q(order) == 0


# ── Pix e cartão online: estorno parcial no gateway ──────────────────────────


@_MOCK_ADAPTERS
@pytest.mark.parametrize("method", ["pix", "card"])
def test_gateway_refunds_only_what_goes_back_on_sale(method, fim_do_expediente, django_capture_on_commit_callbacks):
    order = _order(f"NS-GW-{method}")
    intent = world.pay(order, method)

    order = _not_picked_up(order, django_capture_on_commit_callbacks)

    assert order.data["no_show"]["refund_q"] == CROIS_Q
    assert order.data["no_show"]["retained_q"] == BOLO_Q
    assert world.refunded_q(order.ref) == CROIS_Q
    assert _net_q(intent) == BOLO_Q
    # O estorno entrou no histórico com o valor parcial.
    (event,) = order.events.filter(type="payment.refunded")
    assert event.payload["amount_q"] == CROIS_Q


@_MOCK_ADAPTERS
def test_gateway_refund_is_not_repeated_when_the_cancellation_runs_again(fim_do_expediente, django_capture_on_commit_callbacks):
    order = _order("NS-GW-DUAS")
    intent = world.pay(order, "pix")
    order = _not_picked_up(order, django_capture_on_commit_callbacks)

    # O ``on_cancelled`` re-disparado (sweeper) chama o estorno de novo, sem valor.
    payment_service.refund(order)
    payment_service.refund(order)

    assert world.refunded_q(order.ref) == CROIS_Q
    assert _net_q(intent) == BOLO_Q


@_MOCK_ADAPTERS
def test_gateway_refunds_everything_when_everything_goes_back(fim_do_expediente, django_capture_on_commit_callbacks):
    order = _order("NS-GW-TUDO-VOLTA", lost=False)
    intent = world.pay(order, "pix")

    order = _not_picked_up(order, django_capture_on_commit_callbacks)

    assert (order.data["no_show"]["refund_q"], order.data["no_show"]["retained_q"]) == (CROIS_Q, 0)
    assert world.refunded_q(order.ref) == CROIS_Q
    assert _net_q(intent) == 0


@_MOCK_ADAPTERS
def test_gateway_refunds_nothing_when_everything_was_lost(fim_do_expediente, django_capture_on_commit_callbacks):
    order = _order("NS-GW-TUDO-PERDA", back=False)
    intent = world.pay(order, "pix")

    order = _not_picked_up(order, django_capture_on_commit_callbacks)

    assert (order.data["no_show"]["refund_q"], order.data["no_show"]["retained_q"]) == (0, BOLO_Q)
    assert world.refunded_q(order.ref) == 0
    assert _net_q(intent) == BOLO_Q


@_MOCK_ADAPTERS
def test_customer_page_money_outcome_counts_only_what_goes_back(fim_do_expediente, django_capture_on_commit_callbacks):
    mixed = _order("NS-GW-DESTINO")
    world.pay(mixed, "pix")
    lost = _order("NS-GW-DESTINO-PERDA", back=False)
    world.pay(lost, "pix")

    mixed = _not_picked_up(mixed, django_capture_on_commit_callbacks)
    lost = _not_picked_up(lost, django_capture_on_commit_callbacks)

    money = payment_service.cancelled_money(mixed)
    assert (money.outcome, money.amount_q, money.method) == ("refunded", CROIS_Q, "pix")
    # Nada volta: não há devolução a contar; quem explica é o texto do motivo.
    assert payment_service.cancelled_money(lost) is None


# ── Dinheiro: a pendência de devolver só tem o devolvível ────────────────────


def test_cash_pending_refund_is_only_what_goes_back(fim_do_expediente, django_capture_on_commit_callbacks):
    from shopman.cashman import services as cash

    order = _order("NS-CASH")
    intent = world.pay(order, "cash")

    order = _not_picked_up(order, django_capture_on_commit_callbacks)

    # Cancelar não devolve dinheiro: fica a pendência, e só do devolvível.
    assert world.refunded_q(order.ref) == 0
    (pending,) = payment_service.pending_cash_refunds()
    assert (pending.order_ref, pending.amount_q) == (order.ref, CROIS_Q)
    # O PDV diz por que o dinheiro volta (#2696): não é uma venda cancelada.
    assert pending.reason == "not_picked_up"
    assert payment_service.REFUND_REASON_LABELS[pending.reason] == "Pedido não retirado"

    from django.contrib.auth import get_user_model

    operator = get_user_model().objects.create_user(username="caixa-ns", password="x")
    shift = cash.open_shift(operator=operator, float_q=10000)
    assert payment_service.refund_cash(order, shift=shift, actor=operator) == CROIS_Q

    # O retido fica na gaveta, e a pendência some.
    assert _net_q(intent) == BOLO_Q
    assert payment_service.pending_cash_refunds() == []
    assert payment_service.refund_cash(order, shift=shift, actor=operator) == 0


def test_cash_has_nothing_pending_when_everything_was_lost(fim_do_expediente, django_capture_on_commit_callbacks):
    order = _order("NS-CASH-PERDA", back=False)
    world.pay(order, "cash")

    _not_picked_up(order, django_capture_on_commit_callbacks)

    assert payment_service.pending_cash_refunds() == []


# ── Maquininha: estornar só o devolvível ─────────────────────────────────────


def test_card_machine_refund_due_is_only_what_goes_back(fim_do_expediente, django_capture_on_commit_callbacks):
    order = _order("NS-MAQ")
    intent = world.pay(order, "credit")

    order = _not_picked_up(order, django_capture_on_commit_callbacks)

    assert world.refunded_q(order.ref) == 0
    assert payment_service.card_machine_refund_due(order) == (CROIS_Q, [intent])
    (pending,) = payment_service.pending_card_machine_refunds()
    assert (pending.order_ref, pending.amount_q) == (order.ref, CROIS_Q)
    assert pending.reason == "not_picked_up"
    # O aviso do Gestor manda estornar o valor certo.
    alert = OperatorAlert.objects.get(type=payment_service.CARD_MACHINE_REFUND_ALERT, order_ref=order.ref)
    assert "R$ 18,70" in alert.message

    assert payment_service.record_card_machine_refund(order, actor="ana") == CROIS_Q
    assert _net_q(intent) == BOLO_Q
    assert payment_service.card_machine_refund_due(order) == (0, [])
    assert payment_service.pending_card_machine_refunds() == []


def test_card_machine_has_nothing_due_when_everything_was_lost(fim_do_expediente, django_capture_on_commit_callbacks):
    order = _order("NS-MAQ-PERDA", back=False)
    world.pay(order, "credit")

    order = _not_picked_up(order, django_capture_on_commit_callbacks)

    assert payment_service.card_machine_refund_due(order) == (0, [])
    assert not OperatorAlert.objects.filter(type=payment_service.CARD_MACHINE_REFUND_ALERT, order_ref=order.ref).exists()


# ── Não pago ─────────────────────────────────────────────────────────────────


def test_unpaid_order_moves_no_money(fim_do_expediente, django_capture_on_commit_callbacks):
    order = _order("NS-NAO-PAGO")

    order = _not_picked_up(order, django_capture_on_commit_callbacks)

    block = order.data["no_show"]
    assert (block["paid_q"], block["refund_q"], block["retained_q"]) == (0, 0, 0)
    assert world.refunded_q(order.ref) == 0
    assert payment_service.pending_cash_refunds() == []
    assert payment_service.pending_card_machine_refunds() == []


# ── O cancelado comum continua devolvendo tudo ───────────────────────────────


def _cancel(order, capture) -> Order:
    with capture(execute=True):
        assert cancellation.cancel(order, reason="customer_requested", actor="ana") is True
    order.refresh_from_db()
    assert "no_show" not in order.data
    return order


@_MOCK_ADAPTERS
def test_common_cancel_still_refunds_everything_at_the_gateway(django_capture_on_commit_callbacks):
    order = _order("COMUM-PIX")
    intent = world.pay(order, "pix")

    order = _cancel(order, django_capture_on_commit_callbacks)

    assert world.refunded_q(order.ref) == CROIS_Q + BOLO_Q
    assert _net_q(intent) == 0
    money = payment_service.cancelled_money(order)
    assert (money.outcome, money.amount_q) == ("refunded", CROIS_Q + BOLO_Q)


def test_common_cancel_still_leaves_all_the_cash_pending(django_capture_on_commit_callbacks):
    order = _order("COMUM-CASH")
    world.pay(order, "cash")

    order = _cancel(order, django_capture_on_commit_callbacks)

    (pending,) = payment_service.pending_cash_refunds()
    assert pending.amount_q == CROIS_Q + BOLO_Q
    assert pending.reason == "cancelled"


def test_common_cancel_still_sends_everything_back_to_the_card_machine(django_capture_on_commit_callbacks):
    order = _order("COMUM-MAQ")
    intent = world.pay(order, "credit")

    order = _cancel(order, django_capture_on_commit_callbacks)

    assert payment_service.card_machine_refund_due(order) == (CROIS_Q + BOLO_Q, [intent])
