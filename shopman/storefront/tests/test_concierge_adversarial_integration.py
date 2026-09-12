"""Regressões de fronteira C03/C04 identificadas durante revisão adversarial."""

import hashlib
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone

from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage, OutboundAttempt
from shopman.storefront.concierge import agent, service
from shopman.storefront.concierge.contracts import SendOutcome
from shopman.storefront.tests.support.concierge_transport_v3 import (
    adapter_class,
    connection,
    event,
    reset_adapter,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def conversation(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 3,
        "account_id": "adversarial-account",
        "channel_ref": "web",
        "output_retry_enabled": True,
        "connections": {
            "adversarial": connection(
                provider="synthetic",
                account="adversarial-account",
                channel="text",
                subjects=["123"],
            )
        },
    }
    settings.AI_ASSIST_API_KEY = "fake"
    reset_adapter()
    monkeypatch.setattr(service, "_alert", lambda *args, **kwargs: None)
    result = service.receive_inbound(
        event(
            key="adversarial",
            provider="synthetic",
            account="adversarial-account",
            channel="text",
            subject="123",
            text="Confirmei",
        )
    )
    return Conversation.objects.get(pk=result.conversation_id)


def binding_for(conversation):
    return ConversationBinding.objects.get(conversation=conversation)


def authorize_commercial(conversation):
    binding = binding_for(conversation)
    binding.identity_assurance = "verified_customer"
    binding.save(update_fields=["identity_assurance"])
    return binding


def new_event(text, event_id):
    return event(
        key="adversarial",
        provider="synthetic",
        account="adversarial-account",
        channel="text",
        subject="123",
        text=text,
        event_id=event_id,
    )


@pytest.mark.parametrize("first_state", ["not_applied", "unknown"])
def test_dependent_payment_block_waits_for_accepted_summary(conversation, monkeypatch, first_state):
    binding = binding_for(conversation)
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: agent.AgentOutcome(
            reply_text="Pedido registrado; pagamento pendente.",
            extra_replies=["PIX-COPYABLE-BLOCK"],
        ),
    )
    adapter_class().send_outcomes["adversarial"] = [SendOutcome(first_state, "injected")]
    service.run_turn(conversation.pk, binding.pk)
    replies = list(conversation.messages.filter(kind=ConversationMessage.Kind.REPLY).order_by("pk"))
    assert replies[0].transport_state == first_state
    assert [item[2] for item in adapter_class().sent] == ["Pedido registrado; pagamento pendente."]
    assert replies[1].transport_state == "not_applied"
    assert replies[1].envelope["code"] == "preceding_block_pending"
    assert list(replies[1].outbound_attempts.values_list("state", "code")) == [
        ("not_applied", "preceding_block_pending")
    ]


def test_expired_claim_recovers_unsent_block_without_discarding_it(conversation):
    binding = binding_for(conversation)
    claimed, _, inbound = service._claim(conversation.pk, binding.pk)
    evidence = inbound[-1].envelope["window_evidence"]
    prepared = service._prepare_reply(
        claimed,
        binding,
        "Pedido registrado; consulte este mesmo pedido.",
        window_evidence=evidence,
    )
    ConversationMessage.objects.filter(pk__in=[message.pk for message in inbound]).update(
        consumed_by=claimed.turn_fence
    )
    Conversation.objects.filter(pk=conversation.pk).update(claim_until=timezone.now() - timedelta(seconds=1))
    service.recover_pending()
    prepared.refresh_from_db()
    assert prepared.transport_state == "accepted"
    assert [item[2] for item in adapter_class().sent] == [prepared.text]


def test_replay_of_rejected_intent_preserves_original_error(conversation):
    from shopman.shop.models import Channel
    from shopman.shop.services import remote_mutations
    from shopman.storefront.concierge import tools

    Channel.objects.create(ref="web", config={"payment": {"method": ["pix"]}})
    conversation.phone = "+5543999999999"
    conversation.save(update_fields=["phone"])
    binding = authorize_commercial(conversation)
    claimed, _, _ = service._claim(conversation.pk, binding.pk)
    original = tools._error("revision_conflict", "A sacola mudou. Confira novamente.")
    fingerprint = remote_mutations.mutation_fingerprint(
        {
            "customer_ref": "",
            "channel_ref": "web",
            "phone": claimed.phone,
            "revision": "quote-old",
            "payment_method": "pix",
            "notes": "",
        }
    )
    remote_mutations.run_idempotent_mutation(
        scope="concierge.purchase:" + hashlib.sha256(f"{claimed.pk}:web".encode()).hexdigest()[:40],
        key="quote-old",
        fingerprint=fingerprint,
        execute=lambda: (original, 409),
    )
    result = tools.place_order(tools.ToolContext(claimed, "web"), "quote-old", "pix")
    assert result == original


