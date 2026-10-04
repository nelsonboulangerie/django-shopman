# ruff: noqa: F811
"""Acrescentar a pedido já feito pela Concierge (OBS0310-P, dono 03/10/2026).

"Se é possível fazer dentro dos guardrails do sistema, via PDV, por que a
Concierge não poderia fazer?" O que se prova aqui:

- dentro da etapa: a pergunta de uma linha traz os dados do sistema (itens,
  pedido, total novo, saldo) e só o "sim" aplica, pelo MESMO serviço do PDV
  (``order_edit``), com o histórico "Itens acrescentados pela Concierge a pedido
  do cliente"; o cliente recebe UMA mensagem (a resposta leva o total novo e o
  destino da diferença, e o aviso ``order_updated`` não sai);
- pedido pago: a diferença vira saldo a receber, como no balcão;
- fora da etapa, NFC-e autorizada, iFood, sem estoque: nada muda, o motivo é o
  verdadeiro; no pedido do dia, a oferta de pedido novo; na encomenda, a equipe
  já chamada na mesma mensagem (handoff de verdade);
- "não": nada muda;
- pedido de outra pessoa: não é achado;
- o valor mudou entre a pergunta e o "sim": pergunta de novo.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.payman import PaymentService

from shopman.shop.models import ConversationMessage
from shopman.shop.services import order_composition, order_edit, payment, stock
from shopman.storefront.concierge import dialogue, order_addition, service
from shopman.storefront.concierge.dialogue import Facts, OrderFact
from shopman.storefront.concierge.dialogue_eval import registry_copy
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401  (fixtures)
    CHANNEL,
    CONCIERGE_SETTINGS,
    SKU,
    ScriptedClient,
    _binding,
    _create_inbound,
    _receive,
    _reclaim,
    _seed_stock,
    conversation,
    ctx,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db

PRICE_Q = 90


def _order(ref: str, owner_ref: str, *, offset: int = 0, qty: int = 2, status=Order.Status.ACCEPTED,
           channel: str = CHANNEL, **data) -> Order:
    day = timezone.localdate() + timedelta(days=offset)
    total = PRICE_Q * qty
    order = Order.objects.create(
        ref=ref,
        channel_ref=channel,
        session_key=f"SESS-{ref}",
        status=status,
        snapshot={"items": [{"line_id": "L1", "sku": SKU, "name": "Pão Francês", "qty": qty, "unit_price_q": PRICE_Q}]},
        data={
            "customer_ref": owner_ref,
            "fulfillment_type": "pickup",
            "payment": {"method": "cash"},
            "delivery_date": day.isoformat(),
            "delivery_time_slot": "slot-09",
            **data,
        },
        total_q=total,
    )
    OrderItem.objects.create(
        order=order, line_id="L1", sku=SKU, name="Pão Francês", qty=qty, unit_price_q=PRICE_Q, line_total_q=total,
    )
    if channel != "ifood":
        stock.hold(order)
    order.refresh_from_db()
    return order


def _paid_cash(order, amount_q: int) -> None:
    intent = PaymentService.settle(order.ref, amount_q, "cash", idempotency_key=f"test:{order.ref}:cash")
    data = dict(order.data)
    data["payment"] = {**(data.get("payment") or {}), "method": "cash", "intent_ref": intent.ref}
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def _unchanged(order) -> bool:
    order.refresh_from_db()
    return not order_composition.is_adjusted(order) and not order.events.filter(type="order_edited").exists()


def _notices(order):
    return Directive.objects.filter(
        topic="notification.send", payload__order_ref=order.ref, payload__template="order_updated",
    )


# ── Dentro da etapa ───────────────────────────────────────────────────


def test_inside_the_stage_asks_with_system_data_and_applies_only_on_yes(ctx, customer):
    order = _order("NB-ADD-1", customer.ref)
    _paid_cash(order, 180)

    asked = order_addition.propose(ctx.conversation, order_ref="NB-ADD-1", additions=[{"sku": SKU, "qty": 2}])

    assert asked.code == "asked"
    assert asked.text == (
        "Acrescento 2 Pão Francês ao pedido NB-ADD-1, retirada hoje a partir das 9h? "
        "Total novo R$ 3,60, saldo a pagar R$ 1,80. Responda sim ou não."
    )
    assert asked.pending["kind"] == dialogue.CONFIRM_ADD and asked.pending["total_q"] == 360
    # A pergunta não muda nada.
    assert _unchanged(order)

    done = order_addition.apply(ctx.conversation, asked.pending)

    assert done.code == "added"
    assert done.text == (
        "Pronto, acrescentei 2 Pão Francês ao pedido NB-ADD-1. "
        "O novo total é R$ 3,60. A diferença de R$ 1,80 fica para a retirada. 💛"
    )
    order.refresh_from_db()
    record = order_composition.adjustment(order)
    assert record["source"] == order_edit.CONCIERGE_SOURCE and record["event_id"] == "concierge-edit:NB-ADD-1:1"
    assert order_composition.effective_total_q(order) == 360
    # O selado continua intacto.
    assert order.total_q == 180
    # Pedido pago: a diferença é saldo a receber, como no balcão.
    assert payment.balance_due_q(order) == 180
    # Histórico: quem fez e a frase do cliente.
    event = order.events.get(type="order_edited")
    assert event.actor == "concierge" and event.payload["source"] == "concierge:add"
    from shopman.backstage.projections.order_queue import _build_timeline

    labels = [row.label for row in _build_timeline(order)]
    assert "Itens acrescentados pela Concierge a pedido do cliente" in labels
    # A conversa registra para quem lê no Admin. Uma mensagem só ao cliente: a da
    # Concierge; o aviso ``order_updated`` não sai nesse caso.
    assert ConversationMessage.objects.filter(
        conversation=ctx.conversation, kind=ConversationMessage.Kind.NOTE,
        text__startswith="Itens acrescentados pela Concierge a pedido do cliente",
    ).exists()
    assert not _notices(order).exists()


def test_value_changed_between_question_and_yes_asks_again(ctx, customer):
    order = _order("NB-ADD-2", customer.ref)
    asked = order_addition.propose(ctx.conversation, order_ref=order.ref, additions=[{"sku": SKU, "qty": 1}])
    stale = {**asked.pending, "total_q": asked.pending["total_q"] - 10}

    again = order_addition.apply(ctx.conversation, stale)

    assert again.code == "asked" and again.pending["total_q"] == asked.pending["total_q"]
    assert _unchanged(order)


# ── Fora da etapa e portas fechadas ───────────────────────────────────


def test_ready_order_refuses_with_the_true_reason_and_offers_a_new_order(ctx, customer):
    order = _order("NB-ADD-3", customer.ref, status=Order.Status.READY)

    refused = order_addition.propose(ctx.conversation, order_ref=order.ref, additions=[{"sku": SKU, "qty": 2}])

    assert refused.code == "refused"
    assert refused.text == (
        "O pedido NB-ADD-3 já está pronto, e aí não dá mais para acrescentar itens nele. "
        "Quer que eu faça um pedido novo com 2 Pão Francês? Responda sim ou não."
    )
    assert refused.pending == {"kind": dialogue.CONFIRM_NEW, "order_ref": order.ref, "item": "2 Pão Francês"}
    assert _unchanged(order)


def test_authorized_nfce_on_a_preorder_refuses_and_offers_the_team(ctx, customer):
    order = _order("NB-ADD-4", customer.ref, offset=3, nfce_access_key="4126" + "0" * 40)

    refused = order_addition.propose(ctx.conversation, order_ref=order.ref, additions=[{"sku": SKU, "qty": 2}])

    assert refused.code == "refused" and refused.handoff and refused.pending is None
    assert refused.text == (
        "A nota fiscal desse pedido já foi emitida, e aí não dá mais para acrescentar itens nele. "
        "Já chamei a equipe para ver isso com você."
    )
    assert "NB-ADD-4" in refused.handoff_reason and "2 Pão Francês" in refused.handoff_reason
    assert _unchanged(order)


def test_ifood_order_is_changed_on_ifood(ctx, customer):
    order = _order("NB-ADD-5", customer.ref, channel="ifood")

    refused = order_addition.propose(ctx.conversation, order_ref=order.ref, additions=[{"sku": SKU, "qty": 2}])

    assert refused.code == "refused" and "pelo próprio iFood" in refused.text
    assert _unchanged(order)


def test_out_of_stock_refuses_on_the_question(ctx, customer):
    order = _order("NB-ADD-6", customer.ref)  # 10 em estoque, 2 reservados por este pedido

    refused = order_addition.propose(ctx.conversation, order_ref=order.ref, additions=[{"sku": SKU, "qty": 50}])

    assert refused.code == "refused" and refused.text.startswith("50 Pão Francês está indisponível")
    assert _unchanged(order)


def test_stock_gone_between_question_and_yes_refuses_and_nothing_changes(ctx, customer):
    order = _order("NB-ADD-7", customer.ref)
    asked = order_addition.propose(ctx.conversation, order_ref=order.ref, additions=[{"sku": SKU, "qty": 8}])
    assert asked.code == "asked"
    # Outro pedido levou o resto antes do "sim".
    _order("NB-OTHER-7", "outro-cliente", qty=8)

    refused = order_addition.apply(ctx.conversation, asked.pending)

    assert refused.code == "refused" and "indisponível" in refused.text
    assert _unchanged(order)
    assert not _notices(order).exists()


def test_someone_elses_order_is_not_found(ctx, customer):
    order = _order("NB-ADD-8", "outro-cliente")

    refused = order_addition.propose(ctx.conversation, order_ref=order.ref, additions=[{"sku": SKU, "qty": 1}])

    assert refused.code == "refused" and refused.text.startswith("Não achei esse pedido entre os seus pedidos.")
    assert "NB-ADD-8" not in refused.text.split("?")[0].replace("Não achei esse pedido", "")
    assert _unchanged(order)
    # Nem com o "sim" forjado na memória.
    forged = {"kind": dialogue.CONFIRM_ADD, "order_ref": order.ref, "add": [{"sku": SKU, "qty": 1}], "total_q": 270}
    assert order_addition.apply(ctx.conversation, forged).code == "refused"
    assert _unchanged(order)


def test_without_commercial_authority_nothing_changes(ctx, customer):
    order = _order("NB-ADD-9", customer.ref)
    ctx.conversation._commercial_authority = False

    refused = order_addition.propose(ctx.conversation, order_ref=order.ref, additions=[{"sku": SKU, "qty": 1}])

    assert refused.code == "refused" and refused.handoff
    assert _unchanged(order)


# ── A memória: "1", "sim" e "não" ─────────────────────────────────────

NOW = timezone.now()


def _state(*memos):
    return dialogue.next_state({}, list(memos), now=NOW, fence=1, until=NOW + timedelta(days=1))


def _resolve(text, state, facts):
    return dialogue.resolve(text, dialogue.effective(state, facts), facts, copy=registry_copy)


def test_choosing_1_with_the_product_known_goes_to_the_question_without_the_model():
    order = OrderFact("P7", "accepted", "pedido P7, retirada hoje", "pickup")
    facts = Facts(now=NOW, open_order=order, order_status={"P7": "accepted"})
    state = _state({"tool": "set_item", "ref": "CROISSANT", "name": "Croissant", "qty": 2})
    asked = _resolve("mais 4", state, facts)
    assert asked.reason == "ask_order_or_new"
    state = dialogue.next_state(state, [asked.memo], now=NOW, fence=2, until=NOW + timedelta(days=1))

    add = _resolve("1", state, facts)

    assert add.outcome == "add_preview" and add.answers_without_model
    assert add.request == {"order_ref": "P7", "add": [{"sku": "CROISSANT", "qty": 4}], "item": "4 Croissant"}


def test_yes_applies_and_no_keeps_the_order_as_it_is():
    facts = Facts(now=NOW, order_status={"P7": "accepted"})
    pending = {"kind": dialogue.CONFIRM_ADD, "order_ref": "P7", "add": [{"sku": "CROISSANT", "qty": 4}],
               "total_q": 1000, "item": "4 Croissant", "day": NOW.date().isoformat()}
    state = _state({"pending": pending})

    yes = _resolve("sim", state, facts)
    assert yes.outcome == "add_apply" and yes.request["order_ref"] == "P7"
    no = _resolve("não", state, facts)
    assert no.outcome == "ask" and no.reason == "declined" and no.memo == {"pending": None}
    # Pedido que fechou não recebe o "sim".
    closed = Facts(now=NOW, order_status={"P7": "delivered"})
    assert _resolve("sim", state, closed).outcome != "add_apply"


# ── O turno de verdade ────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_turn_one_then_yes_adds_through_the_same_service(conversation, customer, outbox, settings):
    from shopman.shop.models import Conversation

    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    settings.AI_ASSIST_API_KEY = "sk-teste"
    order = _order("NB-ADD-T", customer.ref)
    now = timezone.now()
    pending = {"kind": dialogue.CHOOSE_ORDER, "order_ref": order.ref, "item": "2 Pão Francês", "sku": SKU, "qty": 2}
    state = dialogue.next_state({}, [{"pending": pending}], now=now, fence=1, until=now + timedelta(days=1))
    Conversation.objects.filter(pk=conversation.pk).update(flags={"dialogue": state})

    _receive(conversation, "1", "add-1")
    asked = service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())
    assert asked.replies[0].startswith("Acrescento 2 Pão Francês ao pedido NB-ADD-T")
    assert _unchanged(order)

    _receive(conversation, "sim", "add-2")
    done = service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())
    assert done.replies[0].startswith("Pronto, acrescentei 2 Pão Francês ao pedido NB-ADD-T")
    order.refresh_from_db()
    assert order_composition.effective_total_q(order) == 360
    assert order.events.get(type="order_edited").payload["source"] == "concierge:add"


@pytest.mark.django_db(transaction=True)
def test_turn_refused_preorder_says_why_and_the_team_is_really_called(conversation, customer, outbox, settings):
    from shopman.shop.models import Conversation

    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    settings.AI_ASSIST_API_KEY = "sk-teste"
    order = _order("NB-ADD-E", customer.ref, offset=3, nfce_access_key="4126" + "0" * 40)
    now = timezone.now()
    pending = {"kind": dialogue.CHOOSE_ORDER, "order_ref": order.ref, "item": "2 Pão Francês", "sku": SKU, "qty": 2}
    state = dialogue.next_state({}, [{"pending": pending}], now=now, fence=1, until=now + timedelta(days=1))
    Conversation.objects.filter(pk=conversation.pk).update(flags={"dialogue": state})

    _receive(conversation, "1", "add-e1")
    result = service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())

    assert result.handoff
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert "NB-ADD-E" in conversation.handoff_reason
    # Uma mensagem: o motivo verdadeiro e a equipe já chamada (a R6 deixa sair: há o recibo).
    assert outbox.sent == [
        "A nota fiscal desse pedido já foi emitida, e aí não dá mais para acrescentar itens nele. "
        "Já chamei a equipe para ver isso com você."
    ]
    assert _unchanged(order)
