# ruff: noqa: F401, F811
"""Achados do ensaio do dono (21/11/2026, sábado antes de abrir).

- "o que teria disponível?" com nada à venda: saía "não tenho essa informação" (e uma
  verificação à equipe). É a pergunta do cardápio, e a resposta diz que não há nada para hoje
  e que dá para encomendar.
- duas partes sobre o mesmo produto (uma lida como pergunta, outra como pedido) repetiam
  "Sobre “bagel”, não tenho essa informação aqui." na mesma resposta.
"""

from __future__ import annotations

import pytest

from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_sacola import _turn, conversation, customer, menu, outbox, surface

pytestmark = pytest.mark.django_db


def test_what_is_available_with_nothing_for_sale_says_so(conversation, outbox, menu):
    from shopman.offerman.models import ListingItem

    ListingItem.objects.update(is_sellable=False)

    reply = _turn(conversation, "o que teria disponivel?", [_act("product_question", "o que teria disponivel?")])

    assert reply.startswith("Neste momento não há produtos disponíveis para hoje."), reply
    assert "não tenho essa informação" not in reply


def test_what_is_available_lists_the_menu(conversation, outbox, menu):
    reply = _turn(conversation, "o que teria disponivel?", [_act("product_question", "o que teria disponivel?")])

    assert "disponíveis" in reply and "Croissant" in reply, reply


def test_the_same_not_found_sentence_goes_once(conversation, outbox, menu):
    text = "tem bagel? vocês fazem bagel?"

    reply = _turn(conversation, text, [_act("product_question", "tem bagel?", "bagel"), _act("order", "vocês fazem bagel?", "bagel")])

    assert reply.count("Sobre “bagel”, não tenho essa informação aqui.") == 1, reply
