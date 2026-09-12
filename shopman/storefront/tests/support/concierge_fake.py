"""Segundo transporte exclusivamente sintético: nenhum telefone, botão ou receipt."""

from datetime import timedelta

from shopman.storefront.concierge.transport import ChannelCapabilities, SendOutcome


class OpaqueAdapter:
    provider = "opaque-test"
    channel = "text-only-test"
    capabilities = ChannelCapabilities(max_text_chars=4000, response_window=timedelta(minutes=30))
    sent = []

    def send_text(self, subject, text):
        self.sent.append((subject, text))
        return SendOutcome("accepted", "fake_acceptance")

    def set_handoff(self, subject, on):
        return False

    def identify(self, subject, profile):
        return None
