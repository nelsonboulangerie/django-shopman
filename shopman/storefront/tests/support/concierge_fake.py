"""Segundo transporte exclusivamente sintético: nenhum telefone, botão ou receipt."""

from datetime import timedelta

from shopman.storefront.concierge.contracts import (
    ChannelCapabilities,
    HandoffOutcome,
    ResponseAuthorization,
    SendOutcome,
    WindowEvidence,
)


class OpaqueAdapter:
    provider = "opaque-test"
    channel = "text-only-test"
    capabilities = ChannelCapabilities(max_text_chars=4000, response_window=timedelta(minutes=30))
    sent = []

    def __init__(self, *, connection):
        self.connection = connection
        self.provider = connection.provider
        self.channel = connection.channel

    def send_text(self, subject, text):
        self.sent.append((subject, text))
        return SendOutcome("accepted", "fake_acceptance")

    def set_handoff(self, subject, on):
        return HandoffOutcome("not_applied", "handoff_not_supported")

    def identify(self, subject, profile):
        return None

    def window_evidence(self, envelope, now):
        return WindowEvidence(
            policy="opaque-test-v1",
            source="opaque-event",
            observed_at=now,
            valid_until=now + self.capabilities.response_window,
            assurance="provider_window",
        )

    def authorize_response(self, evidence, now, *, purpose):
        evidence = WindowEvidence.from_value(evidence)
        allowed = bool(evidence and evidence.policy == "opaque-test-v1" and evidence.valid_until > now)
        return ResponseAuthorization(allowed, "opaque_window" if allowed else "window_closed")
