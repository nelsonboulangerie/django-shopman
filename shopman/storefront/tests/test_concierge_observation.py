"""Captura passiva: aprende casos sem atender, enfileirar ou copiar dados."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory
from django.urls import reverse
from shopman.orderman.models import Directive

from shopman.shop.management.commands.maintenance_worker import MAINTENANCE_COMMANDS
from shopman.shop.models import Conversation, ConversationBinding, ConversationMessage
from shopman.storefront.admin.concierge import ConversationAdmin
from shopman.storefront.concierge import agent, service, transport, webhook

pytestmark = pytest.mark.django_db

KEY = "observation-test-key"
CONNECTION_KEY = "manychat-whatsapp-primary"
SUBJECT = "4605528796186498"
NOW = datetime(2026, 9, 14, 15, tzinfo=UTC)
CONFIG = {
    "contract_version": 3,
    "operation_mode": "observe",
    # Observação não depende do modelo nem do switch de atendimento.
    "enabled": False,
    "channel_ref": "whatsapp",
    "connections": {
        CONNECTION_KEY: {
            "active": True,
            "provider": "manychat",
            "account": "mc-account",
            "channel": "whatsapp",
            "adapter_path": "shopman.storefront.concierge.transport.ManyChatWhatsAppAdapter",
            "options": {
                "authentication": {"scheme": "api_key", "keys": [KEY]},
                "allowed_subjects": [SUBJECT],
                "stable_event_identity_verified": False,
                "observation": {
                    "enabled": True,
                    "privacy_approved": True,
                    "notice_version": "privacy-2026-09",
                    "retention_days": 7,
                    "allow_all_subjects": False,
                    "allowed_subjects": [SUBJECT],
                },
            },
        }
    },
}


@pytest.fixture(autouse=True)
def configured(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = deepcopy(CONFIG)
    settings.AI_ASSIST_API_KEY = ""
    monkeypatch.setattr(webhook.timezone, "now", lambda: NOW)
    cache.clear()
    yield
    cache.clear()


def _post(*, subject=SUBJECT, text="Vocês entregam pain perdu?", **extra):
    body = {
        "subscriber_id": subject,
        "text": text,
        "first_name": "Pablo",
        "provider_timestamp": "2026-09-14 11:59:00",
        **extra,
    }
    return Client().post(
        reverse("concierge:connection-events", args=[CONNECTION_KEY]),
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_API_KEY=KEY,
        HTTP_X_CONCIERGE_MODE="observe",
    )


def test_observe_persists_canonical_transcript_without_queue_model_or_output(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("efeito externo")

    monkeypatch.setattr(agent, "build_client", forbidden)
    monkeypatch.setattr(service, "_enqueue_turn", forbidden)
    monkeypatch.setattr(transport, "send_for", forbidden)
    monkeypatch.setattr(transport, "handoff_for", forbidden)

    response = _post(author_type="team", processing_mode="assist")

    assert response.status_code == 200
    assert response.json() == {"status": "observed", "queued": False}
    message = ConversationMessage.objects.get()
    assert message.kind == ConversationMessage.Kind.INBOUND
    assert message.automation_eligible is False
    assert message.consumed_by is None
    assert message.retention_until == NOW + timedelta(days=7)
    assert message.envelope["processing_mode"] == "observe"
    assert message.envelope["author_type"] == "customer"
    assert "profile" not in message.envelope
    assert "subject" not in message.envelope
    assert "event_id" not in message.envelope
    assert "correlation_ref" not in message.envelope
    assert message.envelope["observation_policy"] == {
        "notice_version": "privacy-2026-09",
        "retention_days": 7,
    }
    assert not Directive.objects.exists()
    binding = message.binding
    binding.refresh_from_db()
    message.conversation.refresh_from_db()
    assert binding.last_inbound_at is None
    assert message.conversation.last_inbound_at is None


def test_observation_redacts_identifiers_and_sensitive_details_before_insert():
    raw = (
        "Meu e-mail pablo@example.com, CPF 123.456.789-09, telefone +55 43 99999-0000, "
        "cartão 4111 1111 1111 1111, Rua das Flores, 123. "
        "Tenho diabetes e alergia a amendoim. Meu filho de 7 anos. "
        "Veja https://example.com/?token=top-secret-123"
    )

    assert _post(text=raw).json()["status"] == "observed"

    message = ConversationMessage.objects.get()
    assert message.content == []
    for secret in (
        "pablo@example.com",
        "123.456.789-09",
        "+55 43 99999-0000",
        "4111 1111 1111 1111",
        "Rua das Flores",
        "diabetes",
        "amendoim",
        "7 anos",
        "example.com",
        "top-secret-123",
    ):
        assert secret not in message.text
    assert set(message.envelope["redactions"]) == {
        "url",
        "email",
        "cpf",
        "financial",
        "numeric_identifier",
        "address",
        "health",
        "minor",
        "secret",
    }
    assert not {
        "profile",
        "subject",
        "event_id",
        "correlation_ref",
        "payload_hash",
        "received_at",
        "occurred_at",
    } & message.envelope.keys()


def test_database_rejects_automation_ineligible_message_without_retention():
    conversation = Conversation.objects.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        ConversationMessage.objects.create(
            conversation=conversation,
            role=ConversationMessage.Role.USER,
            kind=ConversationMessage.Kind.NOTE,
            automation_eligible=False,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("enabled", False),
        ("privacy_approved", False),
        ("notice_version", ""),
        ("retention_days", 0),
        ("retention_days", 31),
        ("retention_days", "invalid"),
    ],
)
def test_each_observation_gate_fails_closed(settings, field, value):
    policy = settings.SHOPMAN_CONCIERGE["connections"][CONNECTION_KEY]["options"][
        "observation"
    ]
    policy[field] = value

    response = _post()

    assert response.json() == {"status": "observation_disabled", "queued": False}
    assert not Conversation.objects.exists()


def test_empty_observation_cohort_never_means_everyone(settings):
    policy = settings.SHOPMAN_CONCIERGE["connections"][CONNECTION_KEY]["options"][
        "observation"
    ]
    policy["allowed_subjects"] = []

    assert _post().json()["status"] == "observation_disabled"
    assert not Conversation.objects.exists()


def test_explicit_all_subjects_is_separate_gate(settings):
    policy = settings.SHOPMAN_CONCIERGE["connections"][CONNECTION_KEY]["options"][
        "observation"
    ]
    policy["allowed_subjects"] = []
    policy["allow_all_subjects"] = True

    assert _post(subject="another-contact").json()["status"] == "observed"


def test_observed_history_never_becomes_a_future_turn(settings):
    assert _post().json()["status"] == "observed"
    settings.SHOPMAN_CONCIERGE["enabled"] = True
    settings.AI_ASSIST_API_KEY = "fixture"
    binding = ConversationBinding.objects.select_related("conversation").get()

    assert service.is_allowed(binding)
    assert service.unanswered_inbound(binding.conversation, binding) == []
    assert agent.history_for(binding.conversation) == []
    assert service.recover_pending() == {"queued": 0, "unknown": 0}
    assert not Directive.objects.exists()


def _admin_request(*, curator: bool):
    user = User.objects.create_user(f"viewer-{curator}", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_conversation"))
    if curator:
        user.user_permissions.add(
            Permission.objects.get(codename="review_conversation_observations")
        )
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def test_curator_sees_observation_in_existing_admin_without_parallel_inbox():
    assert _post().json()["status"] == "observed"
    model_admin = ConversationAdmin(Conversation, admin.site)
    conversation = model_admin.get_queryset(_admin_request(curator=True)).get()

    assert model_admin.usage_badge(conversation) == "Observação"
    transcript = str(model_admin.transcript_display(conversation))
    assert "Observação" in transcript
    assert "descarte 21/09/2026" in transcript


def test_regular_viewer_cannot_see_observation_only_conversation():
    assert _post().json()["status"] == "observed"
    model_admin = ConversationAdmin(Conversation, admin.site)

    assert not model_admin.get_queryset(_admin_request(curator=False)).exists()


def test_regular_viewer_keeps_empty_operational_conversation_visible():
    conversation = Conversation.objects.create(customer_name="Sem mensagens")
    model_admin = ConversationAdmin(Conversation, admin.site)

    visible = model_admin.get_queryset(_admin_request(curator=False)).get(
        pk=conversation.pk
    )

    assert model_admin.usage_badge(visible) == "Atendimento"
    assert "Sem mensagens ainda" in str(model_admin.transcript_display(visible))


def test_regular_viewer_sees_only_operational_rows_in_mixed_conversation():
    assert _post(text="segredo observado").json()["status"] == "observed"
    binding = ConversationBinding.objects.select_related("conversation").get()
    ConversationMessage.objects.create(
        conversation=binding.conversation,
        binding=binding,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="mensagem operacional",
        automation_eligible=True,
    )
    model_admin = ConversationAdmin(Conversation, admin.site)
    conversation = model_admin.get_queryset(_admin_request(curator=False)).get()

    transcript = str(model_admin.transcript_display(conversation))
    assert model_admin.usage_badge(conversation) == "Atendimento"
    assert "mensagem operacional" in transcript
    assert "segredo observado" not in transcript


def test_unverified_retries_preserve_at_least_once_evidence():
    assert _post(event_id="candidate-only").json()["status"] == "observed"
    assert _post(event_id="candidate-only").json()["status"] == "observed"

    messages = ConversationMessage.objects.order_by("pk")
    assert messages.count() == 2
    assert all(message.external_id == "" for message in messages)
    assert all(message.envelope["input_assurance"] == "at_least_once" for message in messages)


def test_verified_event_dedupes_only_after_provider_gate(settings):
    options = settings.SHOPMAN_CONCIERGE["connections"][CONNECTION_KEY]["options"]
    options["stable_event_identity_verified"] = True

    assert _post(event_id="official-message-id").json()["status"] == "observed"
    assert _post(event_id="official-message-id").json()["status"] == "duplicate"
    assert ConversationMessage.objects.count() == 1


def test_invalid_header_is_rejected_and_body_cannot_select_observation(monkeypatch):
    seen = []
    monkeypatch.setattr(
        service,
        "receive_inbound",
        lambda event: seen.append(event) or service.IntakeResult(None, None, False, "not_allowed"),
    )
    url = reverse("concierge:connection-events", args=[CONNECTION_KEY])
    body = json.dumps(
        {
            "subscriber_id": SUBJECT,
            "text": "oi",
            "processing_mode": "observe",
        }
    )
    client = Client()

    invalid = client.post(
        url,
        data=body,
        content_type="application/json",
        HTTP_X_API_KEY=KEY,
        HTTP_X_CONCIERGE_MODE="unknown",
    )
    assist = client.post(
        url,
        data=body,
        content_type="application/json",
        HTTP_X_API_KEY=KEY,
    )

    assert invalid.status_code == 400
    assert invalid.json()["code"] == "invalid_processing_mode"
    assert assist.json()["status"] == "disabled"
    assert assist.json()["reason"] == "observation_only"
    assert seen == []


def test_observation_mode_blocks_legacy_assist_even_when_ai_is_enabled(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE["enabled"] = True
    settings.AI_ASSIST_API_KEY = "configured-but-forbidden"

    def forbidden(*args, **kwargs):
        raise AssertionError("atendimento executado durante observação")

    monkeypatch.setattr(service, "receive_inbound", forbidden)
    monkeypatch.setattr(service, "_enqueue_turn", forbidden)
    monkeypatch.setattr(transport, "send_for", forbidden)
    response = Client().post(
        reverse("concierge:connection-events", args=[CONNECTION_KEY]),
        data=json.dumps({"subscriber_id": SUBJECT, "text": "oi"}),
        content_type="application/json",
        HTTP_X_API_KEY=KEY,
    )

    assert response.json() == {"status": "disabled", "reason": "observation_only"}
    assert not Conversation.objects.exists()
    assert not Directive.objects.exists()


def test_observation_mode_cancels_prepared_handoff_ack_without_send_or_operator_alert(
    monkeypatch,
):
    conversation = Conversation.objects.create(state=Conversation.State.HANDOFF)
    binding = ConversationBinding.objects.create(
        conversation=conversation,
        connection_key=CONNECTION_KEY,
        provider="manychat",
        account="mc-account",
        transport_channel="whatsapp",
        subject=SUBJECT,
        status=ConversationBinding.Status.ACTIVE,
    )
    reply = service._prepare_reply(
        conversation,
        binding,
        "ACK que não pode sair",
        purpose="handoff_ack",
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("efeito no operador ou fornecedor")

    monkeypatch.setattr(transport, "send_for", forbidden)
    monkeypatch.setattr(service, "_alert", forbidden)

    result = service._dispatch_reply(conversation, reply)

    result.refresh_from_db()
    assert result.transport_state == "not_applied"
    assert result.envelope["code"] == "observation_mode_cancelled"
    assert result.outbound_attempts.get().code == "observation_mode_cancelled"


def test_output_cancelled_by_observation_cannot_be_retried_later(settings, monkeypatch):
    conversation = Conversation.objects.create()
    binding = ConversationBinding.objects.create(
        conversation=conversation,
        connection_key=CONNECTION_KEY,
        provider="manychat",
        account="mc-account",
        transport_channel="whatsapp",
        subject=SUBJECT,
        status=ConversationBinding.Status.ACTIVE,
    )
    inbound = ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="entrada antiga",
        envelope={"version": 3},
    )
    conversation._inbound_max_id = inbound.pk
    reply = service._prepare_reply(conversation, binding, "resposta antiga")
    monkeypatch.setattr(service, "_alert", lambda *args, **kwargs: None)
    service._dispatch_reply(conversation, reply)
    settings.SHOPMAN_CONCIERGE.update(
        operation_mode="assist",
        enabled=True,
        output_retry_enabled=True,
    )
    settings.AI_ASSIST_API_KEY = "fixture"

    monkeypatch.setattr(
        transport,
        "send_for",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("replay indevido")),
    )
    assert service.retry_not_applied(conversation.pk, reply.pk) is False


def test_observed_verified_event_cannot_be_replayed_as_assist(settings):
    options = settings.SHOPMAN_CONCIERGE["connections"][CONNECTION_KEY]["options"]
    options["stable_event_identity_verified"] = True
    body = {
        "subscriber_id": SUBJECT,
        "text": "não responder",
        "event_id": "official-message-id",
        "provider_timestamp": "2026-09-14 11:59:00",
    }
    assert _post(**body).json()["status"] == "observed"
    settings.SHOPMAN_CONCIERGE["operation_mode"] = "assist"
    settings.SHOPMAN_CONCIERGE["enabled"] = True
    settings.AI_ASSIST_API_KEY = "fixture"

    response = Client().post(
        reverse("concierge:connection-events", args=[CONNECTION_KEY]),
        data=json.dumps(body),
        content_type="application/json",
        HTTP_X_API_KEY=KEY,
    )

    assert response.status_code == 409
    assert response.json() == {"status": "intent_conflict", "queued": False}
    assert ConversationMessage.objects.count() == 1
    assert not Directive.objects.exists()


def test_retention_cleanup_removes_empty_transport_identity():
    assert _post().json()["status"] == "observed"
    message = ConversationMessage.objects.get()

    result = service.purge_observations(now=message.retention_until)

    assert result == {"messages": 1, "bindings": 1, "conversations": 1}
    assert not ConversationMessage.objects.exists()
    assert not ConversationBinding.objects.exists()
    assert not Conversation.objects.exists()


def test_periodic_cleanup_never_deletes_eligible_legacy_transcript():
    conversation = Conversation.objects.create(customer_name="Legado")
    binding = ConversationBinding.objects.create(
        conversation=conversation,
        provider="manychat",
        account="account-1",
        transport_channel="whatsapp",
        subject="legacy-subject",
        connection_key=CONNECTION_KEY,
    )
    message = ConversationMessage.objects.create(
        conversation=conversation,
        binding=binding,
        role=ConversationMessage.Role.USER,
        kind=ConversationMessage.Kind.INBOUND,
        text="mensagem anterior ao modo de observação",
        # Mesmo um envelope historicamente parecido não pode superar a
        # elegibilidade persistente que a migration atribui ao legado.
        envelope={"processing_mode": "observe"},
    )

    result = service.purge_observations(now=NOW + timedelta(days=31))

    assert result == {"messages": 0, "bindings": 0, "conversations": 0}
    assert ConversationMessage.objects.filter(pk=message.pk).exists()
    assert ConversationBinding.objects.filter(pk=binding.pk).exists()
    assert Conversation.objects.filter(pk=conversation.pk).exists()


def test_subject_cleanup_is_available_before_retention(capsys):
    assert _post().json()["status"] == "observed"

    call_command(
        "cleanup_concierge_observations",
        connection_key=CONNECTION_KEY,
        subject=SUBJECT,
    )

    assert json.loads(capsys.readouterr().out) == {
        "bindings": 1,
        "conversations": 1,
        "messages": 1,
    }
    assert not Conversation.objects.exists()


def test_retention_cleanup_is_part_of_the_periodic_worker():
    assert "cleanup_concierge_observations" in MAINTENANCE_COMMANDS
