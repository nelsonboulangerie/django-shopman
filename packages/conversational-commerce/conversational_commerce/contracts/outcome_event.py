"""``OutcomeEvent``: o resultado medido, de fonte independente (observação).

Invariantes (v2 5.5, N20, N21): fonte independente do agente; associação não
é causalidade; desconhecido não vira zero; resultado imaturo é censurado, não
fracasso. Correção é outro registro que ``supersedes`` o anterior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import CONTRACT_DATACLASS, Identifier, Instant, JsonObject, JsonValue, ObservationRecord, Text, Value
from .errors import invalid
from .validate import require_order


@dataclass(**CONTRACT_DATACLASS)
class MetricRef(Value):
    id: Identifier
    definition_version: Text


@dataclass(**CONTRACT_DATACLASS)
class Window(Value):
    start: Instant
    end: Instant

    def check(self) -> None:
        require_order(self.start, self.end, "end", strict=True)


@dataclass(**CONTRACT_DATACLASS)
class OutcomeEvent(ObservationRecord):
    SCHEMA = "cc.outcome_event"
    KIND = "OutcomeEvent"

    customer_ref: Identifier | None = None
    metric: MetricRef
    value: JsonValue = None
    window: Window
    observation: Literal["observed", "unknown", "censored", "not_applicable"]
    source: Identifier
    decision_ids: tuple[Identifier, ...] = ()
    command_ids: tuple[Identifier, ...] = ()
    assignment: JsonObject | None = None
    supersedes: Identifier | None = None

    def check(self) -> None:
        if self.observation == "observed" and self.value is None:
            raise invalid("resultado observado carrega o valor", "value")
        if self.observation != "observed" and self.value is not None:
            raise invalid(f"resultado {self.observation} não tem valor: desconhecido não vira zero", "value")
        if self.supersedes == self.id:
            raise invalid("resultado não substitui a si mesmo", "supersedes")
