"""``InteractionEvent``: algo que chegou de um canal, da equipe ou do sistema (observação).

Invariante (v2 5.5, N12): duplicata não cria comando; texto igual não prova
duplicata; evento fora de ordem não autoriza. A identidade do evento é o que
prova duplicata, e a garantia dela diz quanto se pode confiar nisso.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import (
    CONTRACT_DATACLASS,
    EventAssurance,
    Identifier,
    IdentityEvidence,
    ObservationRecord,
    Text,
    Value,
)
from .errors import invalid

InteractionType = Literal[
    "message",
    "tap",
    "correction",
    "staff_took_over",
    "staff_returned",
    "delivery_update",
    "deadline_due",
    "backend_event",
]


@dataclass(**CONTRACT_DATACLASS)
class ChannelBinding(Value):
    """O vínculo do canal: qual canal e qual conversa nele."""

    channel: Identifier
    conversation_ref: Identifier


@dataclass(**CONTRACT_DATACLASS)
class EventIdentity(Value):
    """Identidade estável do evento. Sem garantia (``none``), não há id e não se deduplica."""

    id: Identifier | None = None
    assurance: EventAssurance

    def check(self) -> None:
        if self.assurance == "none" and self.id is not None:
            raise invalid("evento sem garantia de identidade não carrega id", "id")
        if self.assurance != "none" and self.id is None:
            raise invalid("evento com garantia de identidade precisa de id", "id")


@dataclass(**CONTRACT_DATACLASS)
class InteractionEvent(ObservationRecord):
    SCHEMA = "cc.interaction_event"
    KIND = "InteractionEvent"

    channel_binding: ChannelBinding
    actor: Literal["customer", "staff", "system"]
    event_identity: EventIdentity
    type: InteractionType
    # Conteúdo pessoal vai por referência protegida, nunca no registro.
    content_ref: Text | None = None
    identity_evidence: tuple[IdentityEvidence, ...] = ()
