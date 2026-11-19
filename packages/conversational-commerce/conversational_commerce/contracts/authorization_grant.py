"""``AuthorizationGrant``: quem autoriza, o quê, sobre quais termos, até quando (estrito).

Emitida pelo núcleo a partir de evidência e do perfil, nunca pelo modelo; o
executor confere no ponto de efeito (v2 4.7, propriedade 3). Não vale para
termos, destinatário ou escopo alterados.

Regra do contrato (v2 4.7, propriedade 1; N06): concessão com base em
confirmação do cliente só existe presa a termos (``terms_hash``) e a uma
confirmação POSTERIOR a eles. ``after_terms`` falso não é concessão, é recusa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .common import (
    CONTRACT_DATACLASS,
    EventAssurance,
    Hash,
    Identifier,
    IdentityEvidence,
    Instant,
    Money,
    PositiveInt,
    StrictRecord,
    Value,
)
from .errors import invalid
from .validate import require_order, require_unique


@dataclass(**CONTRACT_DATACLASS)
class GrantLimits(Value):
    max_amount: Money | None = None
    max_uses: PositiveInt | None = None

    def check(self) -> None:
        if self.max_amount is not None and self.max_amount.amount_minor < 0:
            raise invalid("teto negativo", "max_amount")


@dataclass(**CONTRACT_DATACLASS)
class ConfirmationEvidence(Value):
    event_id: Identifier
    event_assurance: EventAssurance
    after_terms: bool


@dataclass(**CONTRACT_DATACLASS)
class AuthorizationGrant(StrictRecord):
    SCHEMA = "cc.authorization_grant"
    KIND = "AuthorizationGrant"

    grant_id: Identifier
    subject: Identifier
    issuer: Identifier
    basis: Literal["customer_confirmation", "staff_approval", "profile_line"]
    purpose: Identifier
    action: Identifier
    targets: tuple[Identifier, ...]
    terms_hash: Hash | None = None
    limits: GrantLimits
    identity_evidence: tuple[IdentityEvidence, ...] = ()
    confirmation_evidence: ConfirmationEvidence | None = None
    valid_from: Instant
    valid_until: Instant
    revoked_at: Instant | None = None

    def check(self) -> None:
        if not self.targets:
            raise invalid("concessão sem alvo", "targets")
        require_unique(self.targets, "targets")
        require_order(self.valid_from, self.valid_until, "valid_until", strict=True)
        require_order(self.valid_from, self.revoked_at, "revoked_at")
        if self.basis == "customer_confirmation":
            if self.terms_hash is None:
                raise invalid("confirmação do cliente só autoriza presa a termos", "terms_hash")
            if self.confirmation_evidence is None:
                raise invalid("confirmação do cliente exige a evidência da confirmação", "confirmation_evidence")
            if not self.confirmation_evidence.after_terms:
                raise invalid("confirmação anterior aos termos não autoriza", "confirmation_evidence", "after_terms")
            if self.confirmation_evidence.event_assurance == "none":
                raise invalid("confirmação sem identidade de evento não autoriza", "confirmation_evidence",
                              "event_assurance")
            if not self.identity_evidence:
                raise invalid("confirmação do cliente exige evidência de identidade", "identity_evidence")
