"""Atomic approval: immutable content + cohort + audit + receipt + outbox.

The request path never calls a provider and never creates a legacy Directive.
Its only external-effect-shaped result is a durable ``MarketingOutbox`` row that
MKT-012 will claim after the transaction is visible.  A failed transaction leaves
none of these records behind; an idempotent replay returns the original graph.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    AudienceSnapshot,
    MarketingAuditEvent,
    MarketingCommandReceipt,
    MarketingContentArtifact,
    MarketingOutbox,
)
from shopman.shop.services import audience as audience_service
from shopman.shop.services import audience_snapshot, marketing_artifacts, marketing_time
from shopman.shop.services.marketing_commands import (
    CommandExecution,
    RejectCommand,
    execute_announcement_command,
)
from shopman.shop.services.marketing_contracts import MarketingContractError

PUBLISH_NOW = "now"
PUBLISH_SCHEDULED = "scheduled"
PUBLISH_MODES = frozenset({PUBLISH_NOW, PUBLISH_SCHEDULED})
APPROVAL_RECORD_RETENTION = timedelta(days=365 * 5)
MIN_GENERAL_COHORT = 10
MAX_ARTIFACT_BYTES = 64 * 1024
_PLATFORMS = frozenset({"instagram", "facebook", "google_business", "whatsapp"})


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    announcement: Announcement
    receipt: MarketingCommandReceipt
    artifact: MarketingContentArtifact
    snapshot: AudienceSnapshot
    outbox: tuple[MarketingOutbox, ...]
    replayed: bool


def approve_command(
    announcement_id: int,
    *,
    actor,
    idempotency_key: str,
    base_version: int,
    publish_mode: str,
    content: Mapping[str, Any],
    platform_content: Mapping[str, Any],
    platforms: Sequence[str],
    publish_at: datetime | None = None,
    publish_timezone: str = "",
    request_id: str = "",
    ai_suggestion_ref: str = "",
    now: datetime | None = None,
    idempotency_payload: Mapping[str, Any] | None = None,
    authorization: Callable[[object, MarketingCommandReceipt], None] | None = None,
) -> ApprovalResult:
    """Approve the exact full content supplied by the reviewing surface.

    ``publish_mode`` is explicit: ``now`` cannot smuggle a timestamp and
    ``scheduled`` cannot omit one.  The content included in the idempotency
    fingerprint is the content persisted in the immutable artifact.
    """

    now = now or timezone.now()
    if timezone.is_naive(now):
        raise MarketingContractError(
            code="invalid_clock",
            detail="O relógio da aprovação precisa incluir timezone.",
        )
    if isinstance(base_version, bool) or not isinstance(base_version, int) or base_version < 1:
        raise MarketingContractError(
            code="invalid_base_version",
            detail="A versão exibida na revisão é inválida.",
            field_errors={"base_version": ("Use um inteiro positivo.",)},
        )
    normalized_mode, normalized_publish_at = normalize_schedule(
        publish_mode,
        publish_at=publish_at,
        now=now,
    )
    safe_content = _json_copy(content, field="content")
    safe_platform_content = _json_copy(platform_content, field="platform_content")
    safe_platforms = _platforms(platforms)
    safe_platform_content = marketing_artifacts.normalize_platform_content(
        platforms=safe_platforms,
        platform_content=safe_platform_content,
    )
    normalized_timezone = _publish_timezone(publish_timezone)
    effective_timezone = normalized_timezone or marketing_time.configured_timezone_name()
    _validate_content(safe_content, safe_platform_content, safe_platforms)
    command_payload = {
        "content": safe_content,
        "platform_content": safe_platform_content,
        "platforms": safe_platforms,
        "publish_at": normalized_publish_at.isoformat() if normalized_publish_at else "",
        "publish_mode": normalized_mode,
        "publish_timezone": effective_timezone,
    }
    fingerprint_payload = (
        _json_copy(idempotency_payload, field="idempotency_payload")
        if idempotency_payload is not None
        else command_payload
    )

    def operation(
        announcement: Announcement,
        receipt: MarketingCommandReceipt,
    ) -> dict[str, Any]:
        if announcement.status not in {
            AnnouncementStatus.DRAFT,
            AnnouncementStatus.PENDING_REVIEW,
        }:
            raise RejectCommand(
                code="announcement_not_reviewable",
                detail="Este anúncio não está mais aguardando decisão.",
                outcome={"status": announcement.status},
            )
        if announcement.is_expired(now=now):
            raise RejectCommand(
                code="announcement_expired",
                detail="Este anúncio expirou. Atualize os fatos antes de publicar.",
                outcome={"status": AnnouncementStatus.EXPIRED},
            )
        if (
            normalized_publish_at is not None
            and announcement.expires_at is not None
            and normalized_publish_at >= announcement.expires_at
        ):
            raise RejectCommand(
                code="scheduled_after_expiry",
                detail="O anúncio expiraria antes de chegar ao horário escolhido.",
                outcome={
                    "expires_at": announcement.expires_at.isoformat(),
                    "publish_at": normalized_publish_at.isoformat(),
                },
                field_errors={
                    "publish_at": ("Escolha um horário anterior à expiração.",),
                },
            )
        if "whatsapp" in safe_platforms:
            base_window = marketing_time.delivery_window(
                normalized_publish_at or now,
                timezone_name=effective_timezone,
            )
            if not base_window.allowed:
                next_allowed = base_window.next_allowed_at
                raise RejectCommand(
                    code=("scheduled_in_quiet_hours" if normalized_publish_at is not None else "quiet_hours_active"),
                    detail=("O WhatsApp fica em silêncio das 20:00 às 08:00. Escolha o próximo horário permitido."),
                    outcome={
                        "next_allowed_at": next_allowed.isoformat() if next_allowed else "",
                        "publish_timezone": effective_timezone,
                    },
                    field_errors={
                        "publish_at": ("Escolha um horário entre 08:00 e 20:00.",),
                    },
                )

        from shopman.shop.services import marketing_facts

        facts = marketing_facts.refresh_for_approval(
            announcement,
            safe_content,
            scheduled_for=normalized_publish_at,
            now=now,
        )
        approved_content = dict(safe_content)
        if facts is not None:
            approved_content["facts"] = facts.as_payload()
        ai_trace = None
        if ai_suggestion_ref:
            from shopman.shop.services import marketing_ai

            try:
                ai_trace = marketing_ai.suggestion_for_approval(
                    ref=ai_suggestion_ref,
                    announcement=announcement,
                    actor=actor,
                    body=str(approved_content.get("body") or ""),
                    hashtags=list(approved_content.get("hashtags") or []),
                )
            except marketing_ai.MarketingAIError as exc:
                raise RejectCommand(
                    code=exc.code,
                    detail=exc.detail,
                    outcome={"ai_suggestion_ref": "invalid"},
                ) from exc
        rules = _audience_rules(announcement)
        sku = str((announcement.trigger_context or {}).get("sku") or "")
        resolution = audience_service.resolve(rules, sku=sku, now=now)
        if resolution.degraded_sources:
            raise RejectCommand(
                code="audience_degraded",
                detail="Não foi possível conferir toda a audiência.",
                outcome={"degraded_source_count": len(resolution.degraded_sources)},
            )
        if "whatsapp" in safe_platforms and resolution.total < MIN_GENERAL_COHORT:
            raise RejectCommand(
                code="audience_below_minimum",
                detail=(
                    f"Campanha geral por WhatsApp exige ao menos {MIN_GENERAL_COHORT} "
                    "pessoas elegíveis. Use o teste sandbox ou ajuste o público."
                ),
                outcome={
                    "eligible_count": resolution.total,
                    "minimum_count": MIN_GENERAL_COHORT,
                },
            )

        platform_bindings = {}
        if "whatsapp" in safe_platforms:
            from shopman.shop.services.marketing_platform_configuration import (
                verified_whatsapp_flow_binding,
            )

            try:
                flow_binding = verified_whatsapp_flow_binding(force=True, now=now)
                from shopman.shop.services.manychat_marketing_safety import (
                    require_safe_delivery,
                )

                require_safe_delivery()
            except MarketingContractError as exc:
                raise RejectCommand(
                    code=exc.code,
                    detail=exc.detail,
                    outcome={"retryable": exc.retryable},
                    field_errors=exc.field_errors,
                ) from exc
            platform_bindings["whatsapp"] = flow_binding.artifact_payload()

        resolved_artifacts = marketing_artifacts.resolve_all_dispatch_artifacts(
            platforms=safe_platforms,
            content=approved_content,
            platform_content=safe_platform_content,
            content_version=announcement.version + 1,
            facts_as_of=facts.as_of.isoformat() if facts is not None else "",
            facts_hash=facts.source_hash if facts is not None else "",
            platform_bindings=platform_bindings,
        )

        approved_version = announcement.version + 1
        artifact_payload = {
            "content": approved_content,
            "content_version": approved_version,
            "platform_content": safe_platform_content,
            "platforms": safe_platforms,
            "resolved_artifacts": marketing_artifacts.resolved_payloads(resolved_artifacts),
            "schema_version": marketing_artifacts.SCHEMA_VERSION,
            "schedule": {
                # A "now" decision is an immediate intent, not a client-chosen
                # timestamp. Keeping it empty makes the sealed hash stable across
                # the human-confirmation round trip; the actual instant is still
                # recorded in the receipt and outbox below.
                "effective_at": (normalized_publish_at.isoformat() if normalized_publish_at else ""),
                "publish_at": (normalized_publish_at.isoformat() if normalized_publish_at else ""),
                "publish_mode": normalized_mode,
                "timezone": effective_timezone,
            },
        }
        if facts is not None:
            artifact_payload["facts"] = facts.as_payload()
        artifact_bytes = canonical_artifact_bytes(artifact_payload)
        if len(artifact_bytes) > MAX_ARTIFACT_BYTES:
            raise RejectCommand(
                code="artifact_too_large",
                detail="O conteúdo aprovado excede o limite seguro.",
            )
        artifact_hash = hashlib.sha256(artifact_bytes).hexdigest()
        if authorization is not None:
            from shopman.shop.services.marketing_security import (
                ACTION_APPROVE,
                authorization_context,
            )

            authorization(
                authorization_context(
                    action=ACTION_APPROVE,
                    resource_ref=f"announcement:{announcement.pk}",
                    base_version=announcement.version,
                    artifact_hash=artifact_hash,
                    audience_hash=resolution.cohort_hash,
                    audience_count=resolution.total,
                    platforms=safe_platforms,
                    scheduled_for=normalized_publish_at,
                    consequence=(
                        "publishes_now_to_eligible_audience"
                        if normalized_mode == PUBLISH_NOW
                        else "schedules_publish_to_eligible_audience"
                    ),
                ),
                receipt,
            )
        artifact = MarketingContentArtifact.objects.create(
            announcement=announcement,
            version=approved_version,
            schema_version=marketing_artifacts.SCHEMA_VERSION,
            payload=artifact_payload,
            artifact_hash=artifact_hash,
            retention_until=now + APPROVAL_RECORD_RETENTION,
        )

        try:
            snapshot = audience_snapshot.create_snapshot(
                resolution,
                rules=rules,
                announcement=announcement,
                version=approved_version,
                now=now,
            )
        except MarketingContractError as exc:
            raise RejectCommand(
                code=exc.code,
                detail=exc.detail,
                outcome={"current_version": exc.current_version},
                field_errors=exc.field_errors,
            ) from exc

        available_at = normalized_publish_at or now
        outbox = _create_outbox(
            receipt=receipt,
            announcement=announcement,
            snapshot=snapshot,
            artifact=artifact,
            platforms=safe_platforms,
            resolution=resolution,
            available_at=available_at,
            now=now,
        )
        if announcement.expires_at is not None:
            expires_late = [row for row in outbox if row.available_at >= announcement.expires_at]
            if expires_late:
                raise RejectCommand(
                    code="delivery_wave_after_expiry",
                    detail="Uma etapa da entrega aconteceria depois da expiração.",
                    outcome={
                        "expires_at": announcement.expires_at.isoformat(),
                        "late_wave_count": len(expires_late),
                    },
                    field_errors={
                        "publish_at": ("Antecipe o horário ou amplie o prazo de revisão.",),
                    },
                )
        quiet_rows = [
            row
            for row in outbox
            if row.platform == "whatsapp"
            and not marketing_time.delivery_window(
                row.available_at,
                timezone_name=effective_timezone,
            ).allowed
        ]
        if quiet_rows:
            raise RejectCommand(
                code="delivery_wave_in_quiet_hours",
                detail="Uma etapa do WhatsApp cairia no período de silêncio.",
                outcome={"quiet_wave_count": len(quiet_rows)},
                field_errors={
                    "publish_at": ("Antecipe o horário para concluir antes das 20:00.",),
                },
            )

        announcement.content = approved_content
        announcement.platform_content = safe_platform_content
        announcement.platforms = safe_platforms
        announcement.audience = resolution.summary()
        announcement.approved_by_id = receipt.actor_id
        announcement.approved_at = now
        announcement.publish_at = normalized_publish_at
        announcement.status = (
            AnnouncementStatus.APPROVED if normalized_mode == PUBLISH_SCHEDULED else AnnouncementStatus.PUBLISHING
        )
        announcement.save(
            update_fields=[
                "content",
                "platform_content",
                "platforms",
                "audience",
                "approved_by",
                "approved_at",
                "publish_at",
                "status",
            ]
        )

        MarketingAuditEvent.objects.create(
            event_type=MarketingAuditEvent.EventType.APPROVED,
            command=receipt,
            announcement=announcement,
            actor_id=receipt.actor_id,
            actor_ref=receipt.actor_ref,
            snapshot=snapshot,
            artifact=artifact,
            base_version=announcement.version,
            resulting_version=approved_version,
            facts={
                "audience_count": resolution.total,
                "outbox_count": len(outbox),
                "platform_count": len(safe_platforms),
                "publish_at": normalized_publish_at.isoformat() if normalized_publish_at else "",
                "publish_mode": normalized_mode,
                "publish_timezone": effective_timezone,
            }
            | (
                {
                    "facts_as_of": facts.as_of.isoformat(),
                    "facts_hash": facts.source_hash,
                }
                if facts is not None
                else {}
            ),
            request_id=receipt.request_id,
            occurred_at=now,
            retention_until=now + APPROVAL_RECORD_RETENTION,
        )
        if ai_trace is not None:
            from shopman.shop.services import marketing_ai

            suggestion, event_type, result_hash, diff_fields = ai_trace
            marketing_ai.record_approval(
                suggestion=suggestion,
                event_type=event_type,
                result_hash=result_hash,
                diff_fields=diff_fields,
                actor=actor,
                command=receipt,
                now=now,
            )
        return {
            "audience_count": resolution.total,
            "artifact_hash": artifact.artifact_hash,
            "artifact_ref": str(artifact.ref),
            "outbox_count": len(outbox),
            "platforms": list(safe_platforms),
            "publish_at": normalized_publish_at.isoformat() if normalized_publish_at else "",
            "publish_mode": normalized_mode,
            "publish_timezone": effective_timezone,
            "effective_at": available_at.isoformat(),
            "snapshot_ref": str(snapshot.ref),
            "status": announcement.status,
        }

    execution = execute_announcement_command(
        kind=MarketingCommandReceipt.Kind.APPROVE,
        announcement_id=announcement_id,
        actor=actor,
        idempotency_key=idempotency_key,
        base_version=base_version,
        payload=fingerprint_payload,
        operation=operation,
        request_id=request_id,
    )
    return _result(execution)


def canonical_artifact_bytes(payload: Mapping[str, Any]) -> bytes:
    """One byte contract shared by persistence tests and the future dispatcher."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _result(execution: CommandExecution) -> ApprovalResult:
    receipt = execution.receipt
    announcement = execution.announcement
    if announcement is None or receipt.resulting_version is None:
        raise RuntimeError("A completed approval receipt has no resulting resource version.")
    artifact = MarketingContentArtifact.objects.get(
        announcement=announcement,
        version=receipt.resulting_version,
    )
    snapshot = AudienceSnapshot.objects.get(
        announcement=announcement,
        version=receipt.resulting_version,
    )
    outbox = tuple(MarketingOutbox.objects.filter(command=receipt).order_by("available_at", "pk"))
    return ApprovalResult(
        announcement=announcement,
        receipt=receipt,
        artifact=artifact,
        snapshot=snapshot,
        outbox=outbox,
        replayed=execution.replayed,
    )


