"""R8 antes da triagem (dono, 20/11/2026).

"Com quem eu falo?", "quem é você", "é robô?", "é uma pessoa?" recebem a frase fixa de
assistente da casa. A triagem não transforma a pergunta de quem atende em atendimento
humano, nem quando o Jev diz "human". Pedido de atendimento junto continua da equipe.
"""

from __future__ import annotations

import pytest

from shopman.shop.models import Conversation
from shopman.storefront.concierge import house_rules, service, triage
from shopman.storefront.tests import test_concierge_engine as engine
from shopman.storefront.tests.test_concierge_engine import _binding, _receive

surface = engine.surface
customer = engine.customer
conversation = engine.conversation
outbox = engine.outbox

REAL_PHRASES = ["com quem eu falo?", "quem é você", "é robô?", "é uma pessoa?"]
MORE_PHRASES = ["Com quem estou falando?", "quem tá falando?", "isso é atendimento automático?", "Quem é vc?"]


@pytest.fixture
def jev_says_human(monkeypatch):
    """O Jev ligado e convicto de que o cliente pede gente: o pior caso real."""
    monkeypatch.setattr(triage, "jev_enabled", lambda: True)
    monkeypatch.setattr(
        triage,
        "classify_with_jev",
        lambda text, **kwargs: {"intent": "human", "urgency": "now", "summary": "", "scores": {"human": 0.97}},
    )


@pytest.mark.parametrize("text", REAL_PHRASES + MORE_PHRASES)
def test_identity_question_gets_the_r8_phrase(text):
    rule, reply = house_rules.fixed_reply_for(text, shop_name="Casa", copy=lambda key: f"[{key}] {{shop_name}}")
    assert rule == "R8"
    assert reply == "[CONCIERGE_IDENTITY] Casa"


@pytest.mark.parametrize(
    "text",
    [
        "você é robô? quero falar com uma pessoa",
        "quero falar com uma pessoa",
        "tem croissant?",
        "quem faz o pão de vocês?",
    ],
)
def test_not_an_identity_answer(text):
    assert house_rules.fixed_reply_for(text, shop_name="Casa", copy=lambda key: key) == ("", "")


@pytest.mark.parametrize("text", REAL_PHRASES)
def test_triage_answers_identity_even_when_jev_says_human(text, jev_says_human):
    decision = triage.decide(text)
    assert decision.destination == triage.ANSWER
    assert not decision.escalates
    assert decision.answered_by == triage.IDENTITY_ANSWERED_BY


def test_human_request_with_identity_still_goes_to_the_team(jev_says_human):
    decision = triage.decide("você é robô? quero falar com uma pessoa")
    assert decision.escalates
    assert decision.intent == "human"


def test_allergy_with_identity_is_not_silenced():
    decision = triage.decide("é robô? tenho alergia grave a nozes")
    assert decision.answered_by != triage.IDENTITY_ANSWERED_BY


@pytest.mark.django_db
@pytest.mark.parametrize("text", REAL_PHRASES)
def test_turn_answers_with_the_r8_phrase_and_never_hands_off(text, conversation, outbox, jev_says_human):
    from shopman.backstage.services import alerts as alert_service

    _receive(conversation, text, f"r8-{REAL_PHRASES.index(text)}")
    result = service.run_turn(conversation.pk, _binding(conversation).pk)

    assert not result.handoff
    conversation.refresh_from_db()
    assert conversation.state != Conversation.State.HANDOFF
    assert conversation.flags["triage"]["answered_by"] == "identity"
    assert alert_service.list_active_alerts(scope="orders") == []
    reply = conversation.messages.filter(kind="reply").order_by("-pk").first()
    assert reply is not None and reply.text.startswith("Sou a assistente virtual da")
