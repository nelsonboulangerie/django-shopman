"""Contratos estáveis da cadeia de Marketing.

Este módulo não executa I/O nem conhece destinatários. Ele concentra o vocabulário
que precisa permanecer idêntico entre commands, outbox, ledger, adapters e
projections. Estados externos são deliberadamente conservadores: uma resposta
perdida depois de um possível efeito nunca vira falha repetível por suposição.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from django.utils import timezone


class CommandState(StrEnum):
    """Resultado observável de um comando mutável."""

    ACCEPTED = "accepted"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class DeliveryState(StrEnum):
    """Estado de um efeito lógico para um único alvo e plataforma."""

    PLANNED = "planned"
    SUPPRESSED = "suppressed"
    QUEUED = "queued"
    SENDING = "sending"
    ACCEPTED = "accepted"
    CONFIRMED = "confirmed"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ProviderOutcomeKind(StrEnum):
    """Taxonomia que um adapter pode afirmar sem exagerar a garantia externa."""

    NOT_ATTEMPTED = "not_attempted"
    ACCEPTED_UNCONFIRMED = "accepted_unconfirmed"
    CONFIRMED = "confirmed"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"
    UNKNOWN = "unknown"


_DELIVERY_TRANSITIONS: dict[DeliveryState, frozenset[DeliveryState]] = {
    DeliveryState.PLANNED: frozenset({
        DeliveryState.SUPPRESSED,
        DeliveryState.QUEUED,
        DeliveryState.CANCELLED,
        DeliveryState.EXPIRED,
    }),
    DeliveryState.QUEUED: frozenset({
        DeliveryState.SENDING,
        DeliveryState.SUPPRESSED,
        DeliveryState.CANCELLED,
        DeliveryState.EXPIRED,
    }),
    DeliveryState.SENDING: frozenset({
        DeliveryState.ACCEPTED,
        DeliveryState.CONFIRMED,
        DeliveryState.FAILED_RETRYABLE,
        DeliveryState.FAILED_FINAL,
        DeliveryState.UNKNOWN,
    }),
    DeliveryState.ACCEPTED: frozenset({
        DeliveryState.CONFIRMED,
        DeliveryState.FAILED_FINAL,
    }),
    DeliveryState.FAILED_RETRYABLE: frozenset({DeliveryState.QUEUED}),
    DeliveryState.UNKNOWN: frozenset({
        DeliveryState.ACCEPTED,
        DeliveryState.CONFIRMED,
        DeliveryState.FAILED_RETRYABLE,
        DeliveryState.FAILED_FINAL,
    }),
    DeliveryState.SUPPRESSED: frozenset(),
    DeliveryState.CONFIRMED: frozenset(),
    DeliveryState.FAILED_FINAL: frozenset(),
    DeliveryState.CANCELLED: frozenset(),
    DeliveryState.EXPIRED: frozenset(),
}


class Clock(Protocol):
    """Relógio injetável usado por contratos e workers determinísticos."""

    def now(self) -> datetime: ...


class SystemClock:
    """Relógio de produção; testes usam um relógio congelado local."""

    def now(self) -> datetime:
        return timezone.now()


@dataclass(slots=True)
class MarketingContractError(Exception):
    """Erro estruturado que atravessa service, API e Projection sem adivinhação."""

    code: str
    detail: str
    retryable: bool = False
    field_errors: dict[str, tuple[str, ...]] = field(default_factory=dict)
    request_id: str = ""
    current_version: int | None = None

    def __str__(self) -> str:
        return self.detail

    def as_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "retryable": self.retryable,
            "field_errors": {
                key: list(messages) for key, messages in self.field_errors.items()
            },
            "request_id": self.request_id,
            "current_version": self.current_version,
        }


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    """Resultado sanitizado de uma tentativa no limite do fornecedor."""

    kind: ProviderOutcomeKind
    code: str
    retryable: bool
    provider_receipt_ref: str = ""
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        expected_retryable = self.kind in {
            ProviderOutcomeKind.NOT_ATTEMPTED,
            ProviderOutcomeKind.FAILED_RETRYABLE,
        }
        if self.retryable != expected_retryable:
            raise ValueError(
                f"{self.kind.value} exige retryable={str(expected_retryable).lower()}"
            )
        if self.kind == ProviderOutcomeKind.UNKNOWN and self.provider_receipt_ref:
            raise ValueError("unknown não pode inventar receipt externo")


@dataclass(slots=True)
class ProviderCallFailure(Exception):
    """Sanitized adapter-boundary failure; never carries vendor response/body."""

    kind: ProviderOutcomeKind
    code: str
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {
            ProviderOutcomeKind.NOT_ATTEMPTED,
            ProviderOutcomeKind.FAILED_RETRYABLE,
            ProviderOutcomeKind.FAILED_FINAL,
            ProviderOutcomeKind.UNKNOWN,
        }:
            raise ValueError("ProviderCallFailure exige um outcome de falha")

    def __str__(self) -> str:
        return self.code

    def as_outcome(self) -> ProviderOutcome:
        return ProviderOutcome(
            kind=self.kind,
            code=self.code,
            retryable=self.kind in {
                ProviderOutcomeKind.NOT_ATTEMPTED,
                ProviderOutcomeKind.FAILED_RETRYABLE,
            },
            retry_after_seconds=self.retry_after_seconds,
        )


@dataclass(frozen=True, slots=True)
class ResolvedDispatchArtifact:
    """Conteúdo imutável aprovado; propositalmente não contém audiência/PII."""

    platform: str
    body: str
    hashtags: tuple[str, ...] = ()
    link: str = ""
    image_url: str = ""
    content_version: int = 1
    facts_hash: str = ""

    def as_payload(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "body": self.body,
            "hashtags": list(self.hashtags),
            "link": self.link,
            "image_url": self.image_url,
            "content_version": self.content_version,
            "facts_hash": self.facts_hash,
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.as_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @property
    def artifact_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def ensure_delivery_transition(current: DeliveryState, target: DeliveryState) -> None:
    """Recusa atalhos que apagariam a história ou repetiriam um efeito incerto."""

    if current == target:
        return
    if target not in _DELIVERY_TRANSITIONS[current]:
        raise MarketingContractError(
            code="invalid_delivery_transition",
            detail=f"Transição de {current.value} para {target.value} não é permitida.",
            current_version=None,
        )


def iso_with_offset(value: datetime) -> str:
    """Serializa datas conscientes; timestamp ingênuo é um erro de contrato."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp precisa incluir timezone/offset")
    return value.isoformat()
