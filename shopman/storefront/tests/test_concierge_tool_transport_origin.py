"""Origem causal do transporte permanece separada do canal comercial."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from shopman.shop.models import Conversation, ConversationBinding
from shopman.storefront.concierge import agent, service, tools

pytestmark = pytest.mark.django_db


class ScriptedClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs):
        return self.responses.pop(0)


def response(*content, stop_reason):
    return SimpleNamespace(
        content=list(content),
        stop_reason=stop_reason,
        stop_details=None,
        usage=SimpleNamespace(
            input_tokens=0,
            output_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


@pytest.fixture
def causal_conversation():
    conversation = Conversation.objects.create(channel_ref="web")
    binding = ConversationBinding.objects.create(
        conversation=conversation,
        provider="future-provider",
        account="tiktok-business",
        transport_channel="tiktok",
        subject="opaque-subject",
        connection_key="tiktok-primary",
        status=ConversationBinding.Status.ACTIVE,
    )
    conversation._binding = binding
    return conversation


def test_agent_loads_causal_binding_into_tool_context(causal_conversation, monkeypatch, settings):
    settings.SHOPMAN_CONCIERGE = {"model": "test-model", "adaptive_thinking": False}
    captured = []
    monkeypatch.setattr(service, "assert_turn_authority", lambda conversation, **kwargs: conversation)
    monkeypatch.setattr(
        "shopman.storefront.concierge.prompt.build_system",
        lambda *args, **kwargs: [{"type": "text", "text": "system"}],
    )

    def execute(name, arguments, context):
        captured.append(context)
        return {"ok": True, "message": "Cardápio consultado."}

    monkeypatch.setattr(tools, "execute", execute)
    client = ScriptedClient(
        response(
            SimpleNamespace(type="tool_use", id="tool-1", name="search_storefront", input={}),
            stop_reason="tool_use",
        ),
        response(SimpleNamespace(type="text", text="Pronto."), stop_reason="end_turn"),
    )
    agent.run_agent(conversation=causal_conversation, history=[], client=client)
    context = captured[0]
    assert context.channel_ref == "web"
    assert (
        context.provider,
        context.account,
        context.transport_channel,
        context.connection_key,
    ) == ("future-provider", "tiktok-business", "tiktok", "tiktok-primary")


def test_new_commercial_session_records_transport_channel_as_origin(causal_conversation, monkeypatch):
    from shopman.shop.services import cart, sessions

    captured = {}
    session = SimpleNamespace(session_key="session-1")

    def get_or_create_session(**kwargs):
        captured.update(kwargs)
        return session, session.session_key

    monkeypatch.setattr(cart, "get_or_create_session", get_or_create_session)
    monkeypatch.setattr(sessions, "modify_session", lambda **kwargs: session)
    context = tools.ToolContext(
        conversation=causal_conversation,
        channel_ref="web",
        provider="future-provider",
        account="tiktok-business",
        transport_channel="tiktok",
        connection_key="tiktok-primary",
    )
    assert tools._ensure_session(context) is session
    assert captured == {
        "session_key": None,
        "channel_ref": "web",
        "origin_channel": "tiktok",
    }
    causal_conversation.refresh_from_db()
    assert causal_conversation.channel_ref == "web"
    assert causal_conversation.session_key == "session-1"


def test_access_link_uses_agnostic_source_and_causal_metadata(causal_conversation, monkeypatch, settings):
    from shopman.doorman.models import AccessLink
    from shopman.doorman.services.access_link import AccessLinkService

    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://store.test"
    causal_conversation.customer_ref = "customer-1"
    causal_conversation.save(update_fields=["customer_ref"])
    captured = {}
    monkeypatch.setattr(
        service,
        "assert_turn_authority",
        lambda conversation, **kwargs: conversation,
    )
    monkeypatch.setattr(
        tools,
        "_auth_customer_info",
        lambda context: SimpleNamespace(uuid=uuid4()),
    )

    def create_token(cls, customer, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            success=True,
            url="https://store.test/auth/access/token",
            expires_at="soon",
        )

    monkeypatch.setattr(AccessLinkService, "create_token", classmethod(create_token))
    context = tools.ToolContext(
        conversation=causal_conversation,
        channel_ref="web",
        provider="future-provider",
        account="tiktok-business",
        transport_channel="tiktok",
        connection_key="tiktok-primary",
    )
    result = tools.send_web_link(context, "menu")
    assert result["ok"]
    assert captured["source"] == AccessLink.Source.API
    assert captured["metadata"] == {
        "next": "/menu",
        "conversation_id": causal_conversation.pk,
        "transport": {
            "provider": "future-provider",
            "account": "tiktok-business",
            "transport_channel": "tiktok",
            "connection_key": "tiktok-primary",
        },
    }
