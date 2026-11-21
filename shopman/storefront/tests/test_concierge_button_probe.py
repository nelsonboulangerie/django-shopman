"""Ensaio do botão "Confirmar pedido" no WhatsApp (#2926): o envio e o registro do clique."""

from __future__ import annotations

import json

import pytest
from django.urls import reverse

from shopman.shop.models import ConversationBinding, ConversationMessage
from shopman.storefront.concierge import button_probe
from shopman.storefront.tests import test_concierge_engine as engine

surface = engine.surface
customer = engine.customer
conversation = engine.conversation
pytestmark = pytest.mark.django_db


def _manychat(conversation):  # noqa: F811
    ConversationBinding.objects.filter(conversation=conversation).update(provider="manychat")
    return ConversationBinding.objects.get(conversation=conversation).subject


def test_the_test_message_carries_the_callback_button_with_the_code(monkeypatch):
    from shopman.shop.adapters import notification_manychat as mc

    sent = {}
    monkeypatch.setattr(mc, "_prepare_call", lambda subscriber, what: ({"api_token": "t"}, int(subscriber)))
    monkeypatch.setattr(mc, "_api_call", lambda endpoint, payload, config: sent.update(payload) or {"success": True})

    result = button_probe.send(
        "123", callback_url="https://api.exemplo.com/api/webhooks/concierge/button-probe/", check_window=False
    )

    message = sent["data"]["content"]["messages"][0]
    assert sent["data"]["content"]["type"] == "whatsapp"
    [btn] = message["buttons"]
    assert btn["type"] == "dynamic_block_callback" and btn["caption"] == "Confirmar pedido"
    assert btn["payload"]["code"] == result["code"] and result["code"] in message["text"]
    assert btn["headers"][button_probe.HEADER].startswith(result["probe"] + ".")
    assert "—" not in message["text"]


def test_an_authenticated_click_is_recorded_on_the_conversation_and_answered(client, conversation):  # noqa: F811
    subject = _manychat(conversation)
    btn = button_probe.button("abc123", "4821", "https://x/")
    body = {"subscriber_id": subject, "payload": btn["payload"]}

    response = client.post(
        reverse("concierge:button-probe"), data=json.dumps(body), content_type="application/json",
        headers={button_probe.HEADER: btn["headers"][button_probe.HEADER]},
    )

    assert response.status_code == 200
    assert response.json()["content"]["messages"][0]["text"] == button_probe.REPLY_TEXT
    note = ConversationMessage.objects.get(conversation=conversation, envelope__has_key="button_probe")
    entry = note.envelope["button_probe"]
    assert entry["authenticated"] and entry["subject"] == subject
    assert entry["payload"] == {"probe": "abc123", "code": "4821", "kind": "confirm_order_probe"}
    assert button_probe.recorded()[0]["payload"]["code"] == "4821"


def test_a_click_without_the_header_is_refused_but_recorded(client, conversation):  # noqa: F811
    subject = _manychat(conversation)

    response = client.post(
        reverse("concierge:button-probe"), data=json.dumps({"subscriber_id": subject, "payload": {}}),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert button_probe.recorded()[0]["authenticated"] is False


def test_outside_the_24h_window_the_probe_is_not_sent(monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    from shopman.shop.adapters import notification_manychat as mc

    old = (timezone.now() - timedelta(hours=30)).isoformat()
    monkeypatch.setattr(button_probe, "_subscriber_info", lambda subscriber: {"last_interaction": old})
    monkeypatch.setattr(mc, "_api_call", lambda *a, **k: pytest.fail("fora da janela não chama o ManyChat"))

    result = button_probe.send("123", callback_url="https://api.exemplo.com/x/")

    assert result == {"success": False, "error": "outside_window", "last_interaction": old}
    assert "fora da janela" in button_probe.explain(result)


def test_a_refusal_is_explained_with_the_provider_code():
    line = button_probe.explain(
        {"success": False, "error": "provider_rejected", "provider_http_status": 400, "provider_code": "2817", "probe": "abc"}
    )

    assert line == "Recusado pelo ManyChat: provider_rejected, HTTP 400, código 2817, ensaio abc."
    assert "—" not in line
