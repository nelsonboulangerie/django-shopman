# ruff: noqa: F401, F811
"""N9b: o turno vivo passa pelo motor do framework só com a chave ligada (#3299).

Com as chaves desligadas, o turno é o de hoje, e o motor nem é montado. Com a classe "informar"
ligada, o agradecimento sai pelo motor, na frase de hoje e pelo mesmo envio, uma vez só. O que o
motor não sabe dizer com frase da Nice continua no caminho de hoje.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from shopman.shop.models import ConversationMessage, Shop
from shopman.storefront.concierge import service, turn_framework
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _binding,
    _receive,
    alpha_menu,
    conversation,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db


def _inform_on():
    shop = Shop.load()
    shop.conversational_live_inform = True
    shop.save()


def _replies(conversation):
    return list(ConversationMessage.objects.filter(conversation=conversation, kind="reply").order_by("pk"))


def test_with_the_switches_off_the_turn_is_today_and_the_engine_is_not_built(conversation, outbox, monkeypatch):
    monkeypatch.setattr(turn_framework, "build_engine", lambda *a, **k: pytest.fail("o motor não deveria ser montado"))
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "obrigada!", "troca-off-1")
        result = service.run_turn(conversation.pk, _binding(conversation).pk)
    assert result.fallback == "" and len(outbox.sent) == 1
    assert all("send_key" not in (reply.envelope or {}) for reply in _replies(conversation))


def test_a_thank_you_goes_through_the_engine_once_in_today_phrase(conversation, outbox):
    _inform_on()
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "obrigada!", "troca-on-1")
        result = service.run_turn(conversation.pk, _binding(conversation).pk)
    thanks = service.copy_message("CONCIERGE_SMALL_TALK_THANKS").strip()
    assert outbox.sent == [thanks]  # uma vez só: o motor enviou, o caminho de hoje não repete
    assert result.replies == [thanks] and result.processed_message_ids
    (reply,) = _replies(conversation)
    assert reply.envelope["send_key"].startswith("send:")  # saiu pelo motor
    # O turno se fecha como hoje: a entrada consumida, sob o mesmo fence.
    assert all(m.consumed_by is not None for m in ConversationMessage.objects.filter(pk__in=result.processed_message_ids))


def test_what_the_engine_cannot_say_in_the_nice_voice_stays_on_today_path(conversation, outbox):
    _inform_on()
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "qual o horário de vocês?", "troca-on-2")
        result = service.run_turn(conversation.pk, _binding(conversation).pk)
    assert result.fallback == "" and len(outbox.sent) == 1
    assert all("send_key" not in (reply.envelope or {}) for reply in _replies(conversation))  # o caminho de hoje


def test_an_interrupted_turn_sends_nothing_through_the_engine(conversation, outbox):
    _inform_on()
    with override_settings(SHOPMAN_CONCIERGE=CONCIERGE_SETTINGS):
        _receive(conversation, "obrigada!", "troca-on-3")
        message = ConversationMessage.objects.filter(conversation=conversation, kind="inbound").latest("pk")
        assert turn_framework.run(conversation, message, interrupted=lambda: True) is None
    assert outbox.sent == []  # a conversa mudou de dono: o motor não envia, e o caminho de hoje decide
