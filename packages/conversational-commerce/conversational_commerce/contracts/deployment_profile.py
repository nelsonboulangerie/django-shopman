"""``DeploymentProfile``: a configuração versionada de um inquilino (estrito, v2 5.8).

Regra única: campo sem decisão fica ausente, com motivo (``LineAbsent``), e a
ação que depende dele fica inelegível, com código (``profile_line_absent``,
``profile_line_not_approved``; F2). Informar a limitação e encaminhar seguem
possíveis. Linha ``proposed`` não vale como aprovada.

Este módulo só dá a FORMA do perfil. Avaliar linha, ligar ação e o perfil de
teste são do F2.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .common import (
    CONTRACT_DATACLASS,
    AuthorityLevel,
    Identifier,
    IdentityAssurance,
    Instant,
    JsonValue,
    Money,
    NonNegativeInt,
    PositiveInt,
    StrictRecord,
    Text,
    Value,
)
from .errors import invalid
from .validate import require_unique


@dataclass(**CONTRACT_DATACLASS)
class ActionRule(Value):
    authority: AuthorityLevel
    # Canal → degrau mínimo da escada de identidade.
    min_identity: Mapping[str, IdentityAssurance]
    confirmation: bool
    caps: tuple[Identifier, ...] = ()
    line_ref: Identifier | None = None


@dataclass(**CONTRACT_DATACLASS)
class LineSet(Value):
    status: Literal["set"] = "set"
    value: JsonValue


@dataclass(**CONTRACT_DATACLASS)
class LineAbsent(Value):
    status: Literal["absent"] = "absent"
    reason: Text


@dataclass(**CONTRACT_DATACLASS)
class ProfileLine(Value):
    """Uma decisão do perfil, com dono, data e estado."""

    id: Identifier
    setting: LineSet | LineAbsent
    owner: Identifier
    decided_at: Instant | None = None
    state: Literal["proposed", "validating", "approved"]

    def check(self) -> None:
        if self.state == "approved" and isinstance(self.setting, LineAbsent):
            raise invalid("linha ausente não pode estar aprovada", "state")
        if self.state == "approved" and self.decided_at is None:
            raise invalid("linha aprovada diz quando foi decidida", "decided_at")


@dataclass(**CONTRACT_DATACLASS)
class FactSource(Value):
    source: Identifier
    validity_rule: Identifier


@dataclass(**CONTRACT_DATACLASS)
class StaffQueue(Value):
    role: Identifier
    nominal_acceptance: bool
    accept_within_seconds: PositiveInt
    respond_within_seconds: PositiveInt
    after_hours_contingency: Identifier


@dataclass(**CONTRACT_DATACLASS)
class TurnLimits(Value):
    max_steps: PositiveInt
    max_seconds: PositiveInt
    max_queries: NonNegativeInt
    max_model_calls: NonNegativeInt
    max_spend: Money
    # Quantos turnos recentes vão ao leitor como contexto (ADR-051); zero, nenhum.
    reading_context_turns: NonNegativeInt = 0

    def check(self) -> None:
        if self.max_spend.amount_minor < 0:
            raise invalid("teto de gasto negativo", "max_spend")


@dataclass(**CONTRACT_DATACLASS)
class Privacy(Value):
    purposes: tuple[Identifier, ...]
    # Tipo de dado → dias de retenção.
    retention_days: Mapping[str, NonNegativeInt]
    # Destinatário (inclusive cada modelo) → campos permitidos.
    fields_by_recipient: Mapping[str, tuple[Identifier, ...]]


@dataclass(**CONTRACT_DATACLASS)
class MetricDefinition(Value):
    id: Identifier
    definition_version: Text
    window_seconds: PositiveInt
    design: Identifier


@dataclass(**CONTRACT_DATACLASS)
class DeploymentProfile(StrictRecord):
    SCHEMA = "cc.deployment_profile"
    KIND = "DeploymentProfile"

    version: Text
    # Porta → capacidades declaradas.
    adapters: Mapping[str, tuple[Identifier, ...]]
    catalog_version: Text
    policy_version: Text
    house_rules_ref: Identifier | None = None
    # Movimento → regra da ação.
    actions: Mapping[str, ActionRule]
    lines: tuple[ProfileLine, ...] = ()
    # Tipo de fato → fonte autorizada e regra de validade.
    fact_sources: Mapping[str, FactSource]
    staff_queue: StaffQueue | None = None
    limits: TurnLimits
    privacy: Privacy
    metrics: tuple[MetricDefinition, ...] = ()

    def check(self) -> None:
        require_unique((line.id for line in self.lines), "lines")
        require_unique((metric.id for metric in self.metrics), "metrics")
        line_ids = {line.id for line in self.lines}
        for move, rule in self.actions.items():
            if rule.line_ref is not None and rule.line_ref not in line_ids:
                raise invalid(f"line_ref aponta linha inexistente: {rule.line_ref}", "actions", move, "line_ref")
