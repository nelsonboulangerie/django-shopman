"""``ActionCommand``: a ordem durável ao executor (estrito).

Retentativa não muda parâmetros, alvo nem termos (v2 5.5): por isso o comando
carrega ``content_hash``, o hash do que ele manda fazer, e o validador confere.
Mesma chave de idempotência com outro ``content_hash`` é conflito (N08), e é o
executor que decide isso; aqui o contrato só garante que o hash é o do conteúdo.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .canonical import sha256_hash, thaw_json
from .common import (
    CONTRACT_DATACLASS,
    Hash,
    Identifier,
    Instant,
    JsonObject,
    NonNegativeInt,
    StrictRecord,
    Value,
)
from .errors import invalid
from .validate import require_order, require_unique


@dataclass(**CONTRACT_DATACLASS)
class Idempotency(Value):
    scope: Identifier
    key: Identifier


def command_content(
    *,
    action: str,
    targets: tuple[str, ...],
    parameters: Mapping[str, Any],
    terms_hash: str | None,
) -> dict[str, Any]:
    """O conteúdo que o ``content_hash`` cobre: ação, alvos, parâmetros e termos."""
    content: dict[str, Any] = {"action": action, "targets": list(targets), "parameters": thaw_json(parameters)}
    if terms_hash is not None:
        content["terms_hash"] = terms_hash
    return content


def command_content_hash(
    *,
    action: str,
    targets: tuple[str, ...],
    parameters: Mapping[str, Any],
    terms_hash: str | None,
) -> str:
    return sha256_hash(command_content(action=action, targets=targets, parameters=parameters, terms_hash=terms_hash))


@dataclass(**CONTRACT_DATACLASS)
class ActionCommand(StrictRecord):
    SCHEMA = "cc.action_command"
    KIND = "ActionCommand"

    command_id: Identifier
    decision_id: Identifier
    grant_id: Identifier
    action: Identifier
    targets: tuple[Identifier, ...]
    parameters: JsonObject
    terms_hash: Hash | None = None
    expected_versions: Mapping[str, NonNegativeInt]
    expected_ownership_epoch: NonNegativeInt
    idempotency: Idempotency
    content_hash: Hash
    deadline: Instant

    def check(self) -> None:
        if not self.targets:
            raise invalid("comando sem alvo", "targets")
        require_unique(self.targets, "targets")
        require_order(self.occurred_at, self.deadline, "deadline", strict=True)
        expected = command_content_hash(
            action=self.action, targets=self.targets, parameters=self.parameters, terms_hash=self.terms_hash
        )
        if self.content_hash != expected:
            raise invalid("content_hash não é o hash de ação, alvos, parâmetros e termos", "content_hash")
