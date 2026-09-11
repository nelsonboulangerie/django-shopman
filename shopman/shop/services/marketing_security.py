"""Transactional authorization, quotas and emergency freeze for Marketing.

The browser never chooses the policy or computes a security hash.  A dangerous
command first reaches its normal server-side validation and, before any write,
produces an exact consequence context.  The short-lived token issued for that
context is consumed inside the command transaction after permissions and
step-up evidence have been checked again.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from shopman.shop.models import (
    MarketingCommandReceipt,
    MarketingConfirmation,
    MarketingQuotaUsage,
    MarketingSafetyState,
    MarketingSecurityEvent,
)
from shopman.shop.services.marketing_contracts import MarketingContractError

CONFIRMATION_TTL = timedelta(minutes=5)
STEP_UP_TTL = timedelta(minutes=15)
SECURITY_RETENTION = timedelta(days=365 * 5)
MAX_EXTERNAL_TARGETS_PER_DAY = 5_000
MAX_BLAST = 5_000
MIN_LARGE_SCHEDULE_DELAY = timedelta(minutes=15)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ACTION_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_SAFE_CAPABILITY_RE = re.compile(r"^shop\.[a-z0-9_]{1,59}$")
_SAFE_RESOURCE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}:[A-Za-z0-9._:-]{1,87}$")
_SAFE_CONSEQUENCE_RE = re.compile(r"^[a-z0-9_]{1,64}$")
logger = logging.getLogger(__name__)

ACTION_APPROVE = "approve"
ACTION_FIRE = "fire"
ACTION_CANCEL = "cancel"
ACTION_RESCHEDULE = "reschedule"
ACTION_RETRY = "retry_delivery"
ACTION_RECONCILE = "reconcile_delivery"
ACTION_UNFREEZE = "unfreeze"
ACTION_CONFIGURE_PLATFORM = "configure_platform"


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    action: str
    resource_ref: str
    base_version: int
    artifact_hash: str = ""
    audience_hash: str = ""
    audience_count: int = 0
    platforms: tuple[str, ...] = ()
    scheduled_for: datetime | None = None
    consequence: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "artifact_hash": self.artifact_hash,
            "audience_count": self.audience_count,
            "audience_hash": self.audience_hash,
            "base_version": self.base_version,
            "consequence": self.consequence,
            "platforms": list(self.platforms),
            "resource_ref": self.resource_ref,
            "scheduled_for": (
                self.scheduled_for.isoformat() if self.scheduled_for is not None else ""
            ),
        }


@dataclass(frozen=True, slots=True)
class AuthorizationRequirement:
    confirmation_mode: str
    step_up_level: str
    dual_control: bool
    typed_phrase: str


@dataclass(frozen=True, slots=True)
class StepUpEvidence:
    actor_id: int = 0
    level: str = ""
    verified_at: datetime | None = None
    auth_hash: str = ""
    permission_fingerprint: str = ""
    safety_generation: int = 0


class MarketingAuthorizationError(MarketingContractError):
    """A precondition failed without creating or consuming a command receipt."""

    def __init__(
        self,
        *,
        code: str,
        detail: str,
        status_code: int,
        retry_after: int | None = None,
        field_errors: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__(
            code=code,
            detail=detail,
            retryable=status_code == 429,
            field_errors=field_errors or {},
        )
        self.status_code = status_code
        self.retry_after = retry_after


class MarketingAuthorizationRequired(Exception):
    """Carries a context computed by the server; issuing the token happens later."""

    def __init__(
        self,
        *,
        actor_id: int,
        capability: str,
        additional_capabilities: tuple[str, ...],
        context: AuthorizationContext,
        requirement: AuthorizationRequirement,
    ) -> None:
        super().__init__("Marketing confirmation required")
        self.actor_id = actor_id
        self.capability = capability
        self.additional_capabilities = additional_capabilities
        self.context = context
        self.requirement = requirement


def authorization_context(
    *,
    action: str,
    resource_ref: str,
    base_version: int,
    artifact_hash: str = "",
    audience_hash: str = "",
    audience_count: int = 0,
    platforms: Sequence[str] = (),
    scheduled_for: datetime | None = None,
    consequence: str,
) -> AuthorizationContext:
    safe_action = str(action or "").strip()
    safe_resource = str(resource_ref or "").strip()
    safe_artifact_hash = str(artifact_hash or "").strip()
    safe_audience_hash = str(audience_hash or "").strip()
    safe_consequence = str(consequence or "").strip()
    if not _SAFE_ACTION_RE.fullmatch(safe_action):
        raise ValueError("invalid Marketing authorization action")
    if not _SAFE_RESOURCE_RE.fullmatch(safe_resource):
        raise ValueError("invalid Marketing authorization resource")
    if isinstance(base_version, bool) or int(base_version) < 1:
        raise ValueError("invalid Marketing authorization version")
    if safe_artifact_hash and not _HASH_RE.fullmatch(safe_artifact_hash):
        raise ValueError("invalid Marketing artifact hash")
    if safe_audience_hash and not _HASH_RE.fullmatch(safe_audience_hash):
        raise ValueError("invalid Marketing audience hash")
    if not _SAFE_CONSEQUENCE_RE.fullmatch(safe_consequence):
        raise ValueError("invalid Marketing consequence")
    if isinstance(audience_count, bool) or int(audience_count) < 0:
        raise ValueError("invalid Marketing audience count")
    safe_platforms = tuple(sorted({str(value).strip() for value in platforms if str(value).strip()}))
    if any(not _SAFE_ACTION_RE.fullmatch(value) for value in safe_platforms):
        raise ValueError("invalid Marketing platform")
    if scheduled_for is not None and timezone.is_naive(scheduled_for):
        raise ValueError("Marketing schedule must include timezone")
    return AuthorizationContext(
        action=safe_action,
        resource_ref=safe_resource,
        base_version=int(base_version),
        artifact_hash=safe_artifact_hash,
        audience_hash=safe_audience_hash,
        audience_count=int(audience_count),
        platforms=safe_platforms,
        scheduled_for=scheduled_for,
        consequence=safe_consequence,
    )


def requirement_for(context: AuthorizationContext, *, now: datetime | None = None) -> AuthorizationRequirement:
    clock = _aware_now(now)
    # Uma consequência pública tem um destino por plataforma mesmo quando não
    # existe audiência de mensagens diretas. O número digitado deve descrever o
    # efeito real; "PUBLICAR 0" para um Story é uma confirmação enganosa.
    count = _external_target_count(context)
    if count > MAX_BLAST:
        raise MarketingAuthorizationError(
            code="marketing_blast_limit_exceeded",
            detail=f"O limite aprovado é {MAX_BLAST} destinos por comando.",
            status_code=422,
            field_errors={"audience_count": ("Divida ou reduza a audiência.",)},
        )
    if context.action == ACTION_RECONCILE:
        return AuthorizationRequirement("summary", "totp", False, "")
    if context.action == ACTION_CONFIGURE_PLATFORM:
        return AuthorizationRequirement("summary", "totp", False, "")
    if context.action == ACTION_UNFREEZE:
        return AuthorizationRequirement("summary", "totp", True, "")

    immediate = context.scheduled_for is None and context.action in {
        ACTION_APPROVE,
        ACTION_FIRE,
        ACTION_RETRY,
    }
    if count >= 2_000:
        if immediate:
            raise MarketingAuthorizationError(
                code="large_blast_must_be_scheduled",
                detail="A partir de 2.000 destinos, o envio precisa ser agendado.",
                status_code=422,
            )
        assert context.scheduled_for is not None
        if context.scheduled_for < clock + MIN_LARGE_SCHEDULE_DELAY:
            raise MarketingAuthorizationError(
                code="large_blast_schedule_too_soon",
                detail="Agende com pelo menos 15 minutos de antecedência.",
                status_code=422,
            )
    if immediate or count >= 50:
        level = "totp" if count >= 500 else "password"
        return AuthorizationRequirement(
            "typed",
            level,
            count >= 500,
            f"PUBLICAR {count}",
        )
    return AuthorizationRequirement("summary", "none", False, "")


def authorize_command(
    *,
    actor,
    capability: str,
    additional_capabilities: Sequence[str] = (),
    context: AuthorizationContext,
    token: str,
    typed_confirmation: str = "",
    step_up: StepUpEvidence | None = None,
    command: MarketingCommandReceipt | None = None,
    now: datetime | None = None,
) -> MarketingConfirmation:
    """Consume one exact token inside the caller's transaction."""

    clock = _aware_now(now)
    safe_capability = _capability(capability)
    safe_additional = tuple(_capability(value) for value in additional_capabilities)
    actor_row = _fresh_actor(actor)
    state = safety_state(for_update=True)
    _require_capability(actor_row, safe_capability)
    for required_capability in safe_additional:
        _require_capability(actor_row, required_capability)
    # Lookup-only reconciliation is what lets Security prove that an unknown
    # effect is safe before unfreezing.  It cannot send/retry and therefore
    # remains available while all effect-creating commands stay blocked.
    if state.frozen and context.action not in {ACTION_RECONCILE, ACTION_UNFREEZE}:
        raise MarketingAuthorizationError(
            code="marketing_frozen",
            detail="Marketing está congelado; nenhum novo efeito externo foi autorizado.",
            status_code=423,
        )
    requirement = requirement_for(context, now=clock)
    raw_token = str(token or "").strip()
    if not raw_token:
        raise MarketingAuthorizationRequired(
            actor_id=actor_row.pk,
            capability=safe_capability,
            additional_capabilities=safe_additional,
            context=context,
            requirement=requirement,
        )
    confirmation = (
        MarketingConfirmation.objects.select_for_update()
        .filter(token_hash=_token_hash(raw_token))
        .first()
    )
    if confirmation is None:
        _denied("confirmation_invalid", actor_row, context)
        raise MarketingAuthorizationError(
            code="confirmation_invalid",
            detail="A confirmação não existe. Revise o resumo novamente.",
            status_code=422,
        )
    expected_context_hash = _context_hash(context)
    if (
        confirmation.actor_id != actor_row.pk
        or confirmation.action != context.action
        or confirmation.capability != safe_capability
        or confirmation.resource_ref != context.resource_ref
        or confirmation.base_version != context.base_version
        or not hmac.compare_digest(confirmation.context_hash, expected_context_hash)
    ):
        _denied("confirmation_context_changed", actor_row, context, confirmation=confirmation)
        raise MarketingAuthorizationError(
            code="confirmation_context_changed",
            detail="O conteúdo, público, horário ou versão mudou. Revise o novo resumo.",
            status_code=409,
        )
    if confirmation.consumed_at is not None:
        raise MarketingAuthorizationError(
            code="confirmation_already_used",
            detail="Esta confirmação já foi usada.",
            status_code=409,
        )
    if confirmation.expires_at <= clock:
        raise MarketingAuthorizationError(
            code="confirmation_expired",
            detail="A confirmação expirou. Revise o resumo novamente.",
            status_code=422,
        )
    current_fingerprint = permission_fingerprint(actor_row, state=state)
    if (
        confirmation.freeze_generation != state.generation
        or not hmac.compare_digest(confirmation.permission_fingerprint, current_fingerprint)
    ):
        _denied("authorization_changed", actor_row, context, confirmation=confirmation)
        raise MarketingAuthorizationError(
            code="authorization_changed",
            detail="Sua autorização mudou desde que a ação foi aberta. Atualize a tela.",
            status_code=403,
        )
    _require_step_up(actor_row, requirement.step_up_level, step_up, state=state, now=clock)
    if requirement.typed_phrase and not hmac.compare_digest(
        str(typed_confirmation or "").strip(), requirement.typed_phrase
    ):
        raise MarketingAuthorizationError(
            code="typed_confirmation_mismatch",
            detail="Digite exatamente a frase mostrada no resumo.",
            status_code=422,
            field_errors={"typed_confirmation": (requirement.typed_phrase,)},
        )
    if confirmation.dual_control:
        _require_second_actor(confirmation, context=context, now=clock)
    _reserve_external_quota(actor_row, context=context, now=clock)
    confirmation.consumed_at = clock
    confirmation.command = command
    confirmation.save(update_fields=["consumed_at", "command"])
    _event(
        "confirmation_consumed",
        actor=actor_row,
        second_actor=confirmation.second_actor,
        confirmation=confirmation,
        context=context,
        facts={"audience_bucket": _audience_bucket(context.audience_count)},
        now=clock,
    )
    return confirmation


