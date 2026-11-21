# ruff: noqa: F401, F811
"""Casar só por palavra genérica não é achar (ensaio do dono no WhatsApp, 21/11/2026).

"quero 2 pão de ensaio A" (o produto tinha saído do cardápio do canal) respondeu "Qual deles?
1) Baguette de Tradition; 2) Croque Monsieur; 3) Croque Madame": casou só pelo "pão" da
descrição. O certo é dizer que não achou e mostrar o que há hoje.
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


@pytest.fixture
def bakery(surface, settings, monkeypatch):
    from shopman.storefront.concierge import intents

    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    _listed("TRADI", "Baguette de Tradition", description="Pão de fermentação natural", stock="20")
    _listed("CQMO", "Croque Monsieur", description="Pão de forma, presunto e queijo", stock="20")
    _listed("CQMA", "Croque Madame", description="Pão de forma, presunto, queijo e ovo", stock="20")


def test_matching_only_a_generic_word_says_not_found_and_shows_the_menu(conversation, outbox, bakery):
    reply = _turn(conversation, "quero 2 pão de ensaio A", [_act("order", "quero 2 pão de ensaio A", "pão de ensaio A", 2)])

    assert reply.startswith("Não encontrei “pão de ensaio A” no cardápio de hoje. O que temos agora:"), reply
    assert "Qual deles?" not in reply
    assert _cart(conversation) == {}


def test_asking_about_it_also_says_not_found(conversation, outbox, bakery):
    reply = _turn(conversation, "tem pão de ensaio?", [_act("product_question", "tem pão de ensaio?", "pão de ensaio")])
    assert reply.startswith("Não encontrei “pão de ensaio” no cardápio de hoje."), reply


def test_a_distinctive_word_still_finds_and_asks_which(conversation, outbox, bakery):
    reply = _turn(conversation, "quero 2 croque", [_act("order", "quero 2 croque", "croque", 2)])
    assert reply.startswith("Qual deles?") and "Croque Monsieur" in reply and "Baguette" not in reply, reply


def test_a_generic_word_alone_is_still_a_search(conversation, outbox, bakery):
    reply = _turn(conversation, "tem pão?", [_act("product_question", "tem pão?", "pão")])
    assert "Não encontrei" not in reply, reply
