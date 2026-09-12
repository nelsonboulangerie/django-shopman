"""Regressões de fronteira C03/C04 identificadas durante revisão adversarial."""

import hashlib
from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationMessage
from shopman.storefront.concierge import agent, service, transport

pytestmark = pytest.mark.django_db


@pytest.fixture
def conversation(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 2,
        "account_id": "adversarial-account",
        "allowed_subscribers": ["123"],
        "channel_ref": "web",
    }
    settings.AI_ASSIST_API_KEY = "fake"
    monkeypatch.setattr(service, "_alert", lambda *args: None)
    result = service.receive_inbound(subscriber_id="123", text="Confirmei", external_id="event-1")
    return Conversation.objects.get(pk=result.conversation_id)


@pytest.mark.parametrize("first_state", ["not_applied", "unknown"])
def test_dependent_payment_block_waits_for_accepted_summary(conversation, monkeypatch, first_state):
    sent = []
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kw: agent.AgentOutcome(
            reply_text="Pedido registrado; pagamento pendente.", extra_replies=["PIX-COPYABLE-BLOCK"]
        ),
    )

    def send(subject, text):
        sent.append(text)
        return transport.SendOutcome(first_state if len(sent) == 1 else "accepted", "injected")

    monkeypatch.setattr(transport, "send_text", send)
    service.run_turn(conversation.pk)
    replies = list(conversation.messages.filter(kind=ConversationMessage.Kind.REPLY).order_by("pk"))
    assert replies[0].transport_state == first_state
    assert sent == ["Pedido registrado; pagamento pendente."]
    assert replies[1].transport_state == "not_applied"
    assert replies[1].envelope["code"] == "preceding_block_pending"


def test_expired_claim_recovers_unsent_block_without_discarding_it(conversation, monkeypatch):
    claimed, inbound = service._claim(conversation.pk)
    prepared = service._prepare_reply(claimed, "Pedido registrado; consulte este mesmo pedido.")
    ConversationMessage.objects.filter(pk__in=[m.pk for m in inbound]).update(consumed_by=claimed.turn_fence)
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=timezone.now() - timedelta(seconds=1))
    sent = []
    monkeypatch.setattr(
        transport, "send_text", lambda subject, text: sent.append(text) or transport.SendOutcome("accepted")
    )
    service.recover_pending()
    prepared.refresh_from_db()
    assert prepared.transport_state == "accepted"
    assert sent == [prepared.text]


def test_replay_of_rejected_intent_preserves_original_error(conversation):
    from shopman.shop.models import Channel
    from shopman.shop.services import remote_mutations
    from shopman.storefront.concierge import tools

    Channel.objects.create(ref="web", config={"payment": {"method": ["pix"]}})
    conversation.phone = "+5543999999999"
    conversation.save(update_fields=["phone"])
    original = tools._error("revision_conflict", "A sacola mudou. Confira novamente.")
    fingerprint = remote_mutations.mutation_fingerprint(
        {
            "customer_ref": "",
            "channel_ref": "web",
            "phone": conversation.phone,
            "revision": "quote-old",
            "payment_method": "pix",
            "notes": "",
        }
    )
    remote_mutations.run_idempotent_mutation(
        scope="concierge.purchase:" + hashlib.sha256(f"{conversation.pk}:web".encode()).hexdigest()[:40],
        key="quote-old",
        fingerprint=fingerprint,
        execute=lambda: (original, 409),
    )
    result = tools.place_order(tools.ToolContext(conversation, "web"), "quote-old", "pix")
    assert result == original


def test_scope_change_blocks_order_lookup_before_identity_filter(conversation, settings, monkeypatch):
    from unittest.mock import Mock

    from shopman.shop.services import customer_orders
    from shopman.storefront.concierge import tools

    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "account_id": "other-account"}
    lookup = Mock(return_value=None)
    monkeypatch.setattr(customer_orders, "customer_identity_filter", lookup)
    result = tools.order_status(tools.ToolContext(conversation, "web"))
    assert not result["ok"]
    lookup.assert_not_called()


