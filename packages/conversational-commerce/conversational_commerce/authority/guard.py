"""A guarda do ponto de efeito, do núcleo (implementa ``ports.guard.EffectGuard``).

O executor chama ``verify(state)`` dentro da mesma unidade atômica do efeito,
com o estado vigente naquele instante (v2 4.7, propriedade 4). A guarda recusa:

| Código | Quando |
|---|---|
| ``authority_revoked`` | a concessão foi revogada, ou a época de posse mudou (a pessoa assumiu) |
| ``grant_expired`` | o instante do efeito está fora da validade da concessão |
| ``terms_changed`` | o hash dos termos vigentes não é o do comando |
| ``revision_conflict`` | a versão de um alvo não é a que o comando esperava |

Ela não decide nada além disso, não chama porta e não guarda estado, salvo o
que viu (``seen``), para a conformidade provar que foi chamada.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from conversational_commerce.contracts import ActionCommand, AuthorizationGrant
from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.ports import EffectState, PortError


@dataclass
class Revocations:
    """As concessões revogadas. A revogação vale a partir de quando é registrada."""

    revoked: dict[str, str] = field(default_factory=dict)

    def revoke(self, grant_id: str, at: str) -> None:
        self.revoked.setdefault(grant_id, at)

    def is_revoked(self, grant_id: str, now: str) -> bool:
        at = self.revoked.get(grant_id)
        return at is not None and at <= now


@dataclass
class CoreEffectGuard:
    grant: AuthorizationGrant
    command: ActionCommand
    revocations: Revocations = field(default_factory=Revocations)
    seen: list[EffectState] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.command.grant_id != self.grant.grant_id:
            raise ValueError("o comando não é desta concessão")
        if self.command.action != self.grant.action or set(self.command.targets) - set(self.grant.targets):
            raise ValueError("o comando pede ação ou alvo fora da concessão")
        if self.command.terms_hash != self.grant.terms_hash:
            raise ValueError("o comando não está preso aos termos da concessão")

    def verify(self, state: EffectState) -> None:
        self.seen.append(state)
        grant, command = self.grant, self.command
        if grant.revoked_at is not None and grant.revoked_at <= state.now:
            raise PortError(ErrorCode.AUTHORITY_REVOKED, "concessão revogada")
        if self.revocations.is_revoked(grant.grant_id, state.now):
            raise PortError(ErrorCode.AUTHORITY_REVOKED, "concessão revogada")
        if state.ownership_epoch != command.expected_ownership_epoch:
            raise PortError(ErrorCode.AUTHORITY_REVOKED, "a posse mudou depois da decisão")
        if not grant.valid_from <= state.now < grant.valid_until:
            raise PortError(ErrorCode.GRANT_EXPIRED, "o efeito está fora da validade da concessão")
        if command.terms_hash is not None and state.terms_hash != command.terms_hash:
            raise PortError(ErrorCode.TERMS_CHANGED, "os termos vigentes não são os confirmados")
        for target, expected in command.expected_versions.items():
            if state.versions.get(target) != expected:
                raise PortError(ErrorCode.REVISION_CONFLICT, f"{target} mudou desde a decisão")
