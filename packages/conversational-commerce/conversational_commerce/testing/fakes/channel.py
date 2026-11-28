"""Canal falso: entrega duplicada e fora de ordem, "desconhecido" ao enviar, canal sem leitura."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from conversational_commerce.contracts import ExposureEvent, InteractionEvent, Producer
from conversational_commerce.ports import Capabilities, HandoffRequest, PortError, PreparedMessage, TrustedContext
from conversational_commerce.ports.channel import OPERATIONS

from .base import FakeBase
from .faults import Fault


class FakeChannel(FakeBase):
    PORT = "channel"

    def __init__(self, clock, faults=None, *, read_receipts: bool = True, name: str = "test-channel") -> None:
        super().__init__(clock, faults)
        self.read_receipts = read_receipts
        # O nome do canal casa com o canal do perfil de teste (``profile/test_profile.CHANNEL``).
        self.name = name
        self.outbox: dict[str, ExposureEvent] = {}
        self.handoffs: list[HandoffRequest] = []
        self._inbox: list[Mapping[str, Any]] = []

    def capabilities(self) -> Capabilities:
        return Capabilities(
            port="channel",
            operations=OPERATIONS,
            guarantees={"at_least_once": True, "event_identity": "provider_claimed",
                        "read_receipts": self.read_receipts, "delivery_receipts": True},
            unsupported=() if self.read_receipts else ("read_receipts",),
        )

    # Entrada: o canal entrega; o falso pode duplicar e trocar a ordem.
    def deliver(self, *raws: Mapping[str, Any]) -> None:
        self._inbox.extend(raws)

    def drain(self) -> list[Mapping[str, Any]]:
        fault = self._fault("drain")
        batch, self._inbox = list(self._inbox), []
        if fault is Fault.DUPLICATE_DELIVERY and batch:
            batch = [*batch, batch[0]]
        elif fault is Fault.OUT_OF_ORDER:
            batch.reverse()
        return batch

    def normalize(self, ctx: TrustedContext, raw: Mapping[str, Any], received_at: str) -> InteractionEvent:
        self._fault("normalize")
        provider_id = raw.get("id")
        return InteractionEvent(
            **self.envelope(ctx, "evt", occurred_at=raw.get("sent_at", received_at)),
            channel_binding={"channel": self.name, "conversation_ref": raw.get("conversation", "conv-1")},
            actor=raw.get("actor", "customer"),
            event_identity={"id": provider_id, "assurance": "provider_claimed"} if provider_id
            else {"assurance": "none"},
            type=raw.get("type", "message"),
            content_ref=raw.get("content_ref"),
            # Identidade nunca é promovida sem prova: o canal só transporta.
            identity_evidence=[{"kind": "channel_identity", "ref": raw["from"], "assurance": "transported"}]
            if raw.get("from") else [],
        )

    def send(self, ctx: TrustedContext, prepared: PreparedMessage, idempotency_key: str) -> ExposureEvent:
        if idempotency_key in self.outbox:
            return self.outbox[idempotency_key]  # pelo menos uma vez, sem duplicar
        fault = self._fault("send")
        if fault is Fault.PROVIDER_DOWN:
            raise PortError("provider_unavailable", "o canal não aceitou a conexão; nada foi enviado")
        state = "unknown" if fault is Fault.SEND_UNKNOWN else "accepted"
        exposure = ExposureEvent(
            **self.envelope(ctx, "exp"),
            decision_id=prepared.decision_id,
            content_hash=prepared.content_hash,
            realizer=Producer(name="fake-channel", version="1"),
            recipient=prepared.recipient,
            attempt=1,
            state=state,
        )
        self.outbox[idempotency_key] = exposure
        return exposure

    def mark(self, idempotency_key: str, state: str) -> ExposureEvent:
        """O teste diz o que o provedor viu depois (entregue, lida)."""
        import dataclasses

        if state == "read" and not self.read_receipts:
            raise ValueError("este canal não informa leitura")
        current = self.outbox[idempotency_key]
        updated = dataclasses.replace(current, id=self.clock.new_id("exp"), state=state,
                                      occurred_at=self.clock.now())
        self.outbox[idempotency_key] = updated
        return updated

    def delivery_status(self, ctx: TrustedContext, exposure_id: str) -> ExposureEvent:
        self._fault("delivery_status")
        for exposure in self.outbox.values():
            if exposure.id == exposure_id or exposure.decision_id == exposure_id:
                return exposure
        raise PortError("invalid_content", f"exposição desconhecida: {exposure_id}")

    def request_handoff(self, ctx: TrustedContext, request: HandoffRequest) -> None:
        self._fault("request_handoff")
        self.handoffs.append(request)
