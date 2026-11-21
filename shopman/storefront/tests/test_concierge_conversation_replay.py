# ruff: noqa: F401, F811
"""Replay do placar de conversa: as falas reais no código de hoje, sem enviar e sem gravar."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.utils import timezone

from shopman.shop.models import Conversation
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import conversation_eval, transport
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    _binding,
    conversation,
    customer,
    outbox,
    surface,
)
from shopman.storefront.tests.test_concierge_sacola import menu

pytestmark = pytest.mark.django_db


@pytest.fixture
def history(conversation, menu):
    """A conversa como ficou no banco: a fala do cliente e uma resposta antiga, seca."""
    from shopman.storefront.tests.test_concierge_engine import _create_inbound

    inbound = _create_inbound(conversation, "quero 2 croissant", "hist-1")
    Message.objects.filter(pk=inbound.pk).update(consumed_by=1)
    Message.objects.create(conversation=conversation, binding=_binding(conversation), role="assistant",
                           kind="reply", text="Croissant: Indisponível.", transport_state="accepted")
    Conversation.objects.filter(pk=conversation.pk).update(last_inbound_at=timezone.now())
    return conversation


def test_replay_runs_todays_code_and_leaves_nothing_behind(history, outbox, monkeypatch, settings):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS

    def must_not_send(*args, **kwargs):
        raise AssertionError("o replay não envia nada")

    monkeypatch.setattr(transport, "handoff_for", must_not_send)
    before = Message.objects.count()
    flags_before = Conversation.objects.get(pk=history.pk).flags

    turns, info = conversation_eval.replay_turns(days=1)

    assert info["turns"] == 1 and info["skipped"] == 0
    [turn] = turns
    assert turn.customer == "quero 2 croissant"
    assert turn.reply and turn.reply != "Croissant: Indisponível."  # a resposta é a do código de hoje
    assert Message.objects.count() == before  # nada ficou gravado
    assert Conversation.objects.get(pk=history.pk).flags == flags_before
    assert outbox.sent == []  # nada foi enviado


def test_replay_command_says_nothing_was_sent(history, capsys, settings):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS

    call_command("concierge_conversation_eval", "--days", "1", "--replay")

    out = capsys.readouterr().out
    assert "Replay no código de hoje (sem IA paga): 1 turnos de 1 conversas" in out
    assert "Nada foi enviado nem gravado." in out


@pytest.mark.parametrize(("reply", "empty"), [
    ("Pedido NB-1: Preparando…. Total: .", True),
    ("Total: .", True),
    ("Pedido NB-1, de 17/11: Preparando… Total: R$ 24,00.", False),
])
def test_an_announced_value_that_is_missing_is_unbacked(reply, empty):
    assert conversation_eval.empty_value(reply) is empty
