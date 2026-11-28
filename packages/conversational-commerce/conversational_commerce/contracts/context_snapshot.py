"""``ContextSnapshot``: o que o núcleo sabia quando decidiu (observação, imutável, com hash).

Invariante (v2 5.5, N14): imutável; hipótese não vira fato; não garante que o
mundo esteja igual no instante do efeito. O ``DecisionRecord`` aponta o
snapshot pelo hash.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from .common import (
    CONTRACT_DATACLASS,
    Fact,
    Hash,
    Identifier,
    IdentityAssurance,
    JsonObject,
    JsonValue,
    NonNegativeInt,
    ObservationRecord,
    Prediction,
    Value,
    VersionRef,
)
from .errors import invalid
from .need import NeedState
from .validate import require_unique


@dataclass(**CONTRACT_DATACLASS)
class IdentityClaim(Value):
    subject_ref: Identifier | None = None
    assurance: IdentityAssurance

    def check(self) -> None:
        if self.assurance == "anonymous" and self.subject_ref is not None:
            raise invalid("identidade anônima não tem subject_ref", "subject_ref")
        if self.assurance != "anonymous" and self.subject_ref is None:
            raise invalid("identidade não anônima precisa de subject_ref", "subject_ref")


@dataclass(**CONTRACT_DATACLASS)
class NeedView(Value):
    need_id: Identifier
    type: Identifier
    state: NeedState


@dataclass(**CONTRACT_DATACLASS)
class Hypothesis(Value):
    """O que se supõe, com confiança. Nunca vira fato."""

    claim: Identifier
    value: JsonValue
    confidence: Prediction


@dataclass(**CONTRACT_DATACLASS)
class ContextSnapshot(ObservationRecord):
    SCHEMA = "cc.context_snapshot"
    KIND = "ContextSnapshot"
    HASH_FIELD: ClassVar[str | None] = "hash"

    episode_version: NonNegativeInt
    ownership_epoch: NonNegativeInt
    identity: IdentityClaim
    needs: tuple[NeedView, ...] = ()
    facts: Mapping[str, Fact]
    hypotheses: tuple[Hypothesis, ...] = ()
    unknowns: tuple[Identifier, ...] = ()
    dialogue_state: JsonObject
    relationship_state: JsonObject
    open_commitments: tuple[Identifier, ...] = ()
    profile_ref: VersionRef
    policy_ref: VersionRef
    # None só no rascunho, antes de ``seal()``; no documento é obrigatório.
    hash: Hash | None = None

    def check(self) -> None:
        if self.episode_id is None:
            raise invalid("snapshot pertence a um episódio", "episode_id")
        require_unique((need.need_id for need in self.needs), "needs")
        hypothesized = {hypothesis.claim for hypothesis in self.hypotheses}
        clash = sorted(hypothesized & set(self.facts))
        if clash:
            raise invalid(f"a mesma chave não é fato e hipótese ao mesmo tempo: {clash}", "hypotheses")
