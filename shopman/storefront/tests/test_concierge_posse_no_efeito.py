"""Posse da conversa reconferida no instante do efeito (#2625; v2 4.7, propriedade 4).

Quatro efeitos locais da Concierge: pedido, desconto, cancelamento e acréscimo. Em
cada um, a transferência para a equipe (``service.mark_handoff``) concorre com o
comando da automação em duas posições, com conexões reais do PostgreSQL:

- **K11**: a barreira fica exatamente entre a conferência da posse que o efeito já
  fazia e a gravação. A equipe assume ali. Nenhum efeito local pode nascer do
  comando antigo: o efeito reconfere a posse com a conversa travada, na mesma
  transação que grava, e recusa.
- **K12**: a barreira fica dentro da transação do efeito, depois da gravação. A
  transferência chega ali e precisa ESPERAR a trava da conversa (espera real de
  row lock, medida em ``pg_blocking_pids``): o efeito venceu, fica feito e
  registrado, ninguém promete desfazê-lo, e o comando antigo não age de novo.

Antes da correção, o K11 grava o efeito do comando antigo e o K12 vê a transferência
passar sem esperar, porque a conferência acontecia fora da transação do efeito.
"""

# ruff: noqa: F401, F811
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import connection
from django.utils.dateparse import parse_datetime
from shopman.offerman.models import ListingItem, Product
from shopman.orderman.models import IdempotencyKey, Order, Session

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage, Coupon
from shopman.shop.services import cart as cart_service
from shopman.shop.services import checkout, customer_orders, order_edit, sessions
from shopman.shop.services import payment as payment_service
from shopman.storefront.concierge import cancellation, discount, order_addition, service, tools
from shopman.storefront.tests.test_concierge_commercial_races import (
    Worker,
    assert_database_wait,
    worker_tool_context,
)
from shopman.storefront.tests.test_concierge_engine import (
    CHANNEL,
    SKU,
    _accept_review,
    _binding,
    _create_inbound,
    _pickup_ready,
    _reclaim,
    conversation,
    ctx,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_order_addition import _order, _paid_cash, _unchanged

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="Requires independent PostgreSQL connections"
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]


@pytest.fixture(autouse=True)
def isolated_callbacks(monkeypatch, outbox):
    assert connection.vendor == "postgresql", "Este ensaio exige PostgreSQL real"
    # A chamada de rede do Pix fica fora da prova: o que se mede é o efeito local.
    monkeypatch.setattr("shopman.shop.services.payment.initiate", lambda order: None)


# ── Peças comuns ─────────────────────────────────────────────────────


def _handoff_worker(conversation_pk: int) -> Worker:
    """A equipe assume pela porta canônica, noutra conexão."""

    def take_over():
        current = Conversation.objects.get(pk=conversation_pk)
        binding = ConversationBinding.objects.get(conversation=current)
        service.mark_handoff(current, binding, "Equipe assumiu a conversa")
        return Conversation.objects.get(pk=conversation_pk).turn_fence

    return Worker(take_over)


def _pause_after(original, boundary: Event, release: Event):
    """Chama ``original`` e para no ponto medido; só a primeira chamada pausa."""
    seen = []

    def paused(*args, **kwargs):
        result = original(*args, **kwargs)
        if not seen:
            seen.append(True)
            boundary.set()
            assert release.wait(20)
        return result

    return paused


def _handoff_wins_before_the_effect(effect: Worker, conversation_pk: int, boundary: Event, release: Event):
    """K11: o efeito para depois da conferência; a equipe assume inteira; o efeito segue."""
    handoff = _handoff_worker(conversation_pk)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(effect)
        try:
            assert boundary.wait(20), "o efeito não chegou à barreira"
            fence = pool.submit(handoff).result(30)
        finally:
            release.set()
        outcome = pending.result(30)
    assert isinstance(fence, int), fence
    assert Conversation.objects.get(pk=conversation_pk).state == Conversation.State.HANDOFF
    return outcome


def _handoff_arrives_inside_the_effect(effect: Worker, conversation_pk: int, boundary: Event, release: Event):
    """K12: o efeito já gravou e segura a trava; a transferência tem de esperar o commit."""
    handoff = _handoff_worker(conversation_pk)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(effect)
        try:
            assert boundary.wait(20), "o efeito não chegou à barreira"
            transferred = pool.submit(handoff)
            assert_database_wait(handoff)
        finally:
            release.set()
        outcome = pending.result(30)
        fence = transferred.result(30)
    assert isinstance(fence, int), fence
    current = Conversation.objects.get(pk=conversation_pk)
    assert current.state == Conversation.State.HANDOFF
    return outcome, current


def _revoked(outcome) -> bool:
    """Recusa pela posse: a exceção do serviço, ou o erro em que a guarda das ferramentas a traduz."""
    if not isinstance(outcome, dict):
        return False
    return outcome.get("exception") == "TurnRevoked" or outcome.get("error") == "authority_unavailable"


def _handoff_note(conversation_pk: int) -> ConversationMessage:
    return ConversationMessage.objects.get(
        conversation_id=conversation_pk,
        kind=ConversationMessage.Kind.NOTE,
        text="Atendimento humano solicitado. Contexto preservado.",
    )


