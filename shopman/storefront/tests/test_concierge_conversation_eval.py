"""Placar de conversa: a conversa do dono em 21/11 lida turno a turno, com a coluna do ManyChat."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage
from shopman.storefront.concierge import conversation_eval

pytestmark = pytest.mark.django_db

INTENTS_PRODUCT = {"version": 1, "layer": "intents", "latency_ms": {"total": 3400},
                   "intents": {"acts": [{"act": "order", "span": "quero 2 croissant"}]}}


def _binding(conversation):
    return conversation.transport_bindings.first() or ConversationBinding.objects.create(
        conversation=conversation, provider="manychat", account="bakery-primary", transport_channel="whatsapp",
        subject=f"sub-{conversation.pk}", connection_key="manychat-whatsapp-primary",
        status=ConversationBinding.Status.ACTIVE, identity_assurance="transport_subject",
    )


def _say(conversation, text):
    return ConversationMessage.objects.create(
        conversation=conversation, binding=_binding(conversation), role=ConversationMessage.Role.USER, kind=ConversationMessage.Kind.INBOUND, text=text
    )


def _reply(conversation, text, usage=None):
    return ConversationMessage.objects.create(
        conversation=conversation, binding=_binding(conversation), role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY,
        text=text, usage=usage or {},
    )


def _note(conversation, text):
    return ConversationMessage.objects.create(
        conversation=conversation, role=ConversationMessage.Role.ASSISTANT, kind=ConversationMessage.Kind.NOTE, text=text
    )


@pytest.fixture
def conversation():
    conv = Conversation.objects.create(phone="+5543999990000", last_inbound_at=timezone.now())
    _say(conv, "quero 2 croissant")
    _reply(conv, "Croissant: Indisponível.", INTENTS_PRODUCT)
    _say(conv, "o que teria disponivel?")
    _reply(conv, "Hoje temos Pão de ensaio A e Pão de ensaio B. Quer que eu separe algum?",
           {"intents": {"acts": [{"act": "product_question"}]}})
    _say(conv, "tem bagel?")
    _reply(conv, "Bagel: Indisponível. Bagel: Indisponível.", {"intents": {"acts": [{"act": "product_question"}]}})
    _note(conv, "Atendimento humano solicitado. Contexto preservado.")
    _say(conv, "oi?")  # a equipe está com a conversa: silêncio legítimo
    _note(conv, "Voltou para o concierge.")
    _say(conv, "alguém aí?")  # de volta à casa, e ninguém respondeu
    return conv


def test_reads_the_real_conversation_turn_by_turn(conversation):
    turns = conversation_eval.read_turns(days=1)
    outcomes = [conversation_eval.outcome_of(t.evidence) for t in turns]
    assert outcomes == ["dead_end", "useful", "dead_end", None, "silent"]
    assert turns[0].evidence.needs_live_data and turns[0].evidence.needs_action
    assert turns[2].evidence.repeated
    assert turns[0].evidence.latency_ms == 3400


def test_manychat_column_says_why_it_would_not_reach(conversation):
    turns = conversation_eval.read_turns(days=1)
    reach = [conversation_eval.incumbent_reach(t.evidence, conversation_eval.MANYCHAT_INSTAGRAM) for t in turns]
    assert reach[0] == "no_live_data"  # estoque do dia: a IA do ManyChat não enxerga
    assert {conversation_eval.incumbent_reach(t.evidence, conversation_eval.MANYCHAT_WHATSAPP) for t in turns} == {
        "no_free_text"
    }


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Croissant: Indisponível.", False),
        ("Não tenho essa informação.", False),
        ("Croissant acabou. Temos pain au chocolat, quer?", True),
        ("Vou verificar com a equipe e já te respondo.", True),
        ("Pronto, 2 croissants na sua sacola.", True),
        ("Croissant volta amanhã a partir das 7h.", True),
    ],
)
def test_next_step_reader(reply, expected):
    assert conversation_eval.has_next_step(reply) is expected


def test_command_prints_the_scorecard_and_the_turns_to_fix(conversation, capsys):
    call_command("concierge_conversation_eval", "--days", "1")
    out = capsys.readouterr().out
    assert "útil (com lastro e próximo passo): 1/4" in out
    assert "silêncio (ninguém respondeu): 1/4" in out
    # Estimativa pela documentação, nunca medição (dono, 21/11/2026), com a premissa dita.
    assert "ManyChat AI no WhatsApp (estimado pela documentação, não medido) alcançaria 0/4" in out
    assert "premissa: no WhatsApp a IA só reconhece intenção" in out
    assert "ManyChat AI faria" not in out
    assert "pronto (0 sem lastro, 0 silêncio, útil >= 90%): não" in out
    assert "cliente: quero 2 croissant" in out


def test_scorecard_shows_the_ladder_and_the_spend_per_day(conversation, capsys):
    reply = conversation.messages.filter(kind="reply").order_by("pk").first()
    reply.usage = {**reply.usage, "cost_usd": 0.00002}
    reply.envelope = {"ladder": {"chosen": "concierge_rewrite", "cost_usd": 0.0003, "attempts": [
        {"source": "house", "conference": {"checks": {"useful": {"status": "fail", "reason": "no_next_step"}}}},
        {"source": "concierge_rewrite", "text": "Croissant acabou. Quer pain au chocolat?",
         "conference": {"checks": {"useful": {"status": "pass"}}}},
    ]}}
    reply.save()

    call_command("concierge_conversation_eval", "--days", "1")
    out = capsys.readouterr().out

    assert "escada (sombra): 1 subidas; escolheria concierge_rewrite 1; pauta (motivos): useful:no_next_step 1" in out
    assert "US$ 0.0003" in out
    assert "escada escolheria: concierge_rewrite · Croissant acabou. Quer pain au chocolat?" in out


def test_unanswered_turns_right_before_a_return_note_were_with_the_team():
    """19/11: "Apenas testando" e "Olá" sem resposta, e a nota "Voltou para o concierge" depois,
    sem a nota de entrada no período. Era a equipe, não silêncio da Concierge."""
    conv = Conversation.objects.create(phone="+5543999990001", last_inbound_at=timezone.now())
    _say(conv, "Apenas testando")
    _say(conv, "Olá")
    _note(conv, "Voltou para o concierge.")
    _say(conv, "com quem eu falo?")
    _reply(conv, "Sou a assistente virtual da loja. Em que posso ajudar?")

    turns = conversation_eval.read_turns(days=1, conversation_id=conv.pk)

    assert [conversation_eval.outcome_of(t.evidence) for t in turns] == [None, "useful"]