def test_scope_change_blocks_order_lookup_before_identity_filter(conversation, settings, monkeypatch):
    from shopman.shop.services import customer_orders
    from shopman.storefront.concierge import tools

    binding = binding_for(conversation)
    claimed, _, _ = service._claim(conversation.pk, binding.pk)
    connection_config = settings.SHOPMAN_CONCIERGE["connections"]["adversarial"]
    settings.SHOPMAN_CONCIERGE["connections"]["adversarial"] = {
        **connection_config,
        "account": "other-account",
    }
    lookup = Mock(return_value=None)
    monkeypatch.setattr(customer_orders, "customer_identity_filter", lookup)
    result = tools.order_status(tools.ToolContext(claimed, "web"))
    assert not result["ok"] and result["error"] == "authority_unavailable"
    lookup.assert_not_called()


def test_explicit_retry_preserves_block_order_and_never_retries_unknown(conversation):
    binding = binding_for(conversation)
    claimed, _, inbound = service._claim(conversation.pk, binding.pk)
    evidence = inbound[-1].envelope["window_evidence"]
    first = service._prepare_reply(
        claimed,
        binding,
        "Pedido registrado; pagamento pendente.",
        window_evidence=evidence,
    )
    second = service._prepare_reply(
        claimed,
        binding,
        "PIX-CODE",
        depends_on=first.pk,
        window_evidence=evidence,
    )
    adapter_class().send_outcomes["adversarial"] = [SendOutcome("not_applied", "provider_rejected")]
    service._dispatch_reply(claimed, first)
    service._dispatch_reply(claimed, second)
    adapter_class().sent = []
    assert not service.retry_not_applied(conversation.pk, second.pk)
    assert service.retry_not_applied(conversation.pk, first.pk)
    assert service.retry_not_applied(conversation.pk, second.pk)
    assert [item[2] for item in adapter_class().sent] == [first.text, second.text]
    second.transport_state = "unknown"
    second.save(update_fields=["transport_state"])
    assert not service.retry_not_applied(conversation.pk, second.pk)
    assert [item[2] for item in adapter_class().sent] == [first.text, second.text]
    assert list(first.outbound_attempts.values_list("attempt_no", flat=True)) == [1, 2]


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
    binding = authorize_commercial(conversation)
    claimed, _, _ = service._claim(conversation.pk, binding.pk)
    ctx = tools.ToolContext(claimed, "web")
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
    binding = binding_for(conversation)
    text = "\n".join("Linha factual " + str(index) + ": " + "a" * 750 for index in range(8))
    monkeypatch.setattr(
        agent,
        "run_agent",
        lambda **kwargs: agent.AgentOutcome(reply_text=text, quote_token="review-full"),
    )
    service.run_turn(conversation.pk, binding.pk)
    replies = list(conversation.messages.filter(kind=ConversationMessage.Kind.REPLY).order_by("pk"))
    assert len(replies) > 1
    assert "".join(item[2] for item in adapter_class().sent) == text
    assert all(message.transport_state == "accepted" for message in replies)
    assert [message.envelope.get("quote_token") for message in replies] == [""] * (len(replies) - 1) + ["review-full"]
    assert [message.envelope.get("depends_on") for message in replies] == [None] + [
        message.pk for message in replies[:-1]
    ]


@pytest.mark.parametrize("change", ["new_input", "new_quote"])
def test_explicit_retry_rejects_stale_context(conversation, change):
    binding = binding_for(conversation)
    claimed, _, inbound = service._claim(conversation.pk, binding.pk)
    claimed.quote = {"token": "offered"}
    claimed.save(update_fields=["quote"])
    message = service._prepare_reply(
        claimed,
        binding,
        "Revisão antiga",
        quote_token="offered",
        window_evidence=inbound[-1].envelope["window_evidence"],
    )
    adapter_class().send_outcomes["adversarial"] = [SendOutcome("not_applied", "provider_rejected")]
    service._dispatch_reply(claimed, message)
    if change == "new_input":
        service.receive_inbound(new_event("Agora quero três", "event-2"))
    else:
        Conversation.objects.filter(pk=conversation.pk).update(quote={"token": "changed"})
    adapter_class().sent = []
    assert not service.retry_not_applied(conversation.pk, message.pk)
    assert adapter_class().sent == []
    assert OutboundAttempt.objects.filter(message=message).count() == 1
