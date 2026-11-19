"""``DecisionRecord``: candidatas, bloqueios, escolha e seleção (observação, imutável).

Invariantes (v2 5.5, N14, N17): registra alternativas e escolha efetiva, não
justificativa posterior; bloqueio depois gera nova decisão ligada
(``parent_decision_id``), nunca reescrita. Seleção determinística não dá suporte
contrafactual e diz isso (``not_applicable``), em vez de gravar "probabilidade 1".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .common import (
    CONTRACT_DATACLASS,
    DecimalText,
    Hash,
    Identifier,
    JsonObject,
    Money,
    NonNegativeInt,
    ObservationRecord,
    Prediction,
    Producer,
    Text,
    Value,
    VersionRef,
)
from .errors import invalid
from .validate import probability as as_probability
from .validate import require_unique


@dataclass(**CONTRACT_DATACLASS)
class SnapshotRef(Value):
    snapshot_ref: Identifier
    snapshot_hash: Hash


@dataclass(**CONTRACT_DATACLASS)
class DecisionCandidate(Value):
    """Uma candidata como a decisão a viu: elegível, ou bloqueada com os motivos."""

    candidate_ref: Identifier
    need_id: Identifier
    move: Identifier
    content: JsonObject
    eligible: bool
    blocked_by: tuple[Identifier, ...] = ()
    prediction: Prediction

    def check(self) -> None:
        if self.eligible == bool(self.blocked_by):
            raise invalid("elegível não tem bloqueio; bloqueada tem ao menos um", "blocked_by")


@dataclass(**CONTRACT_DATACLASS)
class NotApplicable(Value):
    status: Literal["not_applicable"] = "not_applicable"


@dataclass(**CONTRACT_DATACLASS)
class Weight(Value):
    candidate: NonNegativeInt
    probability: DecimalText


@dataclass(**CONTRACT_DATACLASS)
class Propensity(Value):
    """Seleção sorteada: a distribuição DEPOIS dos filtros, a semente e a probabilidade executada."""

    status: Literal["recorded"] = "recorded"
    distribution: tuple[Weight, ...]
    seed: Text
    executed_probability: DecimalText

    def check(self) -> None:
        if not self.distribution:
            raise invalid("distribuição vazia", "distribution")
        require_unique((str(w.candidate) for w in self.distribution), "distribution")
        total = Decimal(0)
        for index, weight in enumerate(self.distribution):
            total += as_probability(weight.probability, "distribution", index, "probability")
        if total != 1:
            raise invalid(f"a distribuição soma {total}, não 1", "distribution")
        if as_probability(self.executed_probability, "executed_probability") == 0:
            raise invalid("ação executada não pode ter probabilidade zero", "executed_probability")


@dataclass(**CONTRACT_DATACLASS)
class Selection(Value):
    method: Literal["deterministic", "seeded"]
    tie_break: Identifier | None = None
    propensity: NotApplicable | Propensity
    experiment: Identifier | None = None

    def check(self) -> None:
        if self.method == "deterministic" and not isinstance(self.propensity, NotApplicable):
            raise invalid("seleção determinística registra propensity not_applicable", "propensity")
        if self.method == "seeded" and not isinstance(self.propensity, Propensity):
            raise invalid("seleção sorteada registra a distribuição", "propensity")


@dataclass(**CONTRACT_DATACLASS)
class ModelCall(Value):
    """Uma chamada a modelo no turno. ``cost`` ausente é custo desconhecido, nunca zero (N21)."""

    model: Producer
    purpose: Identifier
    input_hash: Hash | None = None
    cost: Money | None = None


@dataclass(**CONTRACT_DATACLASS)
class DecisionRecord(ObservationRecord):
    SCHEMA = "cc.decision_record"
    KIND = "DecisionRecord"

    decision_id: Identifier
    turn: NonNegativeInt
    context: SnapshotRef
    candidates: tuple[DecisionCandidate, ...]
    chosen: tuple[NonNegativeInt, ...]
    selection: Selection
    policy: VersionRef
    profile: VersionRef
    model_calls: tuple[ModelCall, ...] = ()
    parent_decision_id: Identifier | None = None

    def check(self) -> None:
        if self.episode_id is None:
            raise invalid("decisão pertence a um episódio", "episode_id")
        if self.parent_decision_id == self.decision_id:
            raise invalid("decisão não é mãe de si mesma", "parent_decision_id")
        require_unique((str(index) for index in self.chosen), "chosen")
        for position, index in enumerate(self.chosen):
            if index >= len(self.candidates):
                raise invalid(f"chosen aponta candidata inexistente: {index}", "chosen", position)
            if not self.candidates[index].eligible:
                raise invalid(f"chosen aponta candidata bloqueada: {index}", "chosen", position)
        propensity = self.selection.propensity
        if isinstance(propensity, Propensity):
            for position, weight in enumerate(propensity.distribution):
                if weight.candidate >= len(self.candidates) or not self.candidates[weight.candidate].eligible:
                    raise invalid("a distribuição só tem candidatas elegíveis (depois dos filtros)",
                                  "selection", "propensity", "distribution", position)