def _create_outbox(
    *,
    receipt: MarketingCommandReceipt,
    announcement: Announcement,
    snapshot: AudienceSnapshot,
    artifact: MarketingContentArtifact,
    platforms: list[str],
    resolution,
    available_at: datetime,
    now: datetime,
) -> tuple[MarketingOutbox, ...]:
    entries: list[MarketingOutbox] = []
    for platform in platforms:
        waves = resolution.waves(now=timezone.localtime(now)) if platform == "whatsapp" else ()
        if not waves:
            entries.append(
                MarketingOutbox(
                    command=receipt,
                    announcement=announcement,
                    snapshot=snapshot,
                    artifact=artifact,
                    platform=platform,
                    available_at=available_at,
                )
            )
            continue
        for wave in waves:
            entries.append(
                MarketingOutbox(
                    command=receipt,
                    announcement=announcement,
                    snapshot=snapshot,
                    artifact=artifact,
                    platform=platform,
                    wave_key=wave.key,
                    available_at=available_at + timedelta(minutes=wave.delay_minutes),
                )
            )
    MarketingOutbox.objects.bulk_create(entries)
    return tuple(entries)


def _audience_rules(announcement: Announcement) -> dict[str, Any]:
    chosen = (announcement.trigger_context or {}).get("audience_rules")
    if isinstance(chosen, dict) and chosen:
        return dict(chosen)
    if announcement.rule_id:
        return dict(announcement.rule.audience_rules or {})
    return {}


