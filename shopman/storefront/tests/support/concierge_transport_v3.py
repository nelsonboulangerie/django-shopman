"""Infraestrutura hermética compartilhada pelos testes do transporte v3."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from shopman.storefront.concierge.contracts import (
    ChannelCapabilities,
    HandoffOutcome,
    InboundEvent,
    ResponseAuthorization,
    SendOutcome,
    TransportScope,
    WindowEvidence,
)


class CanonicalTestAdapter:
    """Adapter configurável sem rede, telefone ou credencial externa."""

    sent: list[tuple[str, str, str]] = []
    handoffs: list[tuple[str, str, bool]] = []
    identified: list[tuple[str, str]] = []
    send_outcomes: dict[str, list[object]] = {}
    handoff_outcomes: dict[tuple[str, bool], object] = {}

    def __init__(self, *, connection):
        self.connection = connection
        self.provider = connection.provider
        self.channel = connection.channel
        self.capabilities = ChannelCapabilities(
            max_text_chars=int(connection.options.get("max_text_chars") or 4000),
            response_window=timedelta(hours=24),
            stable_event_identity_verified=connection.options.get("stable_event_identity_verified") is True,
            supports_handoff=connection.options.get("supports_handoff", True) is True,
            delivery_receipts=True,
        )

    def send_text(self, subject, text):
        self.sent.append((self.connection.key, subject, text))
        outcomes = self.send_outcomes.setdefault(self.connection.key, [])
        outcome = outcomes.pop(0) if outcomes else SendOutcome("accepted", "accepted")
        if callable(outcome):
            outcome = outcome(subject, text)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def set_handoff(self, subject, on):
        self.handoffs.append((self.connection.key, subject, on))
        outcome = self.handoff_outcomes.get(
            (self.connection.key, on),
            HandoffOutcome("accepted", "accepted", f"handoff:{self.connection.key}:{on}"),
        )
        return outcome(subject, on) if callable(outcome) else outcome

    def identify(self, subject, profile):
        self.identified.append((self.connection.key, subject))
        return None

    def window_evidence(self, envelope, now):
        return None

    def authorize_response(self, evidence, now, *, purpose):
        evidence = WindowEvidence.from_value(evidence)
        allowed = bool(evidence and evidence.valid_until > now)
        return ResponseAuthorization(
            allowed,
            "test_window" if allowed else "window_closed",
            evidence.valid_until if evidence else None,
        )


ADAPTER_PATH = "shopman.storefront.tests.support.concierge_transport_v3.CanonicalTestAdapter"


def adapter_class():
    return CanonicalTestAdapter


def reset_adapter():
    CanonicalTestAdapter.sent = []
    CanonicalTestAdapter.handoffs = []
    CanonicalTestAdapter.identified = []
    CanonicalTestAdapter.send_outcomes = {}
    CanonicalTestAdapter.handoff_outcomes = {}
    return CanonicalTestAdapter


def connection(*, provider, account, channel, subjects, verified=True, **options):
    return {
        "active": True,
        "provider": provider,
        "account": account,
        "channel": channel,
        "adapter_path": ADAPTER_PATH,
        "options": {
            "allowed_subjects": subjects,
            "stable_event_identity_verified": verified,
            **options,
        },
    }


def event(
    *,
    key="manychat-wa",
    provider="manychat",
    account="manychat-account",
    channel="whatsapp",
    subject="wa-subject",
    text="Olá",
    event_id="event-1",
    assurance="verified",
    message_type="text",
):
    now = timezone.now()
    return InboundEvent(
        scope=TransportScope(
            provider=provider,
            account=account,
            channel=channel,
            subject=subject,
            connection_key=key,
        ),
        text=text,
        message_type=message_type,
        received_at=now,
        event_id=event_id,
        event_identity_assurance=assurance,
        authentication_assurance="test",
        payload_hash=f"hash:{event_id}:{text}",
        window_evidence=WindowEvidence(
            policy="test-window-v1",
            source="authenticated-test-event",
            observed_at=now,
            valid_until=now + timedelta(hours=24),
            assurance="provider_window",
        ),
    )
