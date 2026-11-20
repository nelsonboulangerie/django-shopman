"""A Concierge sem modelo não diz "diga de outro jeito" (dono, 19/11/2026, "opção 1").

Três garantias, sem rede:

1. **Sem modelo e a leitura local não entendeu:** a casa pergunta à equipe (o "vou
   verificar" do WP-05, com o cartão e o prazo), em vez de "não entendi, diga de outro
   jeito".
2. **Pergunta simples segue direta:** cardápio, horário e pedido não mudam.
3. **"Não entendi" no máximo uma vez por conversa:** com modelo, a segunda vez que a
   casa não entende vai para a equipe.
"""

from __future__ import annotations

import pytest

from shopman.shop.models import Conversation
from shopman.storefront.concierge import intents, service, verification
from shopman.storefront.tests.test_concierge_engine import (  # noqa: F401 (fixtures)
    CONCIERGE_SETTINGS,
    _binding,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_intents import _act
from shopman.storefront.tests.test_concierge_verification import _cards, _receive, _record, _turn

pytestmark = pytest.mark.django_db

UNCLEAR = "e aquele esquema lá do outro dia, como ficou?"


@pytest.fixture(autouse=True)
def settings_after_conversation(request, monkeypatch):
    monkeypatch.setattr(intents, "_model", lambda: "modelo-de-teste")
    request.getfixturevalue("conversation")
    request.getfixturevalue("settings").SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS


def test_without_a_model_what_the_house_did_not_understand_goes_to_the_team(conversation, outbox):  # noqa: F811
    # Sem leitor (o conftest tira a conexão): a divisão local não reconhece a fala.
    _receive(conversation, UNCLEAR, "sem-modelo-1")
    result = service.run_turn(conversation.pk, _binding(conversation).pk)

    assert not result.handoff and not result.fallback
    reply = outbox.sent[-1]
    assert "não entendi" not in reply.casefold() and "de outro jeito" not in reply
    assert "Já perguntei para a equipe" in reply
    record = _record(conversation)
    assert record and record["status"] == verification.OPEN
    assert _cards().count() == 1
    assert "esquema" in _cards().get().message


def test_a_simple_question_without_a_model_is_still_answered_directly(conversation, outbox):  # noqa: F811
    _receive(conversation, "tem pão francês?", "sem-modelo-2")
    service.run_turn(conversation.pk, _binding(conversation).pk)

    assert "Pão Francês" in outbox.sent[-1]
    assert _record(conversation) is None and not _cards().exists()


def test_not_understood_at_most_once_per_conversation_the_second_goes_to_the_team(conversation, outbox):  # noqa: F811
    first = _turn(conversation, UNCLEAR, [_act("unknown", UNCLEAR)], "nao-entendi-1")

    assert not first.handoff
    assert "não entendi" in outbox.sent[-1]
    conversation.refresh_from_db()
    assert conversation.flags.get(intents.UNCLEAR_FLAG) is True

    second = _turn(conversation, "e o negócio do bolo de ontem?", [_act("unknown", "e o negócio do bolo de ontem?")],
                   "nao-entendi-2")

    assert second.handoff
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.HANDOFF
    assert "não entendi" not in outbox.sent[-1]