# ── Pedido ───────────────────────────────────────────────────────────


def _reviewed_cart(ctx):
    review = _pickup_ready(ctx)
    _accept_review(ctx, review)
    return review


def test_k11_order_is_not_born_when_the_team_takes_over_before_the_commit(ctx, monkeypatch):
    review = _reviewed_cart(ctx)
    key = ctx.conversation.session_key
    boundary, release = Event(), Event()
    # Depois da conferência do ``commit_local`` (e da recotação), antes do commit do pedido.
    monkeypatch.setattr(
        checkout, "_prepare_checkout_atomic", _pause_after(checkout._prepare_checkout_atomic, boundary, release)
    )
    effect = Worker(lambda: tools.place_order(worker_tool_context(ctx.conversation), review["quote_token"], "pix"))

    outcome = _handoff_wins_before_the_effect(effect, ctx.conversation.pk, boundary, release)

    assert _revoked(outcome), outcome
    assert not Order.objects.exists()
    assert Session.objects.get(session_key=key).state == "open"
    assert not IdempotencyKey.objects.filter(scope__startswith="commit:", status="done").exists()
    assert Conversation.objects.get(pk=ctx.conversation.pk).last_order_ref == ""


def test_k12_order_committed_before_the_handoff_stands_and_is_reconciled(ctx, monkeypatch):
    review = _reviewed_cart(ctx)
    boundary, release = Event(), Event()
    # Dentro da transação do commit: o pedido já existe, ainda não foi confirmado no banco.
    monkeypatch.setattr(sessions, "commit_session", _pause_after(sessions.commit_session, boundary, release))
    effect = Worker(lambda: tools.place_order(worker_tool_context(ctx.conversation), review["quote_token"], "pix"))

    result, current = _handoff_arrives_inside_the_effect(effect, ctx.conversation.pk, boundary, release)

    assert result.get("ok") and result.get("order_ref"), result
    order = Order.objects.get()
    assert order.ref == result["order_ref"] and order.status != Order.Status.CANCELLED
    # Reconciliado: a conversa sabe do pedido que a automação fez antes de a equipe assumir.
    assert current.last_order_ref == order.ref and current.handoff_at > order.created_at
    # O comando antigo não age de novo: a posse é da equipe, e nenhum segundo pedido nasce.
    assert _revoked(tools.place_order(ctx, review["quote_token"], "pix"))
    assert Order.objects.count() == 1


# ── Desconto ─────────────────────────────────────────────────────────


@pytest.fixture
def discounted_cart(ctx):
    Product.objects.filter(sku=SKU).update(base_price_q=2560)
    ListingItem.objects.filter(product__sku=SKU).update(price_q=2560)
    assert tools.set_item(ctx, SKU, 2)["ok"]
    return ctx


def _ask_discount(ctx):
    worker_ctx = worker_tool_context(ctx.conversation)
    return discount.handle_request(
        conversation=worker_ctx.conversation, channel_ref=CHANNEL, customer_text="Faz um desconto pra mim?"
    )


def test_k11_discount_is_not_granted_when_the_team_takes_over_before_the_coupon(discounted_cart, monkeypatch):
    ctx = discounted_cart
    boundary, release = Event(), Event()
    # O valor está calculado; o cupom ainda não foi emitido nem aplicado.
    monkeypatch.setattr(discount, "amount_for", _pause_after(discount.amount_for, boundary, release))
    effect = Worker(lambda: _ask_discount(ctx))

    outcome = _handoff_wins_before_the_effect(effect, ctx.conversation.pk, boundary, release)

    assert _revoked(outcome), outcome
    assert not Coupon.objects.filter(code__startswith="CONCIERGE-").exists()
    data = Session.objects.get(session_key=ctx.conversation.session_key).data or {}
    assert discount.SESSION_KEY not in data and not data.get("coupon_code")


def test_k12_discount_granted_before_the_handoff_stands(discounted_cart, monkeypatch):
    ctx = discounted_cart
    boundary, release = Event(), Event()
    # Dentro da transação do cupom: emitido e aplicado à sacola, ainda não confirmado no banco.
    monkeypatch.setattr(
        cart_service,
        "validate_and_apply_coupon",
        _pause_after(cart_service.validate_and_apply_coupon, boundary, release),
    )
    effect = Worker(lambda: _ask_discount(ctx))

    outcome, current = _handoff_arrives_inside_the_effect(effect, ctx.conversation.pk, boundary, release)

    assert outcome.code == "granted", outcome
    session = Session.objects.get(session_key=ctx.conversation.session_key)
    assert session.data["coupon_code"] == outcome.coupon_code
    assert session.data[discount.SESSION_KEY]["discount_q"] == outcome.discount_q > 0
    assert Coupon.objects.filter(code=outcome.coupon_code).count() == 1
    assert current.handoff_at > parse_datetime(session.data[discount.SESSION_KEY]["at"])
    # O pedido repetido não concede outro cupom.
    assert _ask_discount(ctx).code != "granted"
    assert Coupon.objects.filter(code__startswith="CONCIERGE-").count() == 1


