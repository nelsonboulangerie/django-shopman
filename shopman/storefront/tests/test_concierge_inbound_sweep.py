# ruff: noqa: F401, F811
"""Reentrega do que o ManyChat recebeu e não chegou aqui (#2943).

Caso real (21/11/2026): o "oi" do dono chegou ao ManyChat às 02h54Z, o web-operator
reiniciou na mesma hora (sem deploy) e a mensagem não chegou ao banco. O External Request
do ManyChat não reenvia. A varredura pergunta ao ManyChat e reingere, uma vez só.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationBinding
from shopman.shop.models import ConversationMessage as Message
from shopman.storefront.concierge import inbound_sweep
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    PROVIDER,
    _binding,
    conversation,
    customer,
    outbox,
    surface,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def manychat(conversation, settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr(inbound_sweep, "PROVIDER", PROVIDER)
    seen = {}

    def info(subject):
        seen.setdefault("calls", []).append(subject)
        return seen.get("info")

    monkeypatch.setattr(inbound_sweep, "_subscriber_info", info)
    binding = _binding(conversation)
    ConversationBinding.objects.filter(pk=binding.pk).update(last_inbound_at=timezone.now() - timedelta(hours=30))
    return seen


def _inbound(conversation, text):  # noqa: F811
    return Message.objects.filter(conversation=conversation, kind="inbound", text=text)


def test_a_message_the_manychat_got_and_we_did_not_is_reingested_once(conversation, manychat):
    written = timezone.now() - timedelta(minutes=3)
    manychat["info"] = {"last_input_text": "oi, tem croissant?", "last_interaction": written.isoformat()}

    first = inbound_sweep.sweep()
    again = inbound_sweep.sweep()

    assert first["reingested"] == 1
    assert again["reingested"] == 0, "idempotente: não responde duas vezes"
    assert _inbound(conversation, "oi, tem croissant?").count() == 1
    message = _inbound(conversation, "oi, tem croissant?").get()
    assert message.envelope.get("correlation_ref") == "inbound_sweep"


def test_nothing_newer_than_ours_is_not_reingested(conversation, manychat):
    binding = _binding(conversation)
    ConversationBinding.objects.filter(pk=binding.pk).update(last_inbound_at=timezone.now())
    manychat["info"] = {"last_input_text": "oi", "last_interaction": (timezone.now() - timedelta(minutes=1)).isoformat()}

    assert inbound_sweep.sweep()["reingested"] == 0


def test_outside_the_24h_window_is_not_reingested(conversation, manychat):
    manychat["info"] = {"last_input_text": "oi", "last_interaction": (timezone.now() - timedelta(hours=25)).isoformat()}

    assert inbound_sweep.sweep()["reingested"] == 0


def test_a_conversation_with_the_team_is_not_swept(conversation, manychat):
    Conversation.objects.filter(pk=conversation.pk).update(state=Conversation.State.HANDOFF)
    manychat["info"] = {"last_input_text": "oi", "last_interaction": timezone.now().isoformat()}

    result = inbound_sweep.sweep()

    assert result["checked"] == 0 and not manychat.get("calls"), "vai ao Live Chat por desenho"


def test_the_same_text_already_here_is_not_reingested(conversation, manychat):
    from shopman.storefront.tests.test_concierge_engine import _create_inbound

    written = timezone.now() - timedelta(minutes=2)
    _create_inbound(conversation, "oi, tem croissant?", "ja-chegou")
    manychat["info"] = {"last_input_text": "oi, tem croissant?", "last_interaction": written.isoformat()}

    assert inbound_sweep.sweep()["reingested"] == 0
    assert _inbound(conversation, "oi, tem croissant?").count() == 1


def test_the_round_has_a_ceiling(conversation, manychat):
    assert len(inbound_sweep.candidates(limit=0)) == 0
    assert len(inbound_sweep.candidates(limit=5)) == 1
