"""A concessão: quem autoriza, o quê, sobre quais termos, até quando (v2 4.7).

Quem emite é o núcleo, nunca o modelo (propriedade 3). A concessão com base em
confirmação do cliente só existe presa a termos vigentes e a uma confirmação:

- **posterior** aos termos apresentados (N06, K03);
- do mesmo sujeito, inquilino e ambiente dos termos (K06);
- vinda de um evento com identidade estável (N12);
- feita na mesma época de posse em que os termos foram apresentados (K29);
- antes de os termos vencerem.

A validade é a da linha ``grant.validity_seconds`` do perfil, e nunca passa da
dos termos. Linha ausente, sem concessão: a ação fica inelegível (K39).

``Offer`` é o que o turno grava no estado de diálogo quando apresenta os termos:
é contra ela que um "sim" vira concessão.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from conversational_commerce.contracts import AuthorizationGrant, DeploymentProfile, IdentityEvidence
from conversational_commerce.profile import read_line

GRANT_VALIDITY_LINE = "grant.validity_seconds"
FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
OFFER_KEY = "terms_offer"


class GrantRefused(Exception):
    """A concessão não pode ser emitida. ``code`` diz por quê, no vocabulário das precondições."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = str(code)
        super().__init__(f"{self.code}: {message}" if message else self.code)


@dataclass(frozen=True, slots=True)
class Offer:
    """Os termos apresentados e a pergunta que pede a confirmação deles."""

    terms_hash: str
    terms_id: str
    terms_version: int
    target: str
    subject_ref: str
    tenant: str
    environment: str
    presented_at: str
    valid_until: str
    question_id: str
    epoch: int

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dialogue(cls, dialogue_state: Mapping[str, Any]) -> Offer | None:
        raw = dialogue_state.get(OFFER_KEY)
        return None if not raw else cls(**dict(raw))


@dataclass(frozen=True, slots=True)
class Confirmation:
    """O "sim" como o núcleo o vê: o evento, quem fala (do contexto confiável) e a evidência."""

    event_id: str
    event_assurance: str
    occurred_at: str
    tenant: str
    environment: str
    subject_ref: str | None
    epoch: int
    identity_evidence: tuple[IdentityEvidence, ...] = ()


def later(instant: str, seconds: int) -> str:
    moment = datetime.strptime(instant, FORMAT).replace(tzinfo=UTC) + timedelta(seconds=seconds)
    return moment.strftime(FORMAT)


def confirmation_problem(offer: Offer, confirmation: Confirmation, now: str) -> str | None:
    """Por que esta confirmação não autoriza estes termos; ``None`` quando autoriza."""
    if (confirmation.tenant, confirmation.environment) != (offer.tenant, offer.environment):
        return "object_forbidden"
    if confirmation.subject_ref is None or confirmation.subject_ref != offer.subject_ref:
        return "confirmation_from_other_subject"
    if confirmation.event_assurance == "none":
        return "event_identity_unstable"
    if confirmation.occurred_at <= offer.presented_at:
        return "confirmation_before_terms"
    if confirmation.epoch != offer.epoch:
        return "authority_revoked"
    if now >= offer.valid_until:
        return "terms_expired"
    if not confirmation.identity_evidence:
        return "identity_insufficient"
    return None


def _validity(profile: DeploymentProfile) -> int:
    reading = read_line(profile, GRANT_VALIDITY_LINE)
    if not reading.usable:
        raise GrantRefused(reading.code, f"linha {GRANT_VALIDITY_LINE}")
    value = reading.value
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GrantRefused("profile_line_absent", f"linha {GRANT_VALIDITY_LINE} sem duração válida")
    return value


def issue_grant(*, record: Mapping[str, Any], grant_id: str, offer: Offer, confirmation: Confirmation,
                action: str, profile: DeploymentProfile, now: str, issuer: str = "core") -> AuthorizationGrant:
    """A concessão por confirmação do cliente, presa ao hash dos termos. Levanta ``GrantRefused``."""
    problem = confirmation_problem(offer, confirmation, now)
    if problem is not None:
        raise GrantRefused(problem)
    valid_until = min(later(now, _validity(profile)), offer.valid_until)
    return AuthorizationGrant(
        **record, grant_id=grant_id, subject=offer.subject_ref, issuer=issuer, basis="customer_confirmation",
        purpose=action, action=action, targets=(offer.target,), terms_hash=offer.terms_hash, limits={},
        identity_evidence=confirmation.identity_evidence,
        confirmation_evidence={"event_id": confirmation.event_id, "event_assurance": confirmation.event_assurance,
                               "after_terms": True},
        valid_from=now, valid_until=valid_until)


def issue_line_grant(*, record: Mapping[str, Any], grant_id: str, subject: str, action: str,
                     targets: tuple[str, ...], identity_evidence: tuple[IdentityEvidence, ...],
                     profile: DeploymentProfile, now: str, issuer: str = "core") -> AuthorizationGrant:
    """A concessão pela linha do perfil (ação reversível, sem termos, A2). Levanta ``GrantRefused``."""
    if not identity_evidence:
        raise GrantRefused("identity_insufficient")
    return AuthorizationGrant(
        **record, grant_id=grant_id, subject=subject, issuer=issuer, basis="profile_line", purpose=action,
        action=action, targets=targets, limits={}, identity_evidence=identity_evidence, valid_from=now,
        valid_until=later(now, _validity(profile)))
