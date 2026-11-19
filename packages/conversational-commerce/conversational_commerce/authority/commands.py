"""O comando: a ordem durável ao executor, com chave de idempotência estável.

A chave nasce do que o comando É, nunca de quando foi feito:
``<episódio>.<ação>.<alvo>.<termos ou parâmetros>``. Retentativa usa o MESMO
comando: mesma chave e mesmo conteúdo (``content_hash``, F1). Mudou o conteúdo,
é outro pedido, que pede outra decisão; a mesma chave com outro conteúdo é
``idempotency_conflict`` (N08, K09).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from conversational_commerce.contracts import ActionCommand, AuthorizationGrant, sha256_hash
from conversational_commerce.contracts.action_command import command_content_hash

from .grants import later

COMMAND_DEADLINE_SECONDS = 15 * 60


def idempotency_key(*, episode_id: str, action: str, target: str, terms_hash: str | None,
                    parameters: Mapping[str, Any]) -> str:
    """Estável para o mesmo pedido: termos confirmados, ou os parâmetros da mudança."""
    basis = terms_hash or sha256_hash({"parameters": dict(parameters)})
    return f"{episode_id}.{action}.{target}.{basis.removeprefix('sha256:')[:16]}"


def build_command(*, record: Mapping[str, Any], command_id: str, decision_id: str, grant: AuthorizationGrant,
                  parameters: Mapping[str, Any], expected_versions: Mapping[str, int], ownership_epoch: int,
                  scope: str, now: str, deadline_seconds: int = COMMAND_DEADLINE_SECONDS) -> ActionCommand:
    """O comando que executa a concessão: a ação, os alvos e os termos são os dela."""
    targets = tuple(grant.targets)
    key = idempotency_key(episode_id=record["episode_id"], action=grant.action, target=targets[0],
                          terms_hash=grant.terms_hash, parameters=parameters)
    deadline = min(later(now, deadline_seconds), grant.valid_until)
    return ActionCommand(
        **record, command_id=command_id, decision_id=decision_id, grant_id=grant.grant_id, action=grant.action,
        targets=targets, parameters=dict(parameters), terms_hash=grant.terms_hash,
        expected_versions=dict(expected_versions), expected_ownership_epoch=ownership_epoch,
        idempotency={"scope": scope, "key": key},
        content_hash=command_content_hash(action=grant.action, targets=targets, parameters=parameters,
                                          terms_hash=grant.terms_hash),
        deadline=deadline)