def test_explicit_retry_preserves_block_order_and_never_retries_unknown(conversation, settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "output_retry_enabled": True}
    conversation, _ = service._claim(conversation.pk)
    first = service._prepare_reply(conversation, "Pedido registrado; pagamento pendente.")
    second = service._prepare_reply(conversation, "PIX-CODE", depends_on=first.pk)
    monkeypatch.setattr(transport, "send_text", lambda *args: transport.SendOutcome("not_applied", "provider_rejected"))
    service._dispatch_reply(conversation, first)
    service._dispatch_reply(conversation, second)
    sent = []
    monkeypatch.setattr(
        transport, "send_text", lambda subject, text: sent.append(text) or transport.SendOutcome("accepted")
    )
    assert not service.retry_not_applied(conversation.pk, second.pk)
    assert service.retry_not_applied(conversation.pk, first.pk)
    assert service.retry_not_applied(conversation.pk, second.pk)
    assert sent == [first.text, second.text]
    second.transport_state = "unknown"
    second.save(update_fields=["transport_state"])
    assert not service.retry_not_applied(conversation.pk, second.pk)
    assert sent == [first.text, second.text]


@pytest.fixture
def checkout_surface():
    from shopman.storefront.tests.test_concierge_engine import surface

    return surface.__wrapped__()


def test_identity_change_inside_commit_boundary_cannot_create_order(conversation, checkout_surface, monkeypatch):
    from shopman.orderman.models import Order

    from shopman.shop.models import Channel
    from shopman.shop.services import remote_mutations
    from shopman.storefront.concierge import tools
    from shopman.storefront.tests.test_concierge_engine import _accept_review, _pickup_ready

    channel = Channel.objects.get(ref="web")
    channel.config = {"payment": {"method": ["pix"]}, "stock": {"allow_untracked": False}}
    channel.save(update_fields=["config"])
    conversation.phone = "+5543999999999"
    conversation.save(update_fields=["phone"])
    ctx = tools.ToolContext(conversation, "web")
    quote = _pickup_ready(ctx)
    assert quote["ok"], quote
    _accept_review(ctx, quote)
    original = remote_mutations.run_idempotent_mutation
    raced = []

    def race(**kwargs):
        raced.append(True)
        Conversation.objects.filter(pk=conversation.pk).update(phone="+5543888888888")
        return original(**kwargs)

    monkeypatch.setattr(remote_mutations, "run_idempotent_mutation", race)
    result = tools.place_order(ctx, quote["quote_token"], "pix")
    assert raced == [True]
    assert not result["ok"]
    assert not Order.objects.exists()


def test_multiblock_review_is_offered_only_after_last_primary_block(conversation, monkeypatch):
    text = "\n".join("Linha factual " + str(i) + ": " + "a" * 750 for i in range(8))
    sent = []
    monkeypatch.setattr(agent, "run_agent", lambda **kw: agent.AgentOutcome(reply_text=text, quote_token="review-full"))
    monkeypatch.setattr(
        transport, "send_text", lambda subject, text: sent.append(text) or transport.SendOutcome("accepted")
    )
    service.run_turn(conversation.pk)
    replies = list(conversation.messages.filter(kind=ConversationMessage.Kind.REPLY).order_by("pk"))
    assert len(replies) > 1
    assert "".join(sent) == text
    assert all(message.transport_state == "accepted" for message in replies)
    assert [message.envelope.get("quote_token") for message in replies] == [""] * (len(replies) - 1) + ["review-full"]
    assert [message.envelope.get("depends_on") for message in replies] == [None] + [
        message.pk for message in replies[:-1]
    ]


@pytest.mark.parametrize("change", ["new_input", "new_quote"])
def test_explicit_retry_rejects_stale_context(conversation, settings, monkeypatch, change):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "output_retry_enabled": True}
    conversation, _ = service._claim(conversation.pk)
    conversation.quote = {"token": "offered"}
    conversation.save(update_fields=["quote"])
    message = service._prepare_reply(conversation, "Revisão antiga", quote_token="offered")
    message.transport_state = "not_applied"
    message.envelope = {**message.envelope, "code": "provider_rejected"}
    message.save(update_fields=["transport_state", "envelope"])
    if change == "new_input":
        service.receive_inbound(subscriber_id="123", text="Agora quero três", external_id="event-2")
    else:
        Conversation.objects.filter(pk=conversation.pk).update(quote={"token": "changed"})
    sent = []
    monkeypatch.setattr(transport, "send_text", lambda *args: sent.append(args) or transport.SendOutcome("accepted"))
    assert not service.retry_not_applied(conversation.pk, message.pk)
    assert sent == []
