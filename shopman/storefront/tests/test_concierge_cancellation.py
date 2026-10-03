"""Cancelamento pela Concierge, conforme a etapa (dono, 03/10/2026).

A Concierge cancela sozinha exatamente quando o próprio cliente poderia cancelar
pelo site (``customer_orders.can_cancel``), pelo mesmo serviço, depois de um "sim".
Fora disso, a regra da casa R4: a equipe. O pedido registra quem cancelou e por quê.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Conversation, ConversationMessage
from shopman.storefront.concierge import cancellation, service, tools
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401  (fixtures)
    ScriptedClient,
    _accept_review,
    _binding,
    _pickup_ready,
    _receive,
    conversation,
    ctx,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def placed(ctx, django_capture_on_commit_callbacks):  # noqa: F811
    """Um pedido da cliente pelo WhatsApp, recém-registrado (Pix pendente)."""
    review = _pickup_ready(ctx)
    _accept_review(ctx, review)
    with django_capture_on_commit_callbacks(execute=True):
        result = tools.place_order(ctx, review["quote_token"], "pix", "")
    assert result["ok"], result
    # O que veio antes fica consumido: o turno de agora começa na próxima fala.
    ConversationMessage.objects.filter(
        conversation=ctx.conversation, kind=ConversationMessage.Kind.INBOUND
    ).update(consumed_by=1)
    Conversation.objects.filter(pk=ctx.conversation.pk).update(claim_until=None, session_key="")
    return Order.objects.get(ref=result["order_ref"])


def _turn(conversation, text: str, django_capture_on_commit_callbacks):  # noqa: F811
    _receive(conversation, text, f"cancel-{ConversationMessage.objects.count()}-{timezone.now().timestamp()}")
    with django_capture_on_commit_callbacks(execute=True):
        # Roteiro vazio: nenhum destes turnos pode chegar ao modelo.
        return service.run_turn(conversation.pk, _binding(conversation).pk, client=ScriptedClient())


def test_within_the_window_she_asks_and_cancels_on_yes(placed, conversation, outbox, django_capture_on_commit_callbacks):  # noqa: F811
    asked = _turn(conversation, "Quero cancelar meu pedido", django_capture_on_commit_callbacks)

    assert not asked.handoff
    assert asked.triage.answered_by == "self_cancel"
    assert outbox.sent[-1] == f"Cancelo o pedido {placed.ref}, com 2 Pão Francês? Responda sim ou não."
    placed.refresh_from_db()
    assert placed.status == "new"

    done = _turn(conversation, "sim", django_capture_on_commit_callbacks)

    assert not done.handoff and done.triage.answered_by == "cancel_answer"
    placed.refresh_from_db()
    assert placed.status == "cancelled"
    assert placed.data["cancelled_by"] == "concierge"
    assert placed.data["cancellation_reason"] == "customer_requested"
    # O que a resposta diz do pagamento é lido do sistema depois do cancelamento
    # (aqui o lifecycle roda no fim do bloco de teste; em produção, no commit).
    assert outbox.sent[-1].startswith(f"Pronto, cancelei o pedido {placed.ref}, como você pediu. ")
    assert "nada foi cobrado" in outbox.sent[-1].lower()
    from shopman.shop.services import payment

    assert payment.get_payment_status(placed) == "cancelled"
    event = placed.events.get(type="concierge_cancelled")
    assert event.actor == "concierge"
    assert event.payload["note"] == 'Cancelado pela Concierge a pedido do cliente: "Quero cancelar meu pedido"'
    # A transição também carrega o ator, e o Gestor lê o rótulo em português.
    assert placed.events.filter(type="status_changed", actor="concierge").exists()
    from shopman.backstage.projections.order_queue import _build_timeline

    assert "Cancelado pela Concierge a pedido do cliente" in [row.label for row in _build_timeline(placed)]
    note = conversation.messages.get(kind=ConversationMessage.Kind.NOTE)
    assert placed.ref in note.text
    conversation.refresh_from_db()
    assert cancellation.PENDING_FLAG not in conversation.flags


def test_customer_says_no_and_the_order_stays(placed, conversation, outbox, django_capture_on_commit_callbacks):  # noqa: F811
    _turn(conversation, "Quero cancelar meu pedido", django_capture_on_commit_callbacks)
    kept = _turn(conversation, "não, obrigada", django_capture_on_commit_callbacks)

    assert not kept.handoff
    assert outbox.sent[-1] == f"Combinado, o pedido {placed.ref} segue como está."
    placed.refresh_from_db()
    assert placed.status == "new"
    assert not placed.events.filter(type="concierge_cancelled").exists()


def test_a_later_yes_about_something_else_never_cancels(placed, conversation, outbox, django_capture_on_commit_callbacks):  # noqa: F811
    _turn(conversation, "Quero cancelar meu pedido", django_capture_on_commit_callbacks)
    conversation.refresh_from_db()
    state = dict(conversation.flags[cancellation.PENDING_FLAG])
    state["asked_at"] = (timezone.now() - cancellation.PENDING_TTL - timedelta(minutes=1)).isoformat()
    Conversation.objects.filter(pk=conversation.pk).update(flags={**conversation.flags, cancellation.PENDING_FLAG: state})

    assert cancellation.resolve_pending(Conversation.objects.get(pk=conversation.pk), "sim") is None
    placed.refresh_from_db()
    assert placed.status == "new"


def test_out_of_the_window_goes_to_the_team(placed, conversation, outbox, django_capture_on_commit_callbacks):  # noqa: F811
    # Aceito e em preparo: o cliente já não cancela pelo site, então a Concierge também não.
    placed.transition_status("accepted", actor="test")
    placed.transition_status("preparing", actor="test")

    result = _turn(conversation, "Quero cancelar meu pedido", django_capture_on_commit_callbacks)

    assert result.handoff
    assert result.triage.escalated_by == "cancel_order"
    placed.refresh_from_db()
    assert placed.status == "preparing"
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert cancellation.PENDING_FLAG not in (conversation.flags or {})


def test_paid_order_is_not_self_cancellable_and_goes_to_the_team(placed, conversation, outbox, django_capture_on_commit_callbacks):  # noqa: F811
    # Pago: o site também não deixa o cliente cancelar (o estorno é decisão da equipe).
    from shopman.shop.services import payment

    with django_capture_on_commit_callbacks(execute=True):
        assert payment.mock_confirm(placed)
    placed.refresh_from_db()

    result = _turn(conversation, "Quero cancelar meu pedido", django_capture_on_commit_callbacks)

    assert result.handoff and result.triage.escalated_by == "cancel_order"
    placed.refresh_from_db()
    assert placed.status != "cancelled"
    assert not placed.events.filter(type="concierge_cancelled").exists()


def test_it_changed_stage_between_question_and_yes_so_the_team_takes_it(placed, conversation, outbox, django_capture_on_commit_callbacks):  # noqa: F811
    _turn(conversation, "Quero cancelar meu pedido", django_capture_on_commit_callbacks)
    placed.transition_status("accepted", actor="test")
    placed.transition_status("preparing", actor="test")

    result = _turn(conversation, "sim", django_capture_on_commit_callbacks)

    assert result.handoff
    placed.refresh_from_db()
    assert placed.status == "preparing"


def test_someone_elses_order_is_never_cancelled(placed, conversation, outbox, django_capture_on_commit_callbacks):  # noqa: F811
    # O pedido é de outra pessoa (outro cliente, outro telefone); a fala cita o número dele.
    data = dict(placed.data)
    data["customer_ref"] = "OUTRA-PESSOA"
    data["customer"] = {"name": "Outra", "phone": "+5543999990000", "ref": "OUTRA-PESSOA"}
    Order.objects.filter(pk=placed.pk).update(data=data, handle_ref="+5543999990000")

    result = _turn(conversation, f"Cancela o pedido {placed.ref}", django_capture_on_commit_callbacks)

    assert result.handoff
    placed.refresh_from_db()
    assert placed.status == "new"
    assert cancellation.target_order(conversation, f"cancela o pedido {placed.ref}") is None


def test_a_cited_number_must_be_one_of_hers(placed, conversation):  # noqa: F811
    conversation._commercial_authority = True
    code = placed.ref.rsplit("-", 1)[-1]
    assert cancellation.target_order(conversation, f"cancela o {code}") == placed
    assert cancellation.target_order(conversation, "cancela o pedido NB-261003-Z99") is None


def test_payment_line_says_only_what_the_system_did():
    card = SimpleNamespace(data={"payment": {"method": "card"}})
    pix = SimpleNamespace(data={"payment": {"method": "pix"}})
    counter = SimpleNamespace(data={})
    line = cancellation._payment_line
    assert line(card, had_intent=True, status_before="authorized", captured_before=0, status_after="cancelled") == (
        "A reserva no cartão foi desfeita, e nada foi cobrado."
    )
    assert line(pix, had_intent=True, status_before="pending", captured_before=0, status_after="cancelled") == (
        "O pagamento pendente foi cancelado, e nada foi cobrado."
    )
    assert line(pix, had_intent=True, status_before="captured", captured_before=500, status_after="refunded") == (
        "O valor pago, R$ 5,00, foi estornado pelo mesmo meio de pagamento."
    )
    assert line(pix, had_intent=True, status_before="captured", captured_before=500, status_after="captured") == (
        "O estorno do valor pago, R$ 5,00, foi pedido ao meio de pagamento."
    )
    assert line(counter, had_intent=False, status_before="", captured_before=0, status_after="") == ""

