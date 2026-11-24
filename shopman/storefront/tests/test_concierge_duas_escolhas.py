# ruff: noqa: F401, F811
"""Duas escolhas no mesmo turno (#3597, decisão da coordenação, 24/11/2026).

"1 brioche e 1 campagne oval" (observação do ar, 23/11/2026) pede duas coisas, e cada uma tem
mais de um item no cardápio. A resposta mostrava só a última pergunta, e o brioche sumia. Agora
é uma mensagem só, uma pergunta por item, na ordem em que o cliente pediu. O cliente responde as
duas de uma vez ou uma por vez, e nada se perde.
"""

from __future__ import annotations

import pytest

from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _listed,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_sacola import _cart, _turn

pytestmark = pytest.mark.django_db

SAID = "1 brioche e 1 campagne oval"


@pytest.fixture
def menu(surface, settings, monkeypatch):
    from shopman.storefront.concierge import intents

    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    _listed("BRBB", "Brioche Burger Bun", stock="20")
    _listed("BRCH", "Brioche Chocolat", stock="20")
    _listed("CPR", "Campagne Redondo", stock="20")
    _listed("CPX", "Campagne Passas & Castanhas", stock="20")


def _ask(conversation):
    return _turn(conversation, SAID, [_act("order", SAID, SAID, 0)])


def test_both_choices_come_in_one_message_in_the_order_asked(conversation, outbox, menu):
    reply = _ask(conversation)

    assert "Para “brioche”: “Brioche Burger Bun” ou “Brioche Chocolat”?" in reply, reply
    assert "Para “campagne oval”: “Campagne Passas & Castanhas” ou “Campagne Redondo”?" in reply, reply
    assert reply.index("Para “brioche”") < reply.index("Para “campagne oval”"), reply
    print("ASK<<", reply, ">>")
    assert _cart(conversation) == {}


def test_answering_both_at_once_puts_both(conversation, outbox, menu):
    _ask(conversation)

    said = "o burger bun e o redondo"
    reply = _turn(conversation, said, [_act("order", "1 Brioche Burger Bun e 1 Campagne Redondo",
                                              "1 Brioche Burger Bun e 1 Campagne Redondo", 0)])

    assert _cart(conversation) == {"BRBB": 1, "CPR": 1}, reply
    assert "Para “" not in reply, reply


def test_answering_one_at_a_time_keeps_the_other_question(conversation, outbox, menu):
    _ask(conversation)

    first = _turn(conversation, "o burger bun", [_act("order", "1 Brioche Burger Bun", "Brioche Burger Bun", 1)])

    print("FIRST<<", first, ">>")
    assert _cart(conversation) == {"BRBB": 1}, first
    assert "Para “campagne oval”: “Campagne Passas & Castanhas” ou “Campagne Redondo”?" in first, first
    assert "Para “brioche”" not in first, first

    second = _turn(conversation, "o de passas", [_act("order", "1 Campagne Passas & Castanhas",
                                                       "Campagne Passas & Castanhas", 1)])

    assert _cart(conversation) == {"BRBB": 1, "CPX": 1}, second
    assert "Para “" not in second, second
