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


#: O ``getInfo`` real do contato do WhatsApp do dono (24/11/2026): a hora é a do Messenger, velha, e a do WhatsApp
#: vem vazia. A mensagem chegou ao ManyChat e se perdeu no deploy das 20h10Z.
LOST = "Boa tarde\nTudo bem?\nAinda tem pão champagne e folhado de maçã?"
WHATSAPP_INFO = {"last_input_text": LOST, "last_interaction": "2024-06-11T08:12:12-03:00",
                 "whatsapp_interaction": None, "last_seen": "2024-06-15T10:00:00-03:00",
                 "whatsapp_phone": "+5543999990000"}


def _ours(conversation, text, minutes_ago):  # noqa: F811
    from shopman.storefront.tests.test_concierge_engine import _create_inbound

    _create_inbound(conversation, text, f"nossa-{minutes_ago}")
    binding = _binding(conversation)
    ConversationBinding.objects.filter(pk=binding.pk).update(
        last_inbound_at=timezone.now() - timedelta(minutes=minutes_ago))


def test_whatsapp_lost_message_is_reingested_although_the_provider_time_is_stale(conversation, manychat):
    """24/11: a mensagem do dono chegou ao ManyChat e não ao webhook; o ``last_interaction`` de 2024 fazia a
    varredura pulá-la como velha. A fala do ManyChat que difere da nossa última, com a nossa na janela, volta."""
    _ours(conversation, "obrigado", minutes_ago=40)
    manychat["info"] = dict(WHATSAPP_INFO)

    first = inbound_sweep.sweep()
    again = inbound_sweep.sweep()

    assert first["reingested"] == 1
    assert again["reingested"] == 0, "idempotente: a nossa última agora é ela"
    message = _inbound(conversation, LOST).get()
    assert message.envelope.get("correlation_ref") == "inbound_sweep"
    assert message.envelope.get("occurred_at_assurance") == "lower_bound"  # a hora é o piso, não inventada


def test_whatsapp_same_text_as_our_last_is_not_reingested(conversation, manychat):
    _ours(conversation, LOST, minutes_ago=5)
    manychat["info"] = dict(WHATSAPP_INFO)

    assert inbound_sweep.sweep()["reingested"] == 0
    assert _inbound(conversation, LOST).count() == 1


def test_whatsapp_with_our_last_outside_the_window_is_not_reingested(conversation, manychat):
    _ours(conversation, "obrigado", minutes_ago=25 * 60)
    manychat["info"] = dict(WHATSAPP_INFO)

    assert inbound_sweep.sweep()["reingested"] == 0


def test_whatsapp_time_when_the_provider_gives_it_is_used(conversation, manychat):
    _ours(conversation, "obrigado", minutes_ago=40)
    manychat["info"] = {**WHATSAPP_INFO, "whatsapp_interaction": (timezone.now() - timedelta(minutes=2)).isoformat()}

    assert inbound_sweep.sweep()["reingested"] == 1
    assert _inbound(conversation, LOST).get().envelope.get("occurred_at_assurance") == "provider_api"
