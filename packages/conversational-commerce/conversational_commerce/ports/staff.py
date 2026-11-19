"""Porta de equipe: perguntar, abrir compromisso, atribuir, aceitar, cumprir, devolver.

Garantias (v2 5.4): dono e prazo, ou o motivo da ausência; aceite nominal
separado do roteamento (fila que recebe não é pessoa que aceitou); resposta
humana entra como fato com autoria e validade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from conversational_commerce.contracts import Commitment, Known
from conversational_commerce.contracts.common import (
    CONTRACT_DATACLASS,
    Identifier,
    Instant,
    NonNegativeInt,
    Text,
    Value,
)

from .common import Capabilities, TrustedContext

OPERATIONS = (
    "ask",
    "open_or_update",
    "assign",
    "record_acceptance",
    "record_fulfillment",
    "return_conversation",
    "promote_answer",
)


@dataclass(**CONTRACT_DATACLASS)
class StaffQuestion(Value):
    episode_id: Identifier
    question: Text
    respond_by: Instant


@dataclass(**CONTRACT_DATACLASS)
class StaffTicket(Value):
    ticket_id: Identifier
    episode_id: Identifier
    state: Literal["routed", "accepted", "answered", "rejected"]
    # Quem aceitou, nominalmente; ``None`` enquanto só foi roteado.
    accepted_by: Identifier | None = None
    answer: Known | None = None


@dataclass(**CONTRACT_DATACLASS)
class ConversationReturn(Value):
    episode_id: Identifier
    new_epoch: NonNegativeInt
    returned_by: Identifier


@runtime_checkable
class StaffPort(Protocol):
    def capabilities(self) -> Capabilities: ...

    def ask(self, ctx: TrustedContext, question: StaffQuestion) -> StaffTicket: ...

    def open_or_update(self, ctx: TrustedContext, commitment: Commitment) -> Commitment: ...

    def assign(self, ctx: TrustedContext, commitment_id: str, owner: str) -> Commitment: ...

    def record_acceptance(self, ctx: TrustedContext, ticket_id: str) -> StaffTicket: ...

    def record_fulfillment(self, ctx: TrustedContext, commitment_id: str, evidence: str) -> Commitment: ...

    def return_conversation(self, ctx: TrustedContext, episode_id: str, new_epoch: int) -> ConversationReturn: ...

    def promote_answer(self, ctx: TrustedContext, ticket_id: str) -> Known: ...