def normalize_schedule(
    publish_mode: str,
    *,
    publish_at: datetime | None,
    now: datetime,
) -> tuple[str, datetime | None]:
    mode = str(publish_mode or "").strip()
    if mode not in PUBLISH_MODES:
        raise MarketingContractError(
            code="invalid_publish_mode",
            detail="Escolha publicar agora ou agendar.",
            field_errors={"publish_mode": ("Use 'now' ou 'scheduled'.",)},
        )
    if mode == PUBLISH_NOW:
        if publish_at is not None:
            raise MarketingContractError(
                code="publish_now_has_schedule",
                detail="Publicar agora não aceita uma data de agendamento.",
                field_errors={"publish_at": ("Remova a data ou escolha agendar.",)},
            )
        return mode, None
    if publish_at is None:
        raise MarketingContractError(
            code="scheduled_publish_at_required",
            detail="Escolha a data e hora do agendamento.",
            field_errors={"publish_at": ("Este campo é obrigatório para agendar.",)},
        )
    if timezone.is_naive(publish_at):
        raise MarketingContractError(
            code="scheduled_publish_at_naive",
            detail="A data agendada precisa incluir timezone.",
            field_errors={"publish_at": ("Inclua o offset do horário.",)},
        )
    if publish_at <= now:
        raise MarketingContractError(
            code="scheduled_publish_at_past",
            detail="A data agendada precisa estar no futuro.",
            field_errors={"publish_at": ("Escolha um horário futuro.",)},
        )
    return mode, publish_at


