"""A porta de equipe do framework sobre o "vou verificar" da Concierge (N7).

O que estes testes seguram, sobre o ``OperatorAlert`` real (o cartão ``concierge_verify``):

- a checagem de forma do framework (``run_checks("staff", ...)``) passa;
- roteado não é aceito: o cartão no sino é ``routed`` e não nomeia ninguém; só "Assumir"
  (``taken_over``) é aceite nominal; a resposta pelo cartão é fato com autoria;
- K20: a fila não aceita (conversa já com a equipe, ou sem prazo possível): nada abre, o
  tíquete é ``rejected``, e nada afirma aceite; passada à equipe pelo prazo sem ninguém
  assumir, continua sem aceite;
- K22: a promessa com prazo vence sem resposta: o prazo vira evento (o relógio do WP-06), o
  cartão escala e o cliente é avisado UMA vez;
- a época de posse da devolução só cresce.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from conversational_commerce.contracts import Known
from conversational_commerce.ports import PortError, StaffQuestion, TrustedContext
from conversational_commerce.testing.conformance import conformance
from conversational_commerce.testing.conformance.harness import HarnessEnv, run_checks
from conversational_commerce.testing.fakes.clock import FakeClock
from django.utils import timezone

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Conversation
from shopman.storefront.concierge import verification
from shopman.storefront.concierge.ports import subject_of
from shopman.storefront.concierge.staff_port import NiceStaff
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401 (fixtures)
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_verification import (  # noqa: F401 (fixtures)
    _cards,
    _receive,
    _record,
    plural,
)

pytestmark = pytest.mark.django_db

NUDGE = "Ainda estou confirmando com a equipe. Assim que eu tiver a resposta, te aviso por aqui."
QUESTION = "vocês fazem bolo de casamento?"


def ctx_of(conversation):  # noqa: F811
    return TrustedContext(tenant="nelson-boulangerie", environment="test", subject=subject_of(conversation.pk))


def ask(conversation, text=QUESTION):  # noqa: F811
    """O framework pergunta à equipe depois de uma entrada do cliente (vínculo e janela de 24h reais)."""
    _receive(conversation, text, f"staff-port-{conversation.messages.count()}")
    respond_by = (timezone.now() + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return NiceStaff().ask(ctx_of(conversation), StaffQuestion(episode_id=f"conversation-{conversation.pk}",
                                                               question=text, respond_by=respond_by))


def test_the_framework_shape_check_passes():
    env = HarnessEnv(ctx=TrustedContext(tenant="nelson-boulangerie", environment="test"), clock=FakeClock())
    assert run_checks("staff", NiceStaff(), env) == []


def test_routed_is_not_accepted_and_taking_over_is_the_nominal_acceptance(conversation, outbox):  # noqa: F811
    ticket = ask(conversation)
    assert ticket.state == "routed" and ticket.accepted_by is None
    assert _cards().count() == 1 and outbox.sent == []  # quem fala com o cliente é quem chamou
    staff = NiceStaff()
    assert staff.record_acceptance(ctx_of(conversation), ticket.ticket_id).accepted_by is None
    verification.take_over(_cards().get().pk, actor="ana")
    accepted = staff.record_acceptance(ctx_of(conversation), ticket.ticket_id)
    assert (accepted.state, accepted.accepted_by) == ("accepted", "ana")


def test_the_team_answer_is_an_authored_fact(conversation, outbox):  # noqa: F811
    ticket = ask(conversation)
    staff = NiceStaff()
    with pytest.raises(PortError) as unanswered:
        staff.promote_answer(ctx_of(conversation), ticket.ticket_id)
    assert unanswered.value.code.value == "fact_unavailable"
    assert verification.answer(_cards().get().pk, "Fazemos sim, por encomenda.", actor="bia").ok
    fact = staff.promote_answer(ctx_of(conversation), ticket.ticket_id)
    assert isinstance(fact, Known) and fact.source == "staff:bia"
    assert fact.value == {"answer": "Fazemos sim, por encomenda."} and fact.valid_until > fact.observed_at
    answered = staff.record_acceptance(ctx_of(conversation), ticket.ticket_id)
    assert answered.state == "answered" and answered.answer == fact


@conformance("K20", invariants=("N04", "N15"), scope="adapter")
def test_k20_the_queue_does_not_accept_and_nothing_claims_acceptance(conversation, outbox):  # noqa: F811
    # A conversa já está com a equipe: a fila da Concierge não recebe, e nada abre.
    Conversation.objects.filter(pk=conversation.pk).update(state=Conversation.State.HANDOFF)
    rejected = ask(conversation)
    assert rejected.state == "rejected" and rejected.accepted_by is None
    assert not _cards().exists() and _record(conversation) is None and outbox.sent == []

    # Passada à equipe pelo prazo, sem ninguém assumir: continua sem aceite de ninguém.
    Conversation.objects.filter(pk=conversation.pk).update(state=Conversation.State.ACTIVE)
    ticket = ask(conversation)
    record = _record(conversation)
    verification.sweep(now=datetime.fromisoformat(record["handoff_due_at"]))
    still = NiceStaff().record_acceptance(ctx_of(conversation), ticket.ticket_id)
    assert _record(conversation)["status"] != verification.OPEN
    assert still.state == "routed" and still.accepted_by is None


@conformance("K22", invariants=("N04",), scope="adapter")
def test_k22_the_deadline_passes_the_card_escalates_and_the_customer_is_told_once(conversation, outbox):  # noqa: F811
    ask(conversation)
    due = datetime.fromisoformat(_record(conversation)["nudge_due_at"])
    sent = len(outbox.sent)
    assert verification.sweep(now=due)["nudged"] == 1  # o prazo vencido vira evento
    assert verification.sweep(now=due + timedelta(minutes=1))["nudged"] == 0
    assert outbox.sent[sent:] == [NUDGE], "o cliente é avisado uma vez só"
    card = OperatorAlert.objects.get(type=verification.ALERT_TYPE)
    assert card.respond_by == due and card.resolved_at is None
    assert _record(conversation)["nudged_at"]


def test_the_ownership_epoch_of_a_return_only_grows():
    staff = NiceStaff()
    ctx = TrustedContext(tenant="nelson-boulangerie", environment="test")
    assert staff.return_conversation(ctx, "episodio-x", 3).new_epoch == 3
    for epoch in (3, 2):
        with pytest.raises(PortError) as conflict:
            staff.return_conversation(ctx, "episodio-x", epoch)
        assert conflict.value.code.value == "revision_conflict"
    assert staff.return_conversation(ctx, "episodio-x", 4).new_epoch == 4


def test_assigning_is_not_a_thing_on_the_bell():
    with pytest.raises(PortError) as missing:
        NiceStaff().assign(TrustedContext(tenant="t", environment="test"), "c-1", "ana")
    assert missing.value.code.value == "capability_missing"
