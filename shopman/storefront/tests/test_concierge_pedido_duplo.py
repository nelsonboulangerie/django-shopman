# ruff: noqa: F401, F811
"""A pergunta real do dono no teste ao vivo (24/11/2026), que saiu "gravíssima".

"Boa tarde / Tudo bem? / Ainda tem pão champagne e folhado de maçã?" chegou pela varredura (o deploy das
20h10Z a perdeu) e a Nice respondeu, 1h30 depois: "Não encontrei “pão champagne e folhado de maçã”".
Três defeitos:

1. duas coisas pedidas viraram um nome só: cada uma tem a resposta dela;
2. "champagne" é o "campagne" como o cliente fala: a casa acha os Campagne e pergunta qual;
3. a resposta que vem pela varredura saiu atrasada e não dizia: começa pedindo desculpa, numa frase.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from shopman.shop.models import ConversationBinding
from shopman.storefront.concierge import inbound_sweep, intents, service
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    PROVIDER,
    _binding,
    _listed,
    _receive,
    conversation,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db

OWNER = "Boa tarde\nTudo bem?\nAinda tem pão champagne e folhado de maçã?"
QUESTION = "Ainda tem pão champagne e folhado de maçã?"


@pytest.fixture
def menu(surface):
    """O cardápio do ar de 24/11, no que importa: três Campagne com estoque, folhado só de frango."""
    for sku, name in (("CPG", "Pain de Campagne"), ("CPR", "Campagne Redondo"),
                      ("CPX", "Campagne Passas & Castanhas"), ("FFGO", "Folhado de Frango"),
                      ("FENDU", "Fendu"), ("TABAT", "Tabatière")):
        _listed(sku, name, stock="10")


@pytest.fixture
def read_as_live(monkeypatch):
    """A leitura do ar: a IA leu as duas coisas como uma parte só."""
    from shopman.shop.tests.ai_support import configure_ai

    configure_ai("isolated-fixture", model="claude-sonnet-5")
    calls = []

    def read(text, **kwargs):
        calls.append(text)
        return [intents.Act(intents.PRODUCT, span=QUESTION, product="pão champagne e folhado de maçã")], 0.0, ""

    monkeypatch.setattr(intents, "read_with_model", read)
    # No ar o porteiro hesitou (o Jev não teve certeza) e a leitura foi à IA.
    monkeypatch.setattr(intents, "gate", lambda text, **kwargs: intents.GateDecision(False, "jev_unsure"))
    return calls


def _turn(conversation, text, event_id):
    _receive(conversation, text, event_id)
    return service.run_turn(conversation.pk, _binding(conversation).pk)


def _said(outbox) -> str:
    """Tudo o que a Nice mandou no turno (a saudação pode ir numa mensagem própria)."""
    return "\n\n".join(outbox.sent)


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS)
def test_two_things_asked_are_answered_each(conversation, outbox, menu, read_as_live):
    _turn(conversation, OWNER, "dono-1")
    reply = _said(outbox)
    assert read_as_live, "a leitura do ar (pela IA) rodou"
    assert "pão champagne e folhado de maçã" not in reply, reply  # nunca as duas como um nome só
    assert "folhado de maçã" in reply, reply  # a segunda tem a resposta dela: não temos


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS)
def test_champagne_is_the_campagne_and_the_nice_asks_which(conversation, outbox, menu, read_as_live):
    _turn(conversation, OWNER, "dono-2")
    reply = _said(outbox)
    for name in ("Pain de Campagne", "Campagne Redondo", "Campagne Passas & Castanhas"):
        assert name in reply, reply
    for unrelated in ("Fendu", "Tabatière"):
        assert unrelated not in reply, reply  # nada de pão sem relação na lista
    assert "Folhado de Frango" not in reply.split("folhado de maçã")[0], reply


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS)
def test_an_answer_to_a_message_recovered_by_the_sweep_opens_with_an_apology(conversation, outbox, menu,
                                                                              read_as_live, monkeypatch):
    binding = _binding(conversation)
    ConversationBinding.objects.filter(pk=binding.pk).update(last_inbound_at=timezone.now() - timedelta(minutes=90))
    monkeypatch.setattr(inbound_sweep, "PROVIDER", PROVIDER)
    monkeypatch.setattr(inbound_sweep, "_subscriber_info", lambda subject: {
        "last_input_text": OWNER, "last_interaction": "2024-06-11T08:12:12-03:00", "whatsapp_interaction": None})
    from shopman.storefront.tests.test_concierge_engine import _create_inbound

    _create_inbound(conversation, "obrigado", "antes")
    assert inbound_sweep.sweep()["reingested"] == 1

    service.run_turn(conversation.pk, binding.pk)

    assert outbox.sent[0].startswith("Desculpe a demora para responder."), outbox.sent


@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS)
def test_a_message_that_came_on_time_has_no_apology(conversation, outbox, menu, read_as_live):
    _turn(conversation, OWNER, "dono-3")
    assert "Desculpe a demora" not in _said(outbox), outbox.sent



@override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS)
def test_two_things_asked_are_answered_each_by_the_local_reading_too(conversation, outbox, menu):
    """Sem IA (o porteiro decide sozinho), a mesma pergunta tem as mesmas duas respostas."""
    _turn(conversation, OWNER, "dono-4")
    reply = _said(outbox)
    assert "champagne e folhado" not in reply, reply
    for name in ("Pain de Campagne", "Campagne Redondo", "Campagne Passas & Castanhas"):
        assert name in reply, reply
    assert "Não encontrei “folhado de maçã”" in reply, reply


def test_the_pieces_split_only_what_the_menu_does_not_name_together():
    menu = ["Romeu e Julieta", "Pain de Campagne", "Folhado de Frango"]
    assert intents.asked_pieces("pão champagne e folhado de maçã", menu) == ["pão champagne", "folhado de maçã"]
    assert intents.asked_pieces("romeu e julieta", menu) == ["romeu e julieta"]
    assert intents.asked_pieces("pão e manteiga", menu) == ["pão e manteiga"]  # "pão" sozinho não é coisa pedida


def test_a_word_out_of_the_menu_becomes_the_one_it_sounds_like():
    menu = ["Pain de Campagne", "Campagne Redondo", "Folhado de Frango", "Croissant"]
    assert intents.spelled_as_menu("pão champagne", menu) == ("pão campagne", ["campagne"])
    assert intents.spelled_as_menu("folhado de maçã", menu) == ("folhado de maçã", [])
    assert intents.spelled_as_menu("croissant", menu) == ("croissant", [])