def _publish_timezone(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    try:
        return marketing_time.require_configured_timezone(candidate)
    except ValueError as exc:
        code = str(exc)
        raise MarketingContractError(
            code=code,
            detail=(
                "O timezone não corresponde ao configurado para a loja."
                if code == "timezone_mismatch"
                else "O timezone informado não existe."
            ),
            field_errors={"publish_timezone": ("Recarregue o horário da loja.",)},
        ) from exc


def _json_copy(value: Mapping[str, Any], *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MarketingContractError(
            code="invalid_approval_content",
            detail=f"{field} deve ser um objeto JSON.",
            field_errors={field: ("Envie o objeto completo.",)},
        )
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise MarketingContractError(
            code="invalid_approval_content",
            detail=f"{field} contém um valor inválido.",
            field_errors={field: ("Use somente valores JSON.",)},
        ) from exc


def _platforms(platforms: Sequence[str]) -> list[str]:
    if isinstance(platforms, str) or not isinstance(platforms, Sequence):
        raise MarketingContractError(
            code="invalid_platforms",
            detail="Plataformas devem ser uma lista.",
            field_errors={"platforms": ("Envie uma lista de plataformas.",)},
        )
    normalized = [str(item).strip() for item in platforms if str(item).strip()]
    if not normalized:
        raise MarketingContractError(
            code="platform_required",
            detail="Escolha ao menos uma plataforma.",
            field_errors={"platforms": ("Escolha ao menos uma plataforma.",)},
        )
    if len(normalized) != len(set(normalized)):
        raise MarketingContractError(
            code="duplicate_platform",
            detail="Uma plataforma foi escolhida mais de uma vez.",
            field_errors={"platforms": ("Remova a plataforma duplicada.",)},
        )
    unknown = sorted(set(normalized) - _PLATFORMS)
    if unknown:
        raise MarketingContractError(
            code="unknown_platform",
            detail="Há uma plataforma desconhecida.",
            field_errors={"platforms": (f"Não reconhecida: {', '.join(unknown)}.",)},
        )
    return normalized


def _validate_content(
    content: dict[str, Any],
    platform_content: dict[str, Any],
    platforms: list[str],
) -> None:
    if not str(content.get("body") or "").strip():
        raise MarketingContractError(
            code="body_required",
            detail="O texto do anúncio não pode ficar vazio.",
            field_errors={"content.body": ("Revise o texto antes de aprovar.",)},
        )
    unknown_variants = sorted(set(platform_content) - set(platforms))
    if unknown_variants:
        raise MarketingContractError(
            code="orphan_platform_content",
            detail="Existe conteúdo para uma plataforma que não foi escolhida.",
            field_errors={
                "platform_content": (f"Remova as variantes de: {', '.join(unknown_variants)}.",),
            },
        )
    if not all(isinstance(value, Mapping) for value in platform_content.values()):
        raise MarketingContractError(
            code="invalid_platform_content",
            detail="Cada variante de plataforma deve ser um objeto.",
            field_errors={"platform_content": ("Revise as variantes.",)},
        )
