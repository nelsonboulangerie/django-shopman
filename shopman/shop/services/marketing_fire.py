"""Versioned command that creates one manually triggered announcement for review."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    Campaign,
    MarketingAuditEvent,
    MarketingCommandReceipt,
)
from shopman.shop.services import (
    audience as audience_service,
)
from shopman.shop.services import (
    audience_snapshot,
)
from shopman.shop.services import (
    campaign as campaign_service,
)
from shopman.shop.services.marketing_commands import (
    MarketingCommandConflict,
    MarketingCommandRejected,
    command_fingerprints,
)
from shopman.shop.services.marketing_contracts import MarketingContractError
from shopman.shop.services.marketing_security import (
    ACTION_FIRE,
    AuthorizationContext,
    authorization_context,
)

_RETENTION = timedelta(days=365 * 5)
_REQUEST_ID_MAX = 100


@dataclass(frozen=True, slots=True)
class FireCommandExecution:
    announcement: Announcement
    receipt: MarketingCommandReceipt
    replayed: bool


FireAuthorizer = Callable[[AuthorizationContext, MarketingCommandReceipt], None]


class MarketingFireUnavailable(MarketingContractError):
    """A fonte necessária falhou e o resultado idempotente ficou registrado."""

    def __init__(self, *, receipt_ref: str) -> None:
        super().__init__(
            code="audience_degraded",
            detail="Não foi possível conferir todas as fontes da audiência.",
            retryable=True,
        )
        self.receipt_ref = receipt_ref
        self.status_code = 503

    def as_payload(self) -> dict[str, Any]:
        return super().as_payload() | {"receipt_ref": self.receipt_ref}


def fire_campaign_command(
    campaign_id: int,
    *,
    actor,
    idempotency_key: str,
    base_version: int,
    audience_rules: Mapping[str, Any] | None,
    authorize: FireAuthorizer,
    request_id: str = "",
) -> FireCommandExecution:
    """Create a reviewable announcement, sealed cohort and durable receipt exactly once."""

    started_at = time.perf_counter()

    if isinstance(campaign_id, bool) or not isinstance(campaign_id, int) or campaign_id <= 0:
        raise MarketingCommandRejected(
            code="invalid_resource_ref",
            detail="Referência de campanha inválida.",
        )
    if not getattr(actor, "pk", None):
        raise MarketingCommandRejected(
            code="invalid_actor",
            detail="O comando exige uma pessoa autenticada.",
        )
    safe_request_id = str(request_id or "")
    if len(safe_request_id) > _REQUEST_ID_MAX or any(
        not (char.isalnum() or char in "._:-") for char in safe_request_id
    ):
        raise MarketingCommandRejected(
            code="invalid_request_id",
            detail="Identificador da requisição inválido.",
        )

    public_rules = dict(audience_rules or {})
    resource_ref = f"campaign:{campaign_id}"
    payload = {"audience_rules": public_rules}
    key_hash, payload_hash = command_fingerprints(
        kind=MarketingCommandReceipt.Kind.FIRE,
        resource_ref=resource_ref,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload=payload,
    )

    deferred: (
        MarketingCommandConflict | MarketingCommandRejected | MarketingFireUnavailable | None
    ) = None
    execution: FireCommandExecution | None = None
    with transaction.atomic():
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

        repeated = (
            MarketingCommandReceipt.objects.filter(
                actor=actor_row,
                idempotency_key_hash=key_hash,
            )
            .select_related("announcement")
            .first()
        )
        if repeated is not None:
            execution = _replay_or_raise(repeated, payload_hash=payload_hash)
        else:
            rule = (
                Campaign.objects.select_for_update()
                .select_related("template")
                .filter(pk=campaign_id)
                .first()
            )
            now = timezone.now()
            common = {
                "kind": MarketingCommandReceipt.Kind.FIRE,
                "actor": actor_row,
                "actor_ref": f"user:{actor_row.pk}",
                "idempotency_key_hash": key_hash,
                "payload_hash": payload_hash,
                "base_version": base_version,
                "resource_ref": resource_ref,
                "request_id": safe_request_id,
                "retention_until": now + _RETENTION,
            }
            if rule is None:
                receipt = MarketingCommandReceipt.objects.create(
                    **common,
                    state=MarketingCommandReceipt.State.REJECTED,
                    outcome={"code": "campaign_not_found"},
                    completed_at=now,
                )
                deferred = MarketingCommandRejected(
                    code="campaign_not_found",
                    detail="Campanha não encontrada.",
                    receipt_ref=str(receipt.ref),
                )
            elif rule.version != base_version:
                receipt = MarketingCommandReceipt.objects.create(
                    **common,
                    state=MarketingCommandReceipt.State.CONFLICT,
                    resulting_version=rule.version,
                    outcome={"code": "version_conflict"},
                    completed_at=now,
                )
                deferred = MarketingCommandConflict(
                    code="version_conflict",
                    detail="A campanha mudou enquanto você conferia o público.",
                    receipt_ref=str(receipt.ref),
                    current_version=rule.version,
                    field_errors={"base_version": ("Use a versão atual.",)},
                )
            elif not rule.is_active:
                receipt = MarketingCommandReceipt.objects.create(
                    **common,
                    state=MarketingCommandReceipt.State.REJECTED,
                    resulting_version=rule.version,
                    outcome={"code": "campaign_inactive"},
                    completed_at=now,
                )
                deferred = MarketingCommandRejected(
                    code="campaign_inactive",
                    detail="Ligue a campanha antes de preparar um disparo.",
                    receipt_ref=str(receipt.ref),
                    current_version=rule.version,
                )
            else:
                selected_rules = public_rules or dict(rule.audience_rules or {})
                resolution = audience_service.resolve(selected_rules, now=now)
                receipt = MarketingCommandReceipt.objects.create(**common)
                if resolution.degraded_sources:
                    receipt.state = MarketingCommandReceipt.State.REJECTED
                    receipt.resulting_version = rule.version
                    receipt.outcome = {"code": "audience_degraded"}
                    receipt.completed_at = now
                    receipt.save(
                        update_fields=[
                            "state",
                            "resulting_version",
                            "outcome",
                            "completed_at",
                        ]
                    )
                    deferred = MarketingFireUnavailable(receipt_ref=str(receipt.ref))
                elif resolution.total <= 0:
                    receipt.state = MarketingCommandReceipt.State.REJECTED
                    receipt.resulting_version = rule.version
                    receipt.outcome = {"code": "no_eligible_audience"}
                    receipt.completed_at = now
                    receipt.save(
                        update_fields=[
                            "state",
                            "resulting_version",
                            "outcome",
                            "completed_at",
                        ]
                    )
                    deferred = MarketingCommandRejected(
                        code="no_eligible_audience",
                        detail="Ninguém está elegível neste público; nada foi criado.",
                        receipt_ref=str(receipt.ref),
                        current_version=rule.version,
                        field_errors={"audience_rules": ("Ajuste o público e conte novamente.",)},
                    )
                else:
                    authorize(
                        authorization_context(
                            action=ACTION_FIRE,
                            resource_ref=resource_ref,
                            base_version=base_version,
                            audience_hash=resolution.cohort_hash,
                            audience_count=resolution.total,
                            platforms=tuple(rule.platforms or ()),
                            consequence="creates_review_announcement",
                        ),
                        receipt,
                    )
                    announcement = campaign_service.fire_now(
                        rule.pk,
                        audience_rules=public_rules or None,
                        author=actor_row,
                        force_review=True,
                        resolved_audience=resolution,
                    )
                    snapshot = audience_snapshot.create_snapshot(
                        resolution,
                        rules=selected_rules,
                        announcement=announcement,
                        version=announcement.version,
                        now=now,
                    )
                    resulting_version = rule.version + 1
                    rule.version = resulting_version
                    rule.updated_at = now
                    rule.save(update_fields=["version", "updated_at"])
                    receipt.announcement = announcement
                    receipt.state = MarketingCommandReceipt.State.COMPLETED
                    receipt.resulting_version = resulting_version
                    receipt.outcome = {
                        "announcement_ref": f"announcement:{announcement.pk}",
                        "audience_count": resolution.total,
                        "snapshot_ref": str(snapshot.ref),
                        "status": announcement.status,
                    }
                    receipt.completed_at = now
                    receipt.save(
                        update_fields=[
                            "announcement",
                            "state",
                            "resulting_version",
                            "outcome",
                            "completed_at",
                        ]
                    )
                    MarketingAuditEvent.objects.create(
                        event_type=MarketingAuditEvent.EventType.CAMPAIGN_FIRED,
                        command=receipt,
                        announcement=announcement,
                        actor=actor_row,
                        actor_ref=f"user:{actor_row.pk}",
                        snapshot=snapshot,
                        base_version=base_version,
                        resulting_version=resulting_version,
                        facts={
                            "audience_count": resolution.total,
                            "cohort_hash": resolution.cohort_hash,
                            "requires_review": True,
                        },
                        request_id=safe_request_id,
                        occurred_at=now,
                        retention_until=now + _RETENTION,
                    )
                    execution = FireCommandExecution(announcement, receipt, False)

    from shopman.shop.services.marketing_observability import (
        record_command,
        record_correlation,
    )

    terminal_receipt = execution.receipt if execution is not None else receipt
    record_command(
        kind=MarketingCommandReceipt.Kind.FIRE,
        outcome=terminal_receipt.state,
        seconds=time.perf_counter() - started_at,
        replayed=bool(execution and execution.replayed),
    )
    record_correlation(
        stage="receipt",
        request_id=terminal_receipt.request_id,
        receipt_ref=str(terminal_receipt.ref),
    )

    if deferred is not None:
        raise deferred
    if execution is None:
        raise RuntimeError("O comando de disparo terminou sem resultado.")
    return execution


def _replay_or_raise(
    receipt: MarketingCommandReceipt,
    *,
    payload_hash: str,
) -> FireCommandExecution:
    if receipt.payload_hash != payload_hash:
        raise MarketingCommandConflict(
            code="idempotency_conflict",
            detail="Esta chave de idempotência já pertence a outro comando.",
            receipt_ref=str(receipt.ref),
            current_version=receipt.resulting_version,
        )
    code = str((receipt.outcome or {}).get("code") or receipt.state)
    if receipt.state == MarketingCommandReceipt.State.CONFLICT:
        raise MarketingCommandConflict(
            code=code,
            detail="A campanha continua em conflito com a versão revisada.",
            receipt_ref=str(receipt.ref),
            current_version=receipt.resulting_version,
        )
    if receipt.state == MarketingCommandReceipt.State.REJECTED:
        if code == "audience_degraded":
            raise MarketingFireUnavailable(receipt_ref=str(receipt.ref))
        raise MarketingCommandRejected(
            code=code,
            detail="O disparo continua recusado pelo estado atual.",
            receipt_ref=str(receipt.ref),
            current_version=receipt.resulting_version,
        )
    if receipt.announcement is None:
        raise RuntimeError("Um comprovante concluído de disparo não possui anúncio.")
    return FireCommandExecution(receipt.announcement, receipt, True)
