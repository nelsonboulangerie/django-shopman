"""Porta de canal: normalizar entrada, enviar, consultar entrega, pedir transferência.

Garantias (v2 5.4): entrega pelo menos uma vez sem duplicar efeito; janela do
canal respeitada; identidade nunca promovida sem prova; aceite do transporte
não é aceite de pessoa. "Desconhecido" ao enviar não se reenvia às cegas (K17).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from conversational_commerce.contracts import ChannelBinding, ExposureEvent, InteractionEvent
from conversational_commerce.contracts.common import CONTRACT_DATACLASS, Hash, Identifier, Instant, Text, Value

from .common import Capabilities, TrustedContext

OPERATIONS = ("normalize", "send", "delivery_status", "request_handoff")


@dataclass(**CONTRACT_DATACLASS)
class PreparedMessage(Value):
    """A mensagem pronta para sair: o que foi decidido, o hash do conteúdo e para quem."""

    decision_id: Identifier
    content_hash: Hash
    recipient: Identifier
    binding: ChannelBinding
    body_ref: Text


@dataclass(**CONTRACT_DATACLASS)
class HandoffRequest(Value):
    binding: ChannelBinding
    reason: Identifier
    requested_at: Instant


@runtime_checkable
class ChannelPort(Protocol):
    def capabilities(self) -> Capabilities: ...

    def normalize(self, ctx: TrustedContext, raw: Mapping[str, Any], received_at: str) -> InteractionEvent: ...

    def send(self, ctx: TrustedContext, prepared: PreparedMessage, idempotency_key: str) -> ExposureEvent: ...

    def delivery_status(self, ctx: TrustedContext, exposure_id: str) -> ExposureEvent: ...

    def request_handoff(self, ctx: TrustedContext, request: HandoffRequest) -> None: ...
