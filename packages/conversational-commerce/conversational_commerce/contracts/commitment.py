"""``Commitment``: o que a casa ficou devendo, promessa ou caso (observação).

Invariantes (v2 5.5, N04): toda promessa tem dono e prazo, ou a falta do prazo
declarada com contingência; sem dono possível não se promete. Reconhecer,
aceitar e cumprir são eventos distintos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import CONTRACT_DATACLASS, Identifier, Instant, ObservationRecord, Text, Value
from .errors import invalid

CommitmentState = Literal["open", "accepted", "fulfilled", "broken", "expired", "reopened"]


@dataclass(**CONTRACT_DATACLASS)
class DeadlineSet(Value):
    status: Literal["set"] = "set"
    at: Instant
    rule_ref: Identifier


@dataclass(**CONTRACT_DATACLASS)
class DeadlineAbsent(Value):
    status: Literal["absent"] = "absent"
    absent_reason: Text
    contingency: Identifier


@dataclass(**CONTRACT_DATACLASS)
class Commitment(ObservationRecord):
    SCHEMA = "cc.commitment"
    KIND = "Commitment"

    commitment_id: Identifier
    type: Literal["promise", "case"]
    obligation: Text
    owner: Identifier
    deadline: DeadlineSet | DeadlineAbsent
    fulfillment_criterion: Text
    evidence: tuple[Identifier, ...] = ()
    state: CommitmentState
    problem_code: Identifier | None = None
    requested_resolution: Text | None = None
    reopened_from: Identifier | None = None

    def check(self) -> None:
        if self.type == "case" and self.problem_code is None:
            raise invalid("caso carrega o código do problema", "problem_code")
        if self.type == "promise" and (self.problem_code is not None or self.requested_resolution is not None):
            raise invalid("promessa não tem problema nem resolução pedida", "problem_code")
        if self.state == "fulfilled" and not self.evidence:
            raise invalid("cumprido exige evidência", "evidence")
        if (self.state == "reopened") != (self.reopened_from is not None):
            raise invalid("reopened_from existe se, e só se, o estado é reopened", "reopened_from")