def issue_confirmation(
    required: MarketingAuthorizationRequired,
    *,
    actor,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist and return a fresh bearer once the command transaction rolled back."""

    clock = _aware_now(now)
    if getattr(actor, "pk", None) != required.actor_id:
        raise MarketingAuthorizationError(
            code="confirmation_actor_changed",
            detail="A pessoa da sessão mudou. Atualize a tela.",
            status_code=403,
        )
    raw_token = secrets.token_urlsafe(32)
    with transaction.atomic():
        actor_row = _fresh_actor(actor, for_update=True)
        state = safety_state(for_update=True)
        _require_capability(actor_row, required.capability)
        for required_capability in required.additional_capabilities:
            _require_capability(actor_row, required_capability)
        if state.frozen and required.context.action not in {
            ACTION_RECONCILE,
            ACTION_UNFREEZE,
        }:
            raise MarketingAuthorizationError(
                code="marketing_frozen",
                detail="Marketing está congelado; nenhum novo efeito externo foi autorizado.",
                status_code=423,
            )
        confirmation = MarketingConfirmation.objects.create(
            token_hash=_token_hash(raw_token),
            actor=actor_row,
            action=required.context.action,
            capability=required.capability,
            resource_ref=required.context.resource_ref,
            base_version=required.context.base_version,
            context_hash=_context_hash(required.context),
            artifact_hash=required.context.artifact_hash,
            audience_hash=required.context.audience_hash,
            audience_count=required.context.audience_count,
            platforms=list(required.context.platforms),
            scheduled_for=required.context.scheduled_for,
            consequence=required.context.consequence,
            confirmation_mode=required.requirement.confirmation_mode,
            step_up_level=required.requirement.step_up_level,
            dual_control=required.requirement.dual_control,
            permission_fingerprint=permission_fingerprint(actor_row, state=state),
            freeze_generation=state.generation,
            expires_at=clock + CONFIRMATION_TTL,
            retention_until=clock + SECURITY_RETENTION,
        )
        _event(
            "confirmation_issued",
            actor=actor_row,
            confirmation=confirmation,
            context=required.context,
            facts={"audience_bucket": _audience_bucket(required.context.audience_count)},
            now=clock,
        )
    return {
        "code": "confirmation_required",
        "detail": "Confira o resumo e confirme esta consequência.",
        "confirmation": {
            "token": raw_token,
            "ref": str(confirmation.ref),
            "expires_at": confirmation.expires_at.isoformat(),
            "mode": confirmation.confirmation_mode,
            "step_up": confirmation.step_up_level,
            "dual_control": confirmation.dual_control,
            "typed_phrase": required.requirement.typed_phrase,
            "consequence": required.context.consequence,
            "resource_ref": required.context.resource_ref,
            "base_version": required.context.base_version,
            "audience_count": required.context.audience_count,
            "platforms": list(required.context.platforms),
            "scheduled_for": (
                required.context.scheduled_for.isoformat()
                if required.context.scheduled_for is not None
                else ""
            ),
        },
    }


def approve_second_actor(
    raw_token: str,
    *,
    actor,
    step_up: StepUpEvidence | None,
    now: datetime | None = None,
) -> MarketingConfirmation:
    clock = _aware_now(now)
    with transaction.atomic():
        second = _fresh_actor(actor, for_update=True)
        state = safety_state(for_update=True)
        confirmation = (
            MarketingConfirmation.objects.select_for_update()
            .filter(token_hash=_token_hash(str(raw_token or "").strip()))
            .first()
        )
        if confirmation is None or not confirmation.dual_control:
            raise MarketingAuthorizationError(
                code="dual_control_unavailable",
                detail="Esta confirmação não aceita segundo controle.",
                status_code=422,
            )
        if confirmation.actor_id == second.pk:
            raise MarketingAuthorizationError(
                code="dual_control_same_actor",
                detail="O segundo controle precisa ser feito por outra pessoa.",
                status_code=403,
            )
        if confirmation.consumed_at is not None or confirmation.expires_at <= clock:
            raise MarketingAuthorizationError(
                code="confirmation_expired",
                detail="A confirmação não está mais aberta.",
                status_code=422,
            )
        if confirmation.freeze_generation != state.generation:
            raise MarketingAuthorizationError(
                code="authorization_changed",
                detail="A autorização mudou. Gere um novo resumo.",
                status_code=403,
            )
        _require_any_capability(second, _second_actor_capabilities(confirmation.action))
        _require_step_up(second, "totp", step_up, state=state, now=clock)
        confirmation.second_actor = second
        confirmation.second_approved_at = clock
        confirmation.second_permission_fingerprint = permission_fingerprint(
            second, state=state
        )
        confirmation.save(
            update_fields=[
                "second_actor",
                "second_approved_at",
                "second_permission_fingerprint",
            ]
        )
        _event(
            "dual_control_approved",
            actor=confirmation.actor,
            second_actor=second,
            confirmation=confirmation,
            context=_context_from_confirmation(confirmation),
            now=clock,
        )
        return confirmation


def activate_freeze(*, actor, reason: str, now: datetime | None = None) -> MarketingSafetyState:
    clock = _aware_now(now)
    normalized_reason = _required_reason(reason)
    with transaction.atomic():
        actor_row = _fresh_actor(actor, for_update=True)
        _require_capability(actor_row, "shop.freeze_marketing")
        state = safety_state(for_update=True)
        if state.frozen:
            _suppress_reversible_work(now=clock)
            return state
        state.frozen = True
        state.reason = normalized_reason
        state.frozen_by = actor_row
        state.frozen_at = clock
        state.generation += 1
        state.version += 1
        state.save(update_fields=[
            "frozen",
            "reason",
            "frozen_by",
            "frozen_at",
            "generation",
            "version",
            "updated_at",
        ])
        suppressed = _suppress_reversible_work(now=clock)
        _event(
            "freeze_activated",
            actor=actor_row,
            action="freeze",
            resource_ref="marketing:default",
            reason_code="operator_emergency_freeze",
            facts={
                "reason_hash": _plain_hash(normalized_reason),
                **suppressed,
            },
            now=clock,
        )
        return state


def deactivate_freeze(
    *,
    actor,
    base_version: int,
    token: str,
    step_up: StepUpEvidence | None,
    now: datetime | None = None,
) -> MarketingSafetyState:
    clock = _aware_now(now)
    with transaction.atomic():
        state = safety_state(for_update=True)
        if not state.frozen:
            return state
        if state.version != base_version:
            raise MarketingAuthorizationError(
                code="version_conflict",
                detail="O estado do congelamento mudou. Atualize o resumo.",
                status_code=409,
            )
        from shopman.shop.models import DeliveryAttempt, DeliveryReconciliation, DeliveryTarget

        unresolved = {
            "calling": DeliveryAttempt.objects.filter(
                state=DeliveryAttempt.State.CALLING
            ).count(),
            "reconciliation_pending": DeliveryReconciliation.objects.filter(
                state__in=(
                    DeliveryReconciliation.State.PENDING,
                    DeliveryReconciliation.State.CLAIMED,
                )
            ).count(),
            "unknown": DeliveryTarget.objects.filter(
                state=DeliveryTarget.State.UNKNOWN
            ).count(),
        }
        if any(unresolved.values()):
            raise MarketingAuthorizationError(
                code="freeze_reconciliation_required",
                detail="Reconcilie os efeitos em andamento antes de reativar Marketing.",
                status_code=409,
            )
        suppressed = _suppress_reversible_work(now=clock)
        context = authorization_context(
            action=ACTION_UNFREEZE,
            resource_ref="marketing:default",
            base_version=base_version,
            consequence="resumes_external_effects_after_reconciliation",
        )
        confirmation = authorize_command(
            actor=actor,
            capability="shop.freeze_marketing",
            context=context,
            token=token,
            step_up=step_up,
            now=clock,
        )
        state.frozen = False
        state.reason = ""
        state.frozen_by = None
        state.frozen_at = None
        state.generation += 1
        state.version += 1
        state.save(update_fields=[
            "frozen",
            "reason",
            "frozen_by",
            "frozen_at",
            "generation",
            "version",
            "updated_at",
        ])
        _event(
            "freeze_deactivated",
            actor=confirmation.actor,
            second_actor=confirmation.second_actor,
            confirmation=confirmation,
            context=context,
            reason_code="dual_control_reconciled",
            facts=suppressed,
            now=clock,
        )
        return state


def require_external_effects_enabled() -> None:
    if MarketingSafetyState.objects.filter(scope="default", frozen=True).exists():
        raise MarketingAuthorizationError(
            code="marketing_frozen",
            detail="Marketing está congelado; o efeito externo permanece em espera.",
            status_code=423,
        )


def safety_state(*, for_update: bool = False) -> MarketingSafetyState:
    query = MarketingSafetyState.objects
    if for_update:
        query = query.select_for_update()
    state = query.filter(scope="default").first()
    if state is not None:
        return state
    try:
        with transaction.atomic():
            return MarketingSafetyState.objects.create(scope="default")
    except IntegrityError:
        return query.get(scope="default")


def _suppress_reversible_work(*, now: datetime) -> dict[str, int]:
    """Terminally suppress work that has not crossed an external boundary."""

    from shopman.orderman.models import Directive

    from shopman.shop.directives import ANNOUNCEMENT_NOTIFY, ANNOUNCEMENT_PUBLISH
    from shopman.shop.models import DeliveryTarget, MarketingOutbox
    from shopman.shop.services.marketing_delivery_aggregate import (
        schedule_delivery_refresh,
    )

    outboxes = MarketingOutbox.objects.filter(
        state__in=(MarketingOutbox.State.PENDING, MarketingOutbox.State.CLAIMED)
    )
    announcement_ids = set(outboxes.values_list("announcement_id", flat=True))
    cancelled_outboxes = outboxes.update(
        state=MarketingOutbox.State.CANCELLED,
        lease_owner="",
        lease_until=None,
        last_error_code="marketing_frozen",
        cancelled_at=now,
        updated_at=now,
    )

    targets = DeliveryTarget.objects.filter(
        state__in=(
            DeliveryTarget.State.PLANNED,
            DeliveryTarget.State.QUEUED,
            DeliveryTarget.State.FAILED_RETRYABLE,
        )
    )
    announcement_ids.update(targets.values_list("announcement_id", flat=True))
    cancelled_targets = targets.update(
        state=DeliveryTarget.State.CANCELLED,
        lease_owner="",
        lease_until=None,
        last_error_code="marketing_frozen",
        settled_at=now,
        version=F("version") + 1,
        updated_at=now,
    )
    cancelled_directives = Directive.objects.filter(
        topic__in=(ANNOUNCEMENT_NOTIFY, ANNOUNCEMENT_PUBLISH),
        status=Directive.Status.QUEUED,
    ).update(
        status=Directive.Status.FAILED,
        error_code="marketing_frozen",
        last_error="Marketing emergency freeze suppressed this reversible effect.",
        updated_at=now,
    )
    for announcement_id in announcement_ids:
        schedule_delivery_refresh(announcement_id)
    return {
        "suppressed_directive_count": cancelled_directives,
        "suppressed_outbox_count": cancelled_outboxes,
        "suppressed_target_count": cancelled_targets,
    }


def permission_fingerprint(actor, *, state: MarketingSafetyState | None = None) -> str:
    current_state = state or safety_state()
    permissions = sorted(actor.get_all_permissions())
    canonical = json.dumps(
        {
            "actor_id": actor.pk,
            "auth_hash": actor.get_session_auth_hash(),
            "generation": current_state.generation,
            "permissions": permissions,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return _keyed_hash("permission", canonical)


def step_up_evidence_from_session(request) -> StepUpEvidence:
    raw = request.session.get("marketing_step_up") or {}
    verified_at = None
    try:
        verified_at = datetime.fromisoformat(str(raw.get("verified_at") or ""))
        if timezone.is_naive(verified_at):
            verified_at = None
    except (TypeError, ValueError):
        verified_at = None
    return StepUpEvidence(
        actor_id=int(raw.get("actor_id") or 0),
        level=str(raw.get("level") or ""),
        verified_at=verified_at,
        auth_hash=str(raw.get("auth_hash") or ""),
        permission_fingerprint=str(raw.get("permission_fingerprint") or ""),
        safety_generation=int(raw.get("safety_generation") or 0),
    )


def record_step_up(request, *, level: str, now: datetime | None = None) -> dict[str, str]:
    clock = _aware_now(now)
    actor = _fresh_actor(request.user)
    state = safety_state()
    safe_level = str(level or "")
    if safe_level not in {"password", "totp"}:
        raise ValueError("invalid step-up level")
    request.session["marketing_step_up"] = {
        "actor_id": actor.pk,
        "level": safe_level,
        "verified_at": clock.isoformat(),
        "auth_hash": actor.get_session_auth_hash(),
        "permission_fingerprint": permission_fingerprint(actor, state=state),
        "safety_generation": state.generation,
    }
    request.session.modified = True
    _event(
        "step_up_succeeded",
        actor=actor,
        action="step_up",
        resource_ref="marketing:default",
        reason_code=safe_level,
        now=clock,
    )
    return {"level": safe_level, "expires_at": (clock + STEP_UP_TTL).isoformat()}


def bump_authority_generation() -> None:
    """Invalidate open tokens and step-up evidence after any RBAC membership edit."""

    with transaction.atomic():
        state = safety_state(for_update=True)
        state.generation += 1
        state.save(update_fields=["generation", "updated_at"])


def record_security_denial(
    *,
    actor,
    reason_code: str,
    action: str = "capability_gate",
) -> None:
    """Best-effort durable evidence for denials outside command transactions."""

    try:
        _event(
            "authorization_denied",
            actor=actor if getattr(actor, "pk", None) else None,
            action=action if _SAFE_ACTION_RE.fullmatch(action) else "capability_gate",
            resource_ref="marketing:default",
            reason_code=(
                reason_code if _SAFE_CONSEQUENCE_RE.fullmatch(reason_code) else "denied"
            ),
            now=timezone.now(),
        )
    except Exception:
        logger.debug("marketing.security_evidence_store_unavailable")
        # Authorization must remain fail-closed even before/while the additive
        # evidence migration is being applied.
        return


def _require_step_up(
    actor,
    required: str,
    evidence: StepUpEvidence | None,
    *,
    state: MarketingSafetyState,
    now: datetime,
) -> None:
    if required == "none":
        return
    evidence = evidence or StepUpEvidence()
    levels = {"password": 1, "totp": 2}
    valid = (
        evidence.actor_id == actor.pk
        and evidence.verified_at is not None
        and evidence.verified_at >= now - STEP_UP_TTL
        and evidence.level in levels
        and levels[evidence.level] >= levels[required]
        and hmac.compare_digest(evidence.auth_hash, actor.get_session_auth_hash())
        and evidence.safety_generation == state.generation
        and hmac.compare_digest(
            evidence.permission_fingerprint,
            permission_fingerprint(actor, state=state),
        )
    )
    if not valid:
        raise MarketingAuthorizationError(
            code="step_up_required",
            detail=(
                "Confirme com o aplicativo autenticador."
                if required == "totp"
                else "Confirme novamente com sua senha."
            ),
            status_code=403,
            field_errors={"step_up": (required,)},
        )


def _reserve_external_quota(actor, *, context: AuthorizationContext, now: datetime) -> None:
    if context.action in {
        ACTION_CANCEL,
        ACTION_FIRE,
        ACTION_RESCHEDULE,
        ACTION_RECONCILE,
        ACTION_UNFREEZE,
    }:
        return
    target_count = _external_target_count(context)
    since = now - timedelta(days=1)
    used = sum(
        MarketingQuotaUsage.objects.filter(occurred_at__gte=since).values_list(
            "target_count", flat=True
        )
    )
    if used + target_count > MAX_EXTERNAL_TARGETS_PER_DAY:
        oldest = MarketingQuotaUsage.objects.filter(occurred_at__gte=since).order_by(
            "occurred_at"
        ).values_list("occurred_at", flat=True).first()
        retry_after = max(
            1,
            int(((oldest + timedelta(days=1)) - now).total_seconds()) if oldest else 86_400,
        )
        raise MarketingAuthorizationError(
            code="marketing_daily_target_quota_exceeded",
            detail="A quota diária de destinos externos foi atingida.",
            status_code=429,
            retry_after=retry_after,
        )
    MarketingQuotaUsage.objects.create(
        actor=actor,
        action=context.action,
        resource_ref=context.resource_ref,
        target_count=target_count,
        occurred_at=now,
        retention_until=now + SECURITY_RETENTION,
    )


def _external_target_count(context: AuthorizationContext) -> int:
    return max(context.audience_count, len(context.platforms), 1)


def _require_second_actor(
    confirmation: MarketingConfirmation,
    *,
    context: AuthorizationContext,
    now: datetime,
) -> None:
    if confirmation.second_actor_id is None or confirmation.second_approved_at is None:
        raise MarketingAuthorizationError(
            code="dual_control_required",
            detail="Outra pessoa autorizada precisa confirmar este resumo.",
            status_code=403,
        )
    if confirmation.second_approved_at > now or confirmation.second_approved_at < confirmation.created_at:
        raise MarketingAuthorizationError(
            code="dual_control_invalid",
            detail="O segundo controle não é válido para esta confirmação.",
            status_code=403,
        )
    second = _fresh_actor(confirmation.second_actor)
    _require_any_capability(second, _second_actor_capabilities(context.action))
    if not hmac.compare_digest(
        confirmation.second_permission_fingerprint,
        permission_fingerprint(second),
    ):
        raise MarketingAuthorizationError(
            code="dual_control_authorization_changed",
            detail="A autorização do segundo aprovador mudou. Gere um novo resumo.",
            status_code=403,
        )


def _second_actor_capabilities(action: str) -> tuple[str, ...]:
    if action == ACTION_UNFREEZE:
        return ("shop.freeze_marketing",)
    return (
        "shop.approve_marketing_announcements",
        "shop.publish_marketing_announcements",
    )


def _require_capability(actor, capability: str) -> None:
    if not actor.has_perm(capability):
        raise MarketingAuthorizationError(
            code="capability_revoked",
            detail="Sua capacidade para esta ação foi removida. Nenhum efeito ocorreu.",
            status_code=403,
        )


def _require_any_capability(actor, capabilities: Sequence[str]) -> None:
    if not any(actor.has_perm(capability) for capability in capabilities):
        raise MarketingAuthorizationError(
            code="dual_control_capability_revoked",
            detail="O segundo aprovador não possui mais a capacidade necessária.",
            status_code=403,
        )


def _fresh_actor(actor, *, for_update: bool = False):
    query = get_user_model().objects
    if for_update:
        query = query.select_for_update()
    try:
        return query.get(pk=getattr(actor, "pk", None), is_active=True)
    except get_user_model().DoesNotExist as exc:
        raise MarketingAuthorizationError(
            code="invalid_actor",
            detail="A sessão não representa uma pessoa ativa.",
            status_code=403,
        ) from exc


def _capability(value: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_CAPABILITY_RE.fullmatch(normalized):
        raise ValueError("invalid Marketing capability")
    return normalized


def _context_hash(context: AuthorizationContext) -> str:
    canonical = json.dumps(
        context.payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return _keyed_hash("context", canonical)


def _context_from_confirmation(confirmation: MarketingConfirmation) -> AuthorizationContext:
    return authorization_context(
        action=confirmation.action,
        resource_ref=confirmation.resource_ref,
        base_version=confirmation.base_version,
        artifact_hash=confirmation.artifact_hash,
        audience_hash=confirmation.audience_hash,
        audience_count=confirmation.audience_count,
        platforms=confirmation.platforms,
        scheduled_for=confirmation.scheduled_for,
        consequence=confirmation.consequence,
    )


def _token_hash(value: str) -> str:
    return _keyed_hash("token", value)


def _keyed_hash(domain: str, value: str) -> str:
    return hmac.new(
        str(settings.SECRET_KEY).encode(),
        f"marketing-security:{domain}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _plain_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _required_reason(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise MarketingAuthorizationError(
            code="reason_required",
            detail="Explique brevemente o motivo para manter a decisão auditável.",
            status_code=422,
            field_errors={"reason": ("Informe o motivo.",)},
        )
    if len(normalized) > 200:
        raise MarketingAuthorizationError(
            code="reason_too_long",
            detail="Use no máximo 200 caracteres.",
            status_code=422,
            field_errors={"reason": ("Use no máximo 200 caracteres.",)},
        )
    return normalized


def _event(
    event_type: str,
    *,
    actor=None,
    second_actor=None,
    confirmation: MarketingConfirmation | None = None,
    context: AuthorizationContext | None = None,
    action: str = "",
    resource_ref: str = "",
    reason_code: str = "",
    facts: Mapping[str, Any] | None = None,
    now: datetime,
) -> MarketingSecurityEvent:
    return MarketingSecurityEvent.objects.create(
        actor=actor,
        second_actor=second_actor,
        confirmation=confirmation,
        event_type=event_type,
        action=context.action if context is not None else action,
        resource_ref=context.resource_ref if context is not None else resource_ref,
        reason_code=reason_code,
        facts=dict(facts or {}),
        occurred_at=now,
        retention_until=now + SECURITY_RETENTION,
    )


def _denied(
    reason_code: str,
    actor,
    context: AuthorizationContext,
    *,
    confirmation: MarketingConfirmation | None = None,
) -> None:
    # This is best-effort evidence.  When called inside a command transaction it
    # deliberately rolls back with that transaction; API permission denials are
    # recorded separately by the permission gate.
    _event(
        "authorization_denied",
        actor=actor,
        confirmation=confirmation,
        context=context,
        reason_code=reason_code,
        now=timezone.now(),
    )


def _audience_bucket(count: int) -> str:
    if count < 10:
        return "lt_10"
    if count < 50:
        return "10_49"
    if count < 500:
        return "50_499"
    if count < 2_000:
        return "500_1999"
    if count <= 5_000:
        return "2000_5000"
    return "gt_5000"


def _aware_now(now: datetime | None) -> datetime:
    value = now or timezone.now()
    if timezone.is_naive(value):
        raise ValueError("Marketing security requires an aware clock")
    return value
