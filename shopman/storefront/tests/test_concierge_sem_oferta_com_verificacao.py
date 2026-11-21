# ruff: noqa: F401, F811
"""Com o "vou verificar" na resposta, nenhuma parte oferece "chamo alguém da equipe" (ensaio, 21/11/2026)."""

from __future__ import annotations

import pytest

from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_sacola import _turn, conversation, customer, menu, outbox, surface

pytestmark = pytest.mark.django_db


def test_a_verifying_answer_does_not_also_offer_the_team(conversation, outbox, menu):
    text = "tem bagel? e vocês fazem brigadeiro?"

    reply = _turn(conversation, text, [
        _act("product_question", "tem bagel?", "bagel"),
        _act("order", "vocês fazem brigadeiro?", "brigadeiro"),
    ])

    assert "perguntei para a equipe" in reply or "Juntei isso" in reply, reply
    assert "chamo alguém da equipe" not in reply, reply
