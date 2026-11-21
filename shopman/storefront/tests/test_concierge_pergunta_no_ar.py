# ruff: noqa: F401, F811
"""A pergunta no ar sobrevive (ensaio do dono no WhatsApp, 21/11/2026, 11h55 UTC).

A casa perguntou "Qual deles? 1) Baguette de Tradition; 2) Jambon-Beurre". O cliente:
"ainda está aí?" → a casa respondeu "De qual produto você está falando?" (o "esta" sem
acento lido como "esta aqui"); "as 2 baguettes que pedi" → a casa mostrou um pedido de
17/11. A pergunta no ar tem que continuar no ar.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings as django_settings

from shopman.storefront.concierge import dialogue
from shopman.storefront.concierge.dialogue import Facts
from shopman.storefront.concierge.dialogue_eval import registry_copy

NOW = datetime(2026, 11, 21, 9, 0, tzinfo=ZoneInfo(django_settings.TIME_ZONE))
OPTIONS = [{"n": 1, "ref": "BAGUETTE", "name": "Baguette de Tradition"},
           {"n": 2, "ref": "JAMBON", "name": "Jambon-Beurre"}]
STATE = {"v": dialogue.VERSION, "valid_until": "2026-11-21T23:00:00-03:00",
         "pending": {"kind": dialogue.CHOOSE, "options": OPTIONS},
         "listed": [dict(o) for o in OPTIONS]}


def _resolve(text, state=None):
    facts = Facts(now=NOW)
    return dialogue.resolve(text, dialogue.effective(dict(state or STATE), facts), facts, copy=registry_copy)


@pytest.mark.parametrize("text", ["ainda está aí?", "tá aí?", "alô?", "alguém aí?", "oi, você está aí?"])
def test_still_there_reasks_the_pending_choice(text):
    resolution = _resolve(text)
    assert resolution.outcome == "ask" and resolution.reason == "still_here"
    assert resolution.reply == "Estou aqui, sim! Qual deles? 1) Baguette de Tradition; 2) Jambon-Beurre"


def test_still_there_without_pending_question_offers_help():
    resolution = _resolve("ainda está aí?", state={"v": dialogue.VERSION})
    assert resolution.reply == "Estou aqui, sim! Em que posso ajudar?"


def test_naming_one_option_chooses_it_with_the_quantity():
    resolution = _resolve("as 2 baguettes que pedi")
    assert resolution.outcome == "resolved" and resolution.reason == "named_option"
    assert resolution.refs == ("BAGUETTE",) and resolution.text == "2 Baguette de Tradition"
    assert resolution.memo["pending"] is None


def test_naming_nothing_distinctive_does_not_guess():
    assert _resolve("quero pão").reason != "named_option"


def test_esta_without_accent_is_the_verb_not_a_pointer():
    assert dialogue.pronoun_reference(dialogue.words("ainda está aí")) == ""
    assert dialogue.pronoun_reference(dialogue.words("essa tem recheio")) == "singular"


# ── A conversa do ensaio, de ponta a ponta ──────────────────────────────

from shopman.storefront.tests.test_concierge_engine import (  # noqa: E402
    CONCIERGE_SETTINGS,
    _listed,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import _act  # noqa: E402
from shopman.storefront.tests.test_concierge_sacola import _cart, _turn  # noqa: E402


@pytest.fixture
def baguettes(surface, settings, monkeypatch):
    from shopman.storefront.concierge import intents

    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    _listed("BAGUETTE", "Baguette de Tradition", description="Baguette de fermentação natural", stock="20")
    _listed("JAMBON", "Jambon-Beurre", description="Baguette com presunto e manteiga", stock="20")


@pytest.mark.django_db
def test_the_owner_rehearsal_keeps_the_choice_alive(conversation, outbox, baguettes):
    asked = _turn(conversation, "pode ser 2 baguettes entao", [_act("order", "pode ser 2 baguettes entao", "baguettes", 2)])
    assert asked.startswith("Qual deles?"), asked

    still = _turn(conversation, "ainda está aí?", [])
    assert still.startswith("Estou aqui, sim! Qual deles?"), still
    assert "De qual produto" not in still

    done = _turn(conversation, "as 2 baguettes que pedi", [_act("order", "2 Baguette de Tradition", "baguette de tradition", 2)])
    assert _cart(conversation) == {"BAGUETTE": 2}, done
    assert "Pedido " not in done  # nada de pedido antigo
