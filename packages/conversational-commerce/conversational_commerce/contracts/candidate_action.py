"""``CandidateAction``: um movimento possível, com precondições avaliadas (observação).

Invariante (v2 5.5): fora do catálogo não é executável. Previsão só com
estimador declarado; sem ele, ``Unavailable``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import (
    CONTRACT_DATACLASS,
    AuthorityLevel,
    Identifier,
    Instant,
    JsonObject,
    JsonValue,
    ObservationRecord,
    Prediction,
    Text,
    Value,
)
from .errors import invalid
from .validate import require_unique


@dataclass(**CONTRACT_DATACLASS)
class PreconditionResult(Value):
    code: Identifier
    result: Literal["pass", "fail", "unknown"]
    evidence: JsonValue = None


@dataclass(**CONTRACT_DATACLASS)
class CandidateAction(ObservationRecord):
    SCHEMA = "cc.candidate_action"
    KIND = "CandidateAction"

    candidate_id: Identifier
    need_id: Identifier
    move: Identifier
    move_version: Text
    content: JsonObject
    preconditions: tuple[PreconditionResult, ...]
    expected_effects: tuple[Identifier, ...] = ()
    reversibility: Literal["none_needed", "reversible", "compensable", "irreversible"]
    authority_required: AuthorityLevel
    confirmation_required: bool
    valid_until: Instant | None = None
    prediction: Prediction

    def check(self) -> None:
        if not self.preconditions:
            raise invalid("toda candidata avalia ao menos uma precondição", "preconditions")
        require_unique((p.code for p in self.preconditions), "preconditions")
