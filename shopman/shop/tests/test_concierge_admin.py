"""Admin do concierge de WhatsApp: lista, transcrição e o único verbo (devolver)."""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import site as admin_site
from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from django.urls import reverse

from shopman.shop.admin.concierge import ConversationAdmin, message_summary
from shopman.shop.models import Conversation, ConversationMessage, Shop


@pytest.fixture
def admin_client(db):
    # Sem Shop o OnboardingMiddleware redireciona todo o Admin para criar a loja.
    Shop.objects.create(name="Test Shop", brand_name="Test", short_name="TS", primary_color="#C5A55A", default_ddd="43")
    User.objects.create_superuser("admin", "admin@test.com", "pass")
    client = Client()
    client.login(username="admin", password="pass")
    return client


@pytest.fixture
def conversation(db):
    conv = Conversation.objects.create(
        subscriber_id="sub-123",
        phone="+5543999990000",
        customer_name="Ana Souza",
        customer_ref="cust-ana",
    )
    ConversationMessage.objects.create(
        conversation=conv,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="Quero dois croissants <b>agora</b>",
        content=[{"type": "text", "text": "Quero dois croissants <b>agora</b>"}],
        external_id="m1",
    )
    ConversationMessage.objects.create(
        conversation=conv,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.TOOL_CALL,
        content=[{"type": "tool_use", "id": "t1", "name": "set_item", "input": {"sku": "CROISSANT", "qty": 2}}],
    )
    ConversationMessage.objects.create(
        conversation=conv,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.TOOL_RESULT,
        content=[{"type": "tool_result", "tool_use_id": "t1", "content": "x" * 400}],
    )
    ConversationMessage.objects.create(
        conversation=conv,
        role=ConversationMessage.Role.ASSISTANT,
        kind=ConversationMessage.Kind.REPLY,
        text="Dois croissants na sacola. Retira hoje ou amanhã?",
        content=[{"type": "text", "text": "Dois croissants na sacola. Retira hoje ou amanhã?"}],
        delivered=True,
    )
    return conv


def test_changelist_renders(admin_client, conversation):
    response = admin_client.get(reverse("admin:shop_conversation_changelist"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Ana Souza" in html
    assert "+5543999990000" in html


def test_change_page_renders_transcript(admin_client, conversation):
    response = admin_client.get(reverse("admin:shop_conversation_change", args=[conversation.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Quero dois croissants" in html
    assert "Dois croissants na sacola" in html
    # Texto do cliente nunca vira HTML: escapado, não marcado seguro.
    assert "<b>agora</b>" not in html
    assert "&lt;b&gt;agora&lt;/b&gt;" in html
    # Chamada de ferramenta resumida em uma linha: nome + input.
    assert "set_item(" in html
    assert "&quot;sku&quot;" in html or '"sku"' in html


def test_message_summary_clips_tool_result(conversation):
    result = conversation.messages.get(kind=ConversationMessage.Kind.TOOL_RESULT)
    summary = message_summary(result)
    assert len(summary) <= 200
    call = conversation.messages.get(kind=ConversationMessage.Kind.TOOL_CALL)
    assert message_summary(call) == 'set_item({"sku":"CROISSANT","qty":2})'


def test_return_to_concierge_action_flips_handoff(admin_client, conversation, monkeypatch):
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        "shopman.shop.concierge.transport.set_handoff",
        lambda subscriber_id, on: calls.append((subscriber_id, on)) or True,
    )
    conversation.state = Conversation.State.HANDOFF
    conversation.handoff_reason = "pediu uma pessoa"
    conversation.save()
    active = Conversation.objects.create(subscriber_id="sub-456", phone="+5543999990001")

    response = admin_client.post(
        reverse("admin:shop_conversation_changelist"),
        {"action": "return_to_concierge_selected", "_selected_action": [conversation.pk, active.pk]},
        follow=True,
    )
    assert response.status_code == 200
    conversation.refresh_from_db()
    assert conversation.state == Conversation.State.ACTIVE
    assert conversation.handoff_reason == ""
    assert calls == [("sub-123", False)]
    assert conversation.messages.filter(kind=ConversationMessage.Kind.NOTE, text="Voltou para o concierge.").exists()
    html = response.content.decode()
    assert "1 conversa(s) devolvida(s)" in html
    assert "1 conversa(s) ignorada(s)" in html


def test_admin_is_read_only(db):
    model_admin = ConversationAdmin(Conversation, admin_site)
    request = RequestFactory().get("/")
    request.user = User.objects.create_superuser("root", "root@test.com", "pass")
    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_delete_permission(request) is False
    assert model_admin.has_change_permission(request) is False
    assert model_admin.has_view_permission(request) is True


def test_conversation_message_has_no_own_admin():
    assert ConversationMessage not in admin_site._registry
