"""``ActionReceipt``: estado × efeito observado de um comando (estrito).

Só quatro combinações existem (v2 4.7):

| status    | effect      | significado                               |
|-----------|-------------|-------------------------------------------|
| success   | applied     | efeito comprovado                         |
| failure   | not_applied | falha definitiva, sem efeito              |
| pending   | unknown     | aceito, ainda em execução                 |
| unknown   | unknown     | não se sabe se aconteceu: reconciliar     |

Sucesso exige efeito comprovado; resposta que não chegou é desconhecido, nunca
falha. Pendente e desconhecido carregam prazo e responsável da reconciliação.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from .canonical import FrozenMap
from .common import (
    CONTRACT_DATACLASS,
    Identifier,
    Instant,
    NonNegativeInt,
    StrictRecord,
    Value,
)
from .errors import ErrorCode, invalid
from .validate import require_order

ReceiptStatus = Literal["success", "failure", "pending", "unknown"]
ReceiptEffect = Literal["applied", "not_applied", "unknown"]

VALID_COMBINATIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("success", "applied"),
        ("failure", "not_applied"),
        ("pending", "unknown"),
        ("unknown", "unknown"),
    }
)

ErrorCodeName = Literal[tuple(code.value for code in ErrorCode)]  # type: ignore[valid-type]


@dataclass(**CONTRACT_DATACLASS)
class ReceiptError(Value):
    code: ErrorCodeName
    retry: Literal["never", "same_key", "after_reconcile"]


@dataclass(**CONTRACT_DATACLASS)
class Reconciliation(Value):
    deadline: Instant
    owner: Identifier


@dataclass(**CONTRACT_DATACLASS)
class ActionReceipt(StrictRecord):
    SCHEMA = "cc.action_receipt"
    KIND = "ActionReceipt"

    command_id: Identifier
    status: ReceiptStatus
    effect: ReceiptEffect
    domain_refs: Mapping[str, Identifier] = field(default_factory=FrozenMap)
    observed_versions: Mapping[str, NonNegativeInt] = field(default_factory=FrozenMap)
    error: ReceiptError | None = None
    reconciliation: Reconciliation | None = None
    supersedes: Identifier | None = None

    def check(self) -> None:
        if (self.status, self.effect) not in VALID_COMBINATIONS:
            raise invalid(f"combinação proibida: status {self.status} com effect {self.effect}", "effect")
        if self.status == "success" and self.error is not None:
            raise invalid("sucesso não carrega erro", "error")
        if self.status == "failure":
            if self.error is None:
                raise invalid("falha carrega o erro e a instrução de retentativa", "error")
            if self.error.retry != "never":
                raise invalid("falha é definitiva: nova intenção pede nova decisão, não retentativa", "error", "retry")
        if self.status in ("pending", "unknown") and self.error is not None and self.error.retry == "never":
            raise invalid("efeito desconhecido se reconcilia com a mesma chave; retry never não cabe", "error", "retry")
        if self.status in ("pending", "unknown"):
            if self.reconciliation is None:
                raise invalid(f"{self.status} exige prazo e responsável da reconciliação", "reconciliation")
            require_order(self.occurred_at, self.reconciliation.deadline, "reconciliation", strict=True)
        elif self.reconciliation is not None:
            raise invalid(f"{self.status} é terminal e não tem reconciliação", "reconciliation")
        if self.status == "success" and not self.domain_refs:
            raise invalid("sucesso aponta o efeito no domínio (domain_refs)", "domain_refs")
        if self.supersedes == self.id:
            raise invalid("recibo não substitui a si mesmo", "supersedes")