# ── Cancelamento ─────────────────────────────────────────────────────


@pytest.fixture
def placed(ctx):
    review = _reviewed_cart(ctx)
    result = tools.place_order(ctx, review["quote_token"], "pix")
    assert result["ok"], result
    ConversationMessage.objects.filter(conversation=ctx.conversation, kind=ConversationMessage.Kind.INBOUND).update(
        consumed_by=1
    )
    Conversation.objects.filter(pk=ctx.conversation.pk).update(claim_until=None, session_key="")
    # Um turno novo, o do "sim" à pergunta de cancelamento.
    _create_inbound(ctx.conversation, "sim", "cancel-yes")
    _reclaim(ctx)
    return Order.objects.get(ref=result["order_ref"])


def _cancel(ctx, order):
    worker_ctx = worker_tool_context(ctx.conversation)
    return cancellation._execute(worker_ctx.conversation, {"order_ref": order.ref, "request": "Quero cancelar"})


def test_k11_order_is_not_cancelled_when_the_team_takes_over_before_the_cancel(ctx, placed, monkeypatch):
    boundary, release = Event(), Event()
    # Depois da conferência da posse e da leitura do pagamento; antes do cancelamento.
    monkeypatch.setattr(
        payment_service, "captured_balance_q", _pause_after(payment_service.captured_balance_q, boundary, release)
    )
    effect = Worker(lambda: _cancel(ctx, placed))

    outcome = _handoff_wins_before_the_effect(effect, ctx.conversation.pk, boundary, release)

    assert _revoked(outcome), outcome
    placed.refresh_from_db()
    assert placed.status != Order.Status.CANCELLED
    assert not placed.events.filter(type="concierge_cancelled").exists()
    assert not ConversationMessage.objects.filter(
        conversation=ctx.conversation, text__startswith="Cancelado pela Concierge"
    ).exists()


def test_k12_cancel_committed_before_the_handoff_stands(ctx, placed, monkeypatch):
    boundary, release = Event(), Event()
    # Dentro da transação: o pedido já está cancelado, ainda não confirmado no banco.
    monkeypatch.setattr(customer_orders, "cancel", _pause_after(customer_orders.cancel, boundary, release))
    effect = Worker(lambda: _cancel(ctx, placed))

    outcome, current = _handoff_arrives_inside_the_effect(effect, ctx.conversation.pk, boundary, release)

    assert outcome.code == "cancelled", outcome
    placed.refresh_from_db()
    assert placed.status == Order.Status.CANCELLED
    assert placed.events.filter(type="concierge_cancelled").count() == 1
    note = ConversationMessage.objects.get(conversation=current, text__startswith="Cancelado pela Concierge")
    # Primeiro o cancelamento, depois a transferência: a fila é a da trava.
    assert note.pk < _handoff_note(current.pk).pk
    with pytest.raises(service.TurnRevoked):
        _cancel(ctx, placed)


# ── Acréscimo ────────────────────────────────────────────────────────


@pytest.fixture
def addition(ctx, customer):
    order = _order("NB-POSSE-1", customer.ref)
    _paid_cash(order, 180)
    asked = order_addition.propose(ctx.conversation, order_ref=order.ref, additions=[{"sku": SKU, "qty": 2}])
    assert asked.code == "asked", asked
    return order, asked.pending


def _add(ctx, pending):
    return order_addition.apply(worker_tool_context(ctx.conversation).conversation, pending)


def test_k11_items_are_not_added_when_the_team_takes_over_before_the_edit(ctx, addition, monkeypatch):
    order, pending = addition
    boundary, release = Event(), Event()
    # Depois da conferência da posse e da nova cotação; antes da edição do pedido.
    monkeypatch.setattr(order_addition, "propose", _pause_after(order_addition.propose, boundary, release))
    effect = Worker(lambda: _add(ctx, pending))

    outcome = _handoff_wins_before_the_effect(effect, ctx.conversation.pk, boundary, release)

    assert _revoked(outcome), outcome
    assert _unchanged(order)
    assert not ConversationMessage.objects.filter(
        conversation=ctx.conversation, text__startswith=order_addition.HISTORY_NOTE
    ).exists()


def test_k12_items_added_before_the_handoff_stand(ctx, addition, monkeypatch):
    order, pending = addition
    boundary, release = Event(), Event()
    # Dentro da transação: o pedido já foi editado, ainda não confirmado no banco.
    monkeypatch.setattr(order_edit, "edit", _pause_after(order_edit.edit, boundary, release))
    effect = Worker(lambda: _add(ctx, pending))

    outcome, current = _handoff_arrives_inside_the_effect(effect, ctx.conversation.pk, boundary, release)

    assert outcome.code == "added", outcome
    assert not _unchanged(order)
    assert order.events.filter(type="order_edited").count() == 1
    note = ConversationMessage.objects.get(conversation=current, text__startswith=order_addition.HISTORY_NOTE)
    assert note.pk < _handoff_note(current.pk).pk
    with pytest.raises(service.TurnRevoked):
        _add(ctx, pending)
