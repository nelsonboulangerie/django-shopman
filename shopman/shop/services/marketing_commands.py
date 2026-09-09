"""Serializable command boundary for Marketing mutations.

This module owns the mechanics that every decision must share: a session-derived
actor, a canonical payload fingerprint, one durable receipt per idempotency key,
and compare-and-set against an ``Announcement.version`` protected by a row lock.
Business operations (approval, cancellation and so on) are supplied as a callback
and therefore execute in the very same database transaction as the receipt.

There is intentionally no provider or queue call here.  MKT-010 composes sealed
artifacts, audience snapshots, audit and outbox rows through this boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from shopman.shop.models import Announcement, MarketingCommandReceipt
from shopman.shop.services.marketing_contracts import MarketingContractError

_MIN_IDEMPOTENCY_KEY_LENGTH = 16
_MAX_IDEMPOTENCY_KEY_LENGTH = 200
_MAX_OUTCOME_BYTES = 4096
# G-H01 §3.5: command/audit evidence without PII is retained for five years.
_RECEIPT_RETENTION_DAYS = 365 * 5
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
_FORBIDDEN_OUTCOME_KEYS = frozenset({
    "body",
    "content",
    "email",
    "idempotency_key",
    "members",
    "phone",
    "recipient",
    "target_key",
})


class MarketingCommandError(MarketingContractError):
    """Structured command failure with the stable receipt, when one exists."""

    def __init__(
        self,
        *,
        code: str,
        detail: str,
        receipt_ref: str = "",
        current_version: int | None = None,
        field_errors: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            detail=detail,
            retryable=False,
            field_errors=field_errors or {},
            current_version=current_version,
        )
        self.receipt_ref = receipt_ref

    def as_payload(self) -> dict[str, Any]:
        return super().as_payload() | {"receipt_ref": self.receipt_ref}


class MarketingCommandConflict(MarketingCommandError):
    """The key or resource version no longer represents the requested command."""


class MarketingCommandRejected(MarketingCommandError):
    """A well-formed command was rejected by current domain state."""


class RejectCommand(Exception):
    """Signal a domain rejection while retaining its receipt.

    Only machine-safe outcome fields are persisted.  Human copy and arbitrary
    input stay in the API response/audit boundary instead of the generic receipt.
    """

    def __init__(
        self,
        *,
        code: str,
        detail: str,
        outcome: Mapping[str, Any] | None = None,
        field_errors: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.outcome = dict(outcome or {})
        self.field_errors = field_errors or {}


@dataclass(frozen=True, slots=True)
class CommandExecution:
    """Observable result returned both for first execution and safe replay."""

    receipt: MarketingCommandReceipt
    announcement: Announcement | None
    replayed: bool


CommandOperation = Callable[
    [Announcement, MarketingCommandReceipt],
    Mapping[str, Any] | None,
]


def execute_announcement_command(
    *,
    kind: str,
    announcement_id: int,
    actor,
    idempotency_key: str,
    base_version: int,
    payload: Mapping[str, Any],
    operation: CommandOperation,
    request_id: str = "",
) -> CommandExecution:
    """Execute one Announcement mutation with receipt, CAS and row serialization.

    A replay is recognized *before* comparing the current resource version.  That
    ordering is essential: after the first command succeeds, the resource version
    has advanced, but the same key must still return the first outcome rather than
    manufacture a conflict.
    """

    normalized = _validate_input(
        kind=kind,
        announcement_id=announcement_id,
        actor=actor,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload=payload,
        request_id=request_id,
    )
    key_hash, payload_hash, resource_ref, safe_request_id = normalized
    deferred_error: MarketingCommandError | None = None
    execution: CommandExecution | None = None

    with transaction.atomic():
        # Per-actor lock makes lookup/create deterministic even on databases where
        # a unique-conflict would poison the surrounding transaction.  Commands
        # from different actors still serialize on the Announcement row below.
        try:
            actor_row = get_user_model().objects.select_for_update().get(
                pk=actor.pk,
                is_active=True,
            )
        except get_user_model().DoesNotExist as exc:
            raise MarketingCommandRejected(
                code="invalid_actor",
                detail="A sessão não representa uma pessoa ativa.",
            ) from exc
        existing = MarketingCommandReceipt.objects.filter(
            actor=actor_row,
            idempotency_key_hash=key_hash,
        ).select_related("announcement").first()
        if existing is not None:
            if existing.payload_hash != payload_hash:
                raise MarketingCommandConflict(
                    code="idempotency_conflict",
                    detail="Esta chave de idempotência já pertence a outro comando.",
                    receipt_ref=str(existing.ref),
                    current_version=existing.resulting_version,
                    field_errors={
                        "idempotency_key": ("Gere uma nova chave para a nova intenção.",),
                    },
                )
            execution = CommandExecution(
                receipt=existing,
                announcement=existing.announcement,
                replayed=True,
            )
            deferred_error = _terminal_error(existing)
        else:
            announcement = (
                Announcement.objects.select_for_update()
                .filter(pk=announcement_id)
                .first()
            )
            now = timezone.now()
            common = {
                "kind": kind,
                "actor": actor_row,
                "actor_ref": f"user:{actor_row.pk}",
                "idempotency_key_hash": key_hash,
                "payload_hash": payload_hash,
                "base_version": base_version,
                "resource_ref": resource_ref,
                "request_id": safe_request_id,
                "retention_until": now + timedelta(days=_RECEIPT_RETENTION_DAYS),
            }

            if announcement is None:
                receipt = MarketingCommandReceipt.objects.create(
                    **common,
                    state=MarketingCommandReceipt.State.REJECTED,
                    outcome={"code": "announcement_not_found"},
                    completed_at=now,
                )
                deferred_error = MarketingCommandRejected(
                    code="announcement_not_found",
                    detail="Anúncio não encontrado.",
                    receipt_ref=str(receipt.ref),
                )
                execution = CommandExecution(receipt, None, False)
            elif announcement.version != base_version:
                receipt = MarketingCommandReceipt.objects.create(
                    **common,
                    announcement=announcement,
                    state=MarketingCommandReceipt.State.CONFLICT,
                    resulting_version=announcement.version,
                    outcome={"code": "version_conflict"},
                    completed_at=now,
                )
                deferred_error = MarketingCommandConflict(
                    code="version_conflict",
                    detail="O anúncio mudou enquanto você revisava.",
                    receipt_ref=str(receipt.ref),
                    current_version=announcement.version,
                    field_errors={"base_version": ("Use a versão atual.",)},
                )
                execution = CommandExecution(receipt, announcement, False)
            else:
                receipt = MarketingCommandReceipt.objects.create(
                    **common,
                    announcement=announcement,
                )
                try:
                    # A domain rejection must not preserve a half-written callback.
                    # The inner savepoint rolls its writes back while the outer
                    # transaction can still retain the rejected receipt.
                    with transaction.atomic():
                        outcome = _safe_outcome(operation(announcement, receipt) or {})
                except RejectCommand as rejected:
                    # The savepoint restored the database; refresh the Python
                    # object too so the receipt/result cannot echo rolled-back
                    # in-memory fields or a callback-tampered version.
                    announcement.refresh_from_db()
                    outcome = _safe_outcome(
                        {"code": rejected.code} | dict(rejected.outcome)
                    )
                    receipt.state = MarketingCommandReceipt.State.REJECTED
                    receipt.outcome = outcome
                    receipt.resulting_version = announcement.version
                    receipt.completed_at = timezone.now()
                    receipt.save(update_fields=[
                        "state",
                        "outcome",
                        "resulting_version",
                        "completed_at",
                    ])
                    deferred_error = MarketingCommandRejected(
                        code=rejected.code,
                        detail=rejected.detail,
                        receipt_ref=str(receipt.ref),
                        current_version=announcement.version,
                        field_errors=rejected.field_errors,
                    )
                else:
                    announcement.version += 1
                    announcement.save(update_fields=["version"])
                    receipt.state = MarketingCommandReceipt.State.COMPLETED
                    receipt.outcome = outcome
                    receipt.resulting_version = announcement.version
                    receipt.completed_at = timezone.now()
                    receipt.save(update_fields=[
                        "state",
                        "outcome",
                        "resulting_version",
                        "completed_at",
                    ])
                execution = CommandExecution(receipt, announcement, False)

    if deferred_error is not None:
        raise deferred_error
    assert execution is not None
    return execution


def _validate_input(
    *,
    kind: str,
    announcement_id: int,
    actor,
    idempotency_key: str,
    base_version: int,
    payload: Mapping[str, Any],
    request_id: str,
) -> tuple[str, str, str, str]:
    if not getattr(actor, "pk", None):
        raise MarketingCommandRejected(
            code="invalid_actor",
            detail="O comando exige uma pessoa autenticada.",
        )
    if isinstance(announcement_id, bool) or not isinstance(announcement_id, int) or announcement_id <= 0:
        raise MarketingCommandRejected(
            code="invalid_resource_ref",
            detail="Referência de anúncio inválida.",
        )
    safe_request_id = str(request_id or "")
    if safe_request_id and not _REQUEST_ID_RE.fullmatch(safe_request_id):
        raise MarketingCommandRejected(
            code="invalid_request_id",
            detail="Identificador da requisição inválido.",
        )

    resource_ref = f"announcement:{announcement_id}"
    key_hash, payload_hash = command_fingerprints(
        kind=kind,
        resource_ref=resource_ref,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload=payload,
    )
    return key_hash, payload_hash, resource_ref, safe_request_id


def command_fingerprints(
    *,
    kind: str,
    resource_ref: str,
    idempotency_key: str,
    base_version: int,
    payload: Mapping[str, Any],
) -> tuple[str, str]:
    """Validate and fingerprint a human or system command without storing raw keys."""

    if kind not in MarketingCommandReceipt.Kind.values:
        raise MarketingCommandRejected(
            code="invalid_command_kind",
            detail="Tipo de comando de Marketing inválido.",
            field_errors={"kind": ("Use um comando conhecido.",)},
        )
    if isinstance(base_version, bool) or not isinstance(base_version, int) or base_version <= 0:
        raise MarketingCommandRejected(
            code="invalid_base_version",
            detail="Informe a versão positiva exibida na revisão.",
            field_errors={"base_version": ("A versão deve ser um inteiro positivo.",)},
        )
    key = str(idempotency_key or "")
    if not (
        _MIN_IDEMPOTENCY_KEY_LENGTH <= len(key) <= _MAX_IDEMPOTENCY_KEY_LENGTH
        and all(33 <= ord(char) <= 126 for char in key)
    ):
        raise MarketingCommandRejected(
            code="invalid_idempotency_key",
            detail="Idempotency-Key ausente ou inválida.",
            field_errors={
                "idempotency_key": (
                    f"Use de {_MIN_IDEMPOTENCY_KEY_LENGTH} a {_MAX_IDEMPOTENCY_KEY_LENGTH} caracteres ASCII sem espaços.",
                ),
            },
        )
    if not isinstance(payload, Mapping):
        raise MarketingCommandRejected(
            code="invalid_command_payload",
            detail="O payload do comando deve ser um objeto.",
        )
    resource_ref = str(resource_ref or "")
    if not resource_ref or len(resource_ref) > 120:
        raise MarketingCommandRejected(
            code="invalid_resource_ref",
            detail="Referência do recurso inválida.",
        )
    envelope = {
        "base_version": base_version,
        "kind": kind,
        "payload": dict(payload),
        "resource_ref": resource_ref,
    }
    try:
        canonical = json.dumps(
            envelope,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise MarketingCommandRejected(
            code="invalid_command_payload",
            detail="O payload do comando não é JSON canônico.",
        ) from exc
    return (
        _keyed_hash("idempotency", key),
        _keyed_hash("payload", canonical),
    )


def _keyed_hash(domain: str, value: str) -> str:
    return hmac.new(
        str(settings.SECRET_KEY).encode("utf-8"),
        f"marketing-command:{domain}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _safe_outcome(outcome: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(outcome, Mapping):
        raise ValueError("O outcome do comando deve ser um objeto.")
    normalized = dict(outcome)
    _reject_sensitive_keys(normalized)
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("O outcome do comando deve ser JSON.") from exc
    if len(encoded) > _MAX_OUTCOME_BYTES:
        raise ValueError("O outcome do comando excede o limite seguro.")
    return normalized


def _reject_sensitive_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if str(key).lower() in _FORBIDDEN_OUTCOME_KEYS:
                raise ValueError(f"Campo sensível não permitido no receipt: {key}")
            _reject_sensitive_keys(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _reject_sensitive_keys(nested)


def _terminal_error(receipt: MarketingCommandReceipt) -> MarketingCommandError | None:
    code = str((receipt.outcome or {}).get("code") or receipt.state)
    if receipt.state == MarketingCommandReceipt.State.CONFLICT:
        if code == "version_conflict":
            return MarketingCommandConflict(
                code=code,
                detail="O anúncio mudou enquanto você revisava.",
                receipt_ref=str(receipt.ref),
                current_version=receipt.resulting_version,
                field_errors={"base_version": ("Use a versão atual.",)},
            )
        return MarketingCommandConflict(
            code=code,
            detail="O comando conflita com uma decisão anterior.",
            receipt_ref=str(receipt.ref),
            current_version=receipt.resulting_version,
        )
    if receipt.state == MarketingCommandReceipt.State.REJECTED:
        detail = (
            "Anúncio não encontrado."
            if code == "announcement_not_found"
            else "O comando continua recusado pelo estado atual."
        )
        return MarketingCommandRejected(
            code=code,
            detail=detail,
            receipt_ref=str(receipt.ref),
            current_version=receipt.resulting_version,
        )
    return None
