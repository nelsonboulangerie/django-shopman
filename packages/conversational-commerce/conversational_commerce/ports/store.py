"""Porta de armazenamento: gravar entrada uma vez, carregar, confirmar transição, reivindicar trabalho.

Garantias (v2 5.4, N13): comparar e gravar; estado, registros e trabalho
pendente gravados juntos; isolamento por inquilino. Quem consome aceita
repetição.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from conversational_commerce.contracts import ActionReceipt, Episode, InteractionEvent, Record
from conversational_commerce.contracts.common import (
    CONTRACT_DATACLASS,
    Identifier,
    Instant,
    JsonObject,
    PositiveInt,
    Value,
)

from .common import Capabilities, TrustedContext

OPERATIONS = ("record_event_once", "load_episode", "commit_transition", "claim_work", "append_receipt")


@dataclass(**CONTRACT_DATACLASS)
class WorkItem(Value):
    """Trabalho pendente da caixa de saída: gravado na mesma transação do estado."""

    work_id: Identifier
    kind: Identifier
    payload: JsonObject
    due_at: Instant


@dataclass(**CONTRACT_DATACLASS)
class Claim(Value):
    work: WorkItem
    lease_until: Instant
    attempt: PositiveInt


@dataclass(frozen=True, slots=True)
class Transition:
    """O episódio novo e a versão que quem decidiu viu. Registro dentro de valor: conferido aqui."""

    episode: Episode
    expected_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.episode, Episode):
            raise TypeError("Transition.episode precisa ser um Episode")
        if isinstance(self.expected_version, bool) or not isinstance(self.expected_version, int) \
                or self.expected_version < 0:
            raise TypeError("Transition.expected_version precisa ser inteiro não negativo")


@runtime_checkable
class StorePort(Protocol):
    def capabilities(self) -> Capabilities: ...

    def record_event_once(self, ctx: TrustedContext, event: InteractionEvent) -> tuple[InteractionEvent, bool]: ...

    def load_episode(self, ctx: TrustedContext, episode_id: str) -> Episode | None: ...

    def commit_transition(
        self,
        ctx: TrustedContext,
        transition: Transition,
        records: tuple[Record, ...],
        outbox: tuple[WorkItem, ...],
    ) -> Episode: ...

    def claim_work(self, ctx: TrustedContext, kind: str, lease_seconds: int) -> Claim | None: ...

    def append_receipt(self, ctx: TrustedContext, receipt: ActionReceipt) -> ActionReceipt: ...
