"""Continuidade entre transportes exige identidade verificada e ato explícito."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.guestman.models import Customer

from shopman.shop.models import Conversation, ConversationBinding
from shopman.storefront.concierge import service, transport
from shopman.storefront.concierge.contracts import (
    IdentityResolution,
    InboundEvent,
    TransportConnection,
    TransportScope,
)

pytestmark = pytest.mark.django_db


def _connection(provider, account, channel, subjects, *, identity_link_enabled=True):
    return {
        "active": True,
        "provider": provider,
        "account": account,
        "channel": channel,
        "adapter_path": "shopman.storefront.tests.support.concierge_fake.OpaqueAdapter",
        "options": {
            "allowed_subjects": subjects,
            "identity_link_enabled": identity_link_enabled,
        },
    }


@pytest.fixture
def identity_context(settings):
    customer = Customer.objects.create(
        ref="CUSTOMER-CONTINUITY",
        first_name="Cliente",
        last_name="Canônico",
        phone="+5543999990001",
    )
    settings.AI_ASSIST_API_KEY = "test-only"
    settings.SHOPMAN_CONCIERGE = {
        "enabled": True,
        "contract_version": 3,
        "connections": {
            "manychat-wa": _connection(
                "manychat",
                "manychat-account",
                "whatsapp",
                ["wa-subject"],
            ),
            "tiktok-dm": _connection(
                "tiktok",
                "tiktok-business",
                "direct_message",
                ["tiktok-subject"],
            ),
        },
    }
    conversation = Conversation.objects.create(
        customer_ref=customer.ref,
        customer_name=customer.name,
        phone=customer.phone,
    )
    ConversationBinding.objects.create(
        conversation=conversation,
        provider="manychat",
        account="manychat-account",
        transport_channel="whatsapp",
        subject="wa-subject",
        connection_key="manychat-wa",
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance=ConversationBinding.IdentityAssurance.VERIFIED_CUSTOMER,
        activated_at=timezone.now(),
    )
    scope = TransportScope(
        provider="tiktok",
        account="tiktok-business",
        channel="direct_message",
        subject="tiktok-subject",
        connection_key="tiktok-dm",
    )
    resolution = IdentityResolution(
        customer_uuid=customer.uuid,
        assurance="verified_customer",
        phone=customer.phone,
        name=customer.name,
    )
    return customer, conversation, scope, resolution


def test_identity_resolution_is_immutable(identity_context):
    _, _, _, resolution = identity_context

    with pytest.raises(FrozenInstanceError):
        resolution.assurance = "unverified"


def test_attach_binding_adds_verified_scope_to_existing_conversation(identity_context):
    _, conversation, scope, resolution = identity_context

    binding = service.attach_binding(conversation.pk, scope, resolution)
    repeated = service.attach_binding(conversation.pk, scope, resolution)

    assert repeated.pk == binding.pk
    assert binding.conversation_id == conversation.pk
    assert binding.connection_key == "tiktok-dm"
    assert binding.status == ConversationBinding.Status.ACTIVE
    assert binding.identity_assurance == ConversationBinding.IdentityAssurance.VERIFIED_CUSTOMER
    assert (
        ConversationBinding.objects.filter(
            provider="tiktok",
            account="tiktok-business",
            transport_channel="direct_message",
            subject="tiktok-subject",
        ).count()
        == 1
    )


@pytest.mark.parametrize(
    ("assurance", "gate", "code"),
    [
        ("unverified", True, "identity_unverified"),
        ("verified_customer", False, "identity_link_disabled"),
    ],
)
def test_attach_binding_rejects_unverified_resolution_or_closed_gate(
    identity_context,
    settings,
    assurance,
    gate,
    code,
):
    customer, conversation, scope, resolution = identity_context
    settings.SHOPMAN_CONCIERGE["connections"]["tiktok-dm"]["options"]["identity_link_enabled"] = gate
    resolution = IdentityResolution(
        customer_uuid=customer.uuid,
        assurance=assurance,
        phone=resolution.phone,
        name=resolution.name,
    )

    with pytest.raises(service.BindingAttachmentRejected, match=code) as rejected:
        service.attach_binding(conversation.pk, scope, resolution)

    assert rejected.value.code == code
    assert not ConversationBinding.objects.filter(subject="tiktok-subject").exists()


def test_attach_binding_rejects_identity_conflict_without_mutating_journeys(
    identity_context,
):
    _, conversation, scope, _ = identity_context
    another = Customer.objects.create(
        ref="CUSTOMER-OTHER",
        first_name="Outra",
        phone="+5543999990002",
    )
    conflicting = IdentityResolution(
        customer_uuid=another.uuid,
        assurance="verified_customer",
        phone=another.phone,
        name=another.name,
    )

    with pytest.raises(service.BindingAttachmentRejected, match="identity_conflict"):
        service.attach_binding(conversation.pk, scope, conflicting)

    conversation.refresh_from_db()
    assert conversation.customer_ref == "CUSTOMER-CONTINUITY"
    assert not ConversationBinding.objects.filter(subject="tiktok-subject").exists()


def test_attach_binding_never_moves_binding_from_another_conversation(identity_context):
    _, conversation, scope, resolution = identity_context
    separate = Conversation.objects.create()
    existing = ConversationBinding.objects.create(
        conversation=separate,
        provider=scope.provider,
        account=scope.account,
        transport_channel=scope.channel,
        subject=scope.subject,
        connection_key=scope.connection_key,
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance=ConversationBinding.IdentityAssurance.TRANSPORT_SUBJECT,
        activated_at=timezone.now(),
    )

    with pytest.raises(service.BindingAttachmentRejected, match="binding_already_attached"):
        service.attach_binding(conversation.pk, scope, resolution)

    existing.refresh_from_db()
    assert existing.conversation_id == separate.pk


def test_profile_claim_never_auto_merges_inbound_with_identified_conversation(identity_context):
    customer, identified, scope, _ = identity_context
    now = timezone.now()
    event = InboundEvent(
        scope=scope,
        text="Continuar meu pedido",
        message_type="text",
        received_at=now,
        event_id="tiktok-event-1",
        event_identity_assurance="verified",
        profile={
            "customer_ref": customer.ref,
            "phone": customer.phone,
            "first_name": customer.first_name,
        },
        authentication_assurance="test",
        payload_hash="payload-claiming-existing-customer",
    )

    result = service.receive_inbound(event)

    assert result.conversation_id != identified.pk
    created = Conversation.objects.get(pk=result.conversation_id)
    assert created.customer_ref == created.phone == ""


def test_identify_marks_new_binding_when_conversation_is_already_identified(
    identity_context,
    monkeypatch,
):
    _, conversation, scope, resolution = identity_context
    binding = ConversationBinding.objects.create(
        conversation=conversation,
        provider=scope.provider,
        account=scope.account,
        transport_channel=scope.channel,
        subject=scope.subject,
        connection_key=scope.connection_key,
        status=ConversationBinding.Status.ACTIVE,
        identity_assurance=ConversationBinding.IdentityAssurance.TRANSPORT_SUBJECT,
        activated_at=timezone.now(),
    )
    monkeypatch.setattr(transport, "identity_for", lambda *_args, **_kwargs: resolution)

    identified = service.identify(conversation, binding)

    binding.refresh_from_db()
    assert identified.customer_ref == conversation.customer_ref
    assert binding.identity_assurance == ConversationBinding.IdentityAssurance.VERIFIED_CUSTOMER


def test_manychat_adapter_translates_customer_resolver_to_typed_identity(
    identity_context,
    monkeypatch,
):
    customer, _, _, _ = identity_context
    from shopman.guestman.adapters.auth import CustomerResolver

    monkeypatch.setattr(
        CustomerResolver,
        "upsert_manychat_subscriber",
        lambda _self, payload: SimpleNamespace(
            uuid=customer.uuid,
            phone=customer.phone,
            name=customer.name,
        )
        if payload == {"id": "wa-subject"}
        else None,
    )
    adapter = transport.ManyChatWhatsAppAdapter(
        connection=TransportConnection(
            key="manychat-wa",
            provider="manychat",
            account="manychat-account",
            channel="whatsapp",
            adapter_path="shopman.storefront.concierge.transport.ManyChatWhatsAppAdapter",
        )
    )

    resolution = adapter.identify("wa-subject", {})

    assert resolution == IdentityResolution(
        customer_uuid=customer.uuid,
        assurance="verified_customer",
        phone=customer.phone,
        name=customer.name,
    )
