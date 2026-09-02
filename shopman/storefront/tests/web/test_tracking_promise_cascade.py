"""A cascata unificada da promessa — um teste por estado, e o invariante.

PAYMENT-TRACKING-MERGE: o pagamento deixou de ser uma tela e virou os degraus
de pagamento do próprio acompanhamento. ``order_tracking._build_promise`` é a
espinha: uma pergunta ("de quem é a bola agora?"), seis posses, 19 estados.

Cada teste constrói o mundo que produz um estado e afirma o estado. O invariante
final prova a segurança do desenho: um estado de "bola do cliente" (pagar agora)
nunca aparece fora de ``status ∈ {new, accepted}`` — pagamento e entrega não se
atropelam por construção.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.projections import order_tracking
from shopman.shop.projections.order_tracking import build_tracking

# Estados em que a bola é do cliente: ele precisa agir (pagar/tentar) AGORA.
CUSTOMER_BALL_STATES = {"payment_pix_ready", "payment_card_ready", "payment_retry"}


@pytest.fixture
def make_order(channel):
    counter = {"n": 0}

    def _make(*, status="new", payment=None, data=None):
        counter["n"] += 1
        d = dict(data or {})
        if payment is not None:
            d["payment"] = payment
        order = Order.objects.create(
            ref=f"ORD-CASCADE-{counter['n']:03d}",
            channel_ref=channel.ref,
            status=status,
            total_q=2500,
            handle_type="phone",
            handle_ref="5543999990001",
            data=d,
        )
        return order

    return _make


@pytest.fixture
def patch_payment(monkeypatch):
    """Controla os fatos de pagamento que a cascata lê, sem intent real."""

    def _patch(*, captured=False, live_status=None, deadline_passed=False, deferred=False):
        ps = order_tracking.payment_status
        monkeypatch.setattr(ps, "has_sufficient_captured_payment", lambda order: captured)
        monkeypatch.setattr(ps, "payment_deadline_passed", lambda order: deadline_passed)
        if live_status is not None:
            monkeypatch.setattr(ps, "get_payment_status", lambda order: live_status)
        else:
            monkeypatch.setattr(ps, "get_payment_status", lambda order: None)
        if deferred:
            monkeypatch.setattr(
                order_tracking,
                "store_review_deferred_state",
                lambda order, state=None: _DeferredSentinel(),
            )
        else:
            monkeypatch.setattr(
                order_tracking, "store_review_deferred_state", lambda order, state=None: None
            )

    return _patch


class _DeferredSentinel:
    next_open_at = None
    resolved_at = None


def _promise_state(order):
    return build_tracking(order).promise.state


# ── A tabela dos 19 estados ─────────────────────────────────────────────


def test_state_cancelled(make_order, patch_payment):
    patch_payment()
    order = make_order(status="cancelled")
    assert _promise_state(order) == "cancelled"


def test_state_returned(make_order, patch_payment):
    patch_payment()
    order = make_order(status="returned")
    assert _promise_state(order) == "returned"


def test_state_delivered(make_order, patch_payment):
    patch_payment()
    order = make_order(status="delivered")
    assert _promise_state(order) == "delivered"


def test_state_completed(make_order, patch_payment):
    patch_payment()
    order = make_order(status="completed")
    assert _promise_state(order) == "completed"


def test_state_payment_expired(make_order, patch_payment):
    patch_payment()
    order = make_order(
        status="cancelled",
        data={
            "cancellation_reason": "payment_timeout",
            "payment_timeout_at": "2026-01-01T00:00:00-03:00",
        },
        payment={"method": "pix"},
    )
    assert _promise_state(order) == "payment_expired"


def test_state_payment_expired_lazy_before_cancel(make_order, patch_payment):
    # Prazo vencido mas ainda não cancelado (resolução lazy): degrau 2.
    patch_payment(deadline_passed=True)
    order = make_order(status="accepted", payment={"method": "pix", "pix_code": "PIX"})
    assert _promise_state(order) == "payment_expired"


def test_state_payment_pix_ready(make_order, patch_payment):
    patch_payment()
    order = make_order(status="accepted", payment={"method": "pix", "pix_code": "PIX123"})
    assert _promise_state(order) == "payment_pix_ready"


def test_state_payment_card_ready(make_order, patch_payment):
    patch_payment()
    order = make_order(status="accepted", payment={"method": "card", "checkout_url": "https://pay"})
    assert _promise_state(order) == "payment_card_ready"


def test_state_payment_retry_on_error(make_order, patch_payment):
    patch_payment()
    order = make_order(status="accepted", payment={"method": "card", "error": "gateway_down"})
    assert _promise_state(order) == "payment_retry"


def test_state_payment_retry_card_without_link(make_order, patch_payment):
    patch_payment()
    order = make_order(status="accepted", payment={"method": "card"})
    assert _promise_state(order) == "payment_retry"


# ── O link de pagamento do balcão: a mesma sessão hospedada do cartão ───
#
# Pedido remoto anotado no PDV; o cliente paga do celular pela URL do gateway.
# A cascata testava `method == "card"` cravado em cinco pontos, e quem abria o
# acompanhamento de um pedido de link não encontrava botão nenhum para pagar.


def test_state_payment_card_ready_for_link(make_order, patch_payment):
    patch_payment()
    order = make_order(status="accepted", payment={"method": "link", "checkout_url": "https://pay"})
    promise = build_tracking(order).promise
    assert promise.state == "payment_card_ready"
    # O método próprio viaja: é ele que a tela rotula ("Link de pagamento").
    assert promise.payment_method == "link"
    assert promise.checkout_url == "https://pay"
    assert any(action.href == "https://pay" for action in promise.actions)


def test_state_payment_retry_link_without_url(make_order, patch_payment):
    patch_payment()
    order = make_order(status="accepted", payment={"method": "link"})
    promise = build_tracking(order).promise
    assert promise.state == "payment_retry"
    assert promise.payment_method == "link"


def test_state_payment_authorized_for_link(make_order, patch_payment):
    patch_payment(live_status="authorized")
    order = make_order(status="accepted", payment={"method": "link", "status": "authorized"})
    promise = build_tracking(order).promise
    assert promise.state == "payment_authorized"
    assert promise.payment_method == "link"


def test_state_payment_expired_for_link(make_order, patch_payment):
    """O link é digital: prazo vencido sem captura é `payment_expired`, não "recebemos"."""
    patch_payment(deadline_passed=True)
    order = make_order(status="accepted", payment={"method": "link", "checkout_url": "https://pay"})
    assert _promise_state(order) == "payment_expired"


def test_link_pending_shows_payment_as_pending(make_order, patch_payment):
    """`_payment_info` também alcança o link: o passo de pagamento aparece e fica pendente."""
    patch_payment()
    order = make_order(status="accepted", payment={"method": "link", "intent_ref": "PAY-LINK", "checkout_url": "https://pay"})
    tracking = build_tracking(order)
    assert tracking.payment_pending is True
    assert tracking.payment_status_key == "payment_pending"


def test_state_payment_authorized(make_order, patch_payment):
    patch_payment(live_status="authorized")
    order = make_order(status="accepted", payment={"method": "card", "status": "authorized"})
    assert _promise_state(order) == "payment_authorized"


def test_state_payment_confirmed(make_order, patch_payment):
    patch_payment(captured=True)
    order = make_order(status="accepted", payment={"method": "pix"})
    assert _promise_state(order) == "payment_confirmed"


def test_state_store_closed(make_order, patch_payment):
    patch_payment(deferred=True)
    order = make_order(status="new", payment={"method": "pix"})
    assert _promise_state(order) == "store_closed"


def test_state_store_checking(make_order, patch_payment):
    # new, loja aberta, Pix sem código ainda → conferindo disponibilidade.
    patch_payment()
    order = make_order(status="new", payment={"method": "pix"})
    assert _promise_state(order) == "store_checking"


def test_state_payment_preparing(make_order, patch_payment):
    # accepted, Pix, código nascendo (janela curta entre aceite e QR).
    patch_payment()
    order = make_order(status="accepted", payment={"method": "pix"})
    assert _promise_state(order) == "payment_preparing"


def test_state_preorder_scheduled(make_order, patch_payment):
    patch_payment()
    tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
    order = make_order(
        status="accepted",
        payment={"method": "cash"},
        data={"delivery_date": tomorrow, "delivery_time_slot": "slot-09"},
    )
    assert _promise_state(order) == "preorder_scheduled"


def test_state_preparing(make_order, patch_payment):
    patch_payment()
    order = make_order(status="preparing", payment={"method": "cash"})
    assert _promise_state(order) == "preparing"


def test_state_ready_pickup(make_order, patch_payment):
    patch_payment()
    order = make_order(status="ready", payment={"method": "cash"}, data={"fulfillment_type": "pickup"})
    assert _promise_state(order) == "ready_pickup"


def test_state_ready_delivery(make_order, patch_payment):
    patch_payment()
    order = make_order(status="ready", payment={"method": "cash"}, data={"fulfillment_type": "delivery"})
    assert _promise_state(order) == "ready_delivery"


def test_state_dispatched(make_order, patch_payment):
    patch_payment()
    order = make_order(status="dispatched", payment={"method": "cash"}, data={"fulfillment_type": "delivery"})
    assert _promise_state(order) == "dispatched"


def test_state_received(make_order, patch_payment):
    patch_payment()
    order = make_order(status="new", payment={"method": "cash"})
    assert _promise_state(order) == "received"


# ── O invariante que torna a fusão segura ───────────────────────────────


def test_customer_ball_payment_implies_open_status(make_order, patch_payment):
    """payment_pix_ready/card_ready/retry só aparecem com status ∈ {new, accepted}.

    A prova estrutural de que pagamento (bola do cliente) nunca compete com
    preparo/expedição: são mutuamente exclusivos por construção.
    """
    payments = [
        {"method": "pix", "pix_code": "PIX"},
        {"method": "card", "checkout_url": "https://pay"},
        {"method": "card", "error": "boom"},
    ]
    statuses = ["new", "accepted", "preparing", "ready", "dispatched", "completed", "cancelled", "returned"]
    for payment in payments:
        for status in statuses:
            patch_payment()
            order = make_order(status="new", payment=payment)
            Order.objects.filter(pk=order.pk).update(status=status)
            order.refresh_from_db()
            state = build_tracking(order).promise.state
            if state in CUSTOMER_BALL_STATES:
                assert status in {"new", "accepted"}, (status, payment, state)


# ── Capstone: um pedido, um estado, uma frase (sem segunda tela) ─────────


def test_one_order_one_state_one_phrase(make_order, patch_payment):
    """A prova de que a fusão fechou: um pedido rende UMA promessa, no próprio
    acompanhamento, com o bloco de Pix inline — não uma segunda tela.
    """
    from shopman.storefront.presentation.order_tracking import build_order_tracking

    patch_payment()
    order = make_order(status="accepted", payment={"method": "pix", "pix_code": "00020126BR"})

    proj = build_order_tracking(order)

    # Um estado.
    assert proj.promise.state == "payment_pix_ready"
    # Uma frase: título + mensagem prontos, sem campo vazio.
    assert proj.promise.title and proj.promise.message
    # O pagamento é inline: o bloco viaja na própria promessa do acompanhamento.
    assert proj.promise.payment_method == "pix"
    assert proj.promise.pix_copy_paste == "00020126BR"
    # E a copy estática do bloco vem no payload do acompanhamento (uma tela só).
    assert proj.copy.pix_copy_btn
    assert proj.copy.pix_instruction
