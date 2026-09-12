"""Registry canônico: binding explícito, policy no adapter e outcomes completos."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from shopman.storefront.concierge import transport
from shopman.storefront.concierge.contracts import (
    HandoffOutcome,
    SendOutcome,
)

WINDOW = {
    "policy": "manychat-wa-24h-v1",
    "source": "manychat_whatsapp_last_interaction",
    "field": "provider_timestamp",
    "timezone": "America/Sao_Paulo",
    "authentication": "api_key",
    "duration_seconds": 86400,
    "purposes": ["reply", "handoff_ack"],
}
CONFIG = {
    "connections": {
        "manychat-wa": {
            "active": True,
            "provider": "manychat",
            "account": "mc-account",
            "channel": "whatsapp",
            "adapter_path": "shopman.storefront.concierge.transport.ManyChatWhatsAppAdapter",
            "options": {"response_window": WINDOW, "handoff_field": "concierge_handoff"},
        },
        "opaque-primary": {
            "active": True,
            "provider": "opaque-test",
            "account": "opaque-account",
            "channel": "text-only-test",
            "adapter_path": "shopman.storefront.tests.support.concierge_fake.OpaqueAdapter",
        },
    }
}


def binding(key, provider, account, channel, subject="subject"):
    return SimpleNamespace(
        connection_key=key,
        provider=provider,
        account=account,
        transport_channel=channel,
        subject=subject,
    )


@pytest.fixture(autouse=True)
def registry(settings):
    settings.SHOPMAN_CONCIERGE = CONFIG


def test_two_connections_resolve_by_binding_without_provider_default():
    manychat = transport.adapter_for(binding("manychat-wa", "manychat", "mc-account", "whatsapp"))
    opaque = transport.adapter_for(
        binding("opaque-primary", "opaque-test", "opaque-account", "text-only-test")
    )
    assert isinstance(manychat, transport.ManyChatWhatsAppAdapter)
    assert opaque.connection.key == "opaque-primary"


def test_missing_key_or_scope_mismatch_fails_closed():
    assert transport.adapter_for(binding("", "manychat", "mc-account", "whatsapp")) is None
    assert transport.adapter_for(binding("manychat-wa", "manychat", "other", "whatsapp")) is None


def test_no_top_level_singleton_fallback(settings):
    settings.SHOPMAN_CONCIERGE = {
        "provider": "manychat",
        "account": "mc-account",
        "channel": "whatsapp",
        "adapter_path": "shopman.storefront.concierge.transport.ManyChatWhatsAppAdapter",
    }
    assert transport.configured_connections() == ()


def test_inactive_connection_is_not_resolved(settings):
    settings.SHOPMAN_CONCIERGE = {
        "connections": {"off": {**CONFIG["connections"]["opaque-primary"], "active": False}}
    }
    assert transport.adapter_for(binding("off", "opaque-test", "opaque-account", "text-only-test")) is None


def test_malformed_options_fail_closed_instead_of_crashing_registry(settings):
    settings.SHOPMAN_CONCIERGE = {
        "connections": {
            "broken": {
                **CONFIG["connections"]["opaque-primary"],
                "options": "allowed_subjects=subject",
            }
        }
    }
    assert transport.configured_connections() == ()


def test_duplicate_provider_account_channel_scope_fails_closed(settings):
    settings.SHOPMAN_CONCIERGE = {
        "connections": {
            "first": CONFIG["connections"]["opaque-primary"],
            "second": CONFIG["connections"]["opaque-primary"],
        }
    }
    assert transport.configured_connections() == ()


def test_global_manychat_gateway_rejects_two_accounts(settings):
    second = {
        **CONFIG["connections"]["manychat-wa"],
        "account": "another-account",
    }
    settings.SHOPMAN_CONCIERGE = {
        "connections": {
            "manychat-wa": CONFIG["connections"]["manychat-wa"],
            "manychat-other-account": second,
        }
    }
    assert (
        transport.adapter_for(
            binding("manychat-wa", "manychat", "mc-account", "whatsapp")
        )
        is None
    )
    assert (
        transport.adapter_for(
            binding(
                "manychat-other-account",
                "manychat",
                "another-account",
                "whatsapp",
            )
        )
        is None
    )


def test_manychat_window_is_normalized_and_revalidated_by_adapter():
    current = binding("manychat-wa", "manychat", "mc-account", "whatsapp")
    envelope = {
        "provider": "manychat",
        "account_id": "mc-account",
        "transport_channel": "whatsapp",
        "authentication": "api_key",
        "provider_timestamp": "2026-09-12 11:29:01.391392",
    }
    now = datetime(2026, 9, 12, 15, tzinfo=UTC)
    evidence = transport.window_evidence_for(current, envelope, now)
    assert evidence.observed_at.isoformat() == "2026-09-12T14:29:01.391392+00:00"
    decision = transport.response_authorization(current, evidence.as_dict(), now, purpose="reply")
    assert decision.allowed and decision.valid_until == evidence.valid_until
    assert not transport.response_authorization(
        current, evidence, evidence.valid_until, purpose="reply"
    ).allowed


def test_window_policy_rejects_wrong_scope_and_unapproved_purpose():
    current = binding("manychat-wa", "manychat", "mc-account", "whatsapp")
    now = datetime(2026, 9, 12, 15, tzinfo=UTC)
    wrong = {
        "provider": "manychat",
        "account_id": "other",
        "transport_channel": "whatsapp",
        "authentication": "api_key",
        "provider_timestamp": "2026-09-12 11:29:01.391392",
    }
    assert transport.window_evidence_for(current, wrong, now) is None
    adapter = transport.adapter_for(current)
    evidence = adapter.window_evidence({**wrong, "account_id": "mc-account"}, now)
    assert not transport.response_authorization(current, evidence, now, purpose="marketing").allowed


def test_send_preserves_provider_receipt(monkeypatch):
    from shopman.shop.adapters import notification_manychat

    monkeypatch.setattr(
        notification_manychat,
        "send_text_result",
        lambda *args: {"success": True, "message_id": "provider-message-1"},
    )
    outcome = transport.send_for(
        binding("manychat-wa", "manychat", "mc-account", "whatsapp", "123"), "Oi"
    )
    assert outcome == SendOutcome("accepted", "", "provider-message-1")


def test_handoff_is_structured_and_false_is_unknown(monkeypatch):
    from shopman.shop.adapters import notification_manychat

    current = binding("manychat-wa", "manychat", "mc-account", "whatsapp", "123")
    monkeypatch.setattr(notification_manychat, "set_custom_field", lambda *args: False)
    assert transport.handoff_for(current, True) == HandoffOutcome("unknown", "acceptance_unconfirmed")


def test_unsupported_handoff_is_definitive():
    current = binding("opaque-primary", "opaque-test", "opaque-account", "text-only-test")
    assert transport.handoff_for(current, True) == HandoffOutcome(
        "not_applied", "handoff_not_supported"
    )


def test_opaque_adapter_owns_its_window_policy():
    current = binding("opaque-primary", "opaque-test", "opaque-account", "text-only-test")
    now = datetime.now(UTC)
    evidence = transport.window_evidence_for(current, {}, now)
    assert transport.response_authorization(current, evidence, now + timedelta(minutes=1)).allowed
