"""One backend authority for Marketing Actions across operator surfaces."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone

from shopman.backstage.permissions import can_view_operator_alerts
from shopman.backstage.projections.marketing_v2 import (
    ActionConfirmationProjectionV2,
    AnnouncementProjectionV2,
    MarketingActionProjectionV2,
    MarketingAnnouncementDataV2,
    MarketingBoardDataV2,
    MarketingEnvelopeV2,
    MarketingHistoryDataV2,
)
from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    Campaign,
    DeliveryAttempt,
    DeliveryReconciliation,
    DeliveryTarget,
    MarketingSafetyState,
    NotificationLifecycle,
    UserNotification,
)
from shopman.shop.services.campaign import POSTING_PLATFORMS
from shopman.shop.services.marketing_contracts import ProviderOutcomeKind
from shopman.shop.services.marketing_security import (
    ACTION_APPROVE,
    ACTION_CANCEL,
    ACTION_RECONCILE,
    ACTION_RESCHEDULE,
    ACTION_RETRY,
    MIN_LARGE_SCHEDULE_DELAY,
    MarketingAuthorizationError,
    authorization_context,
    requirement_for,
)

_EMPTY_CONFIRMATION = ActionConfirmationProjectionV2(
    mode="none",
    token_required=False,
    consequence_code="",
    step_up="none",
    dual_control=False,
)
_NOT_PROVIDED = object()


@dataclass(frozen=True, slots=True)
class CampaignActionContext:
    ref: str
    version: int
    active: bool


@dataclass(frozen=True, slots=True)
class PlatformActionContext:
    platform_ref: str
    version: int
    state: str
    in_use: bool


@dataclass(frozen=True, slots=True)
class _RecoveryFacts:
    retryable_count: int = 0
    reconcile_count: int = 0
    reconciliation_pending_count: int = 0
    unreconcilable_unknown_count: int = 0


def with_resolved_actions(
    envelope: MarketingEnvelopeV2,
    *,
    actor,
    now: datetime | None = None,
) -> MarketingEnvelopeV2:
    """Attach Actions to board/detail without changing their factual data."""

    clock = _aware_clock(now)
    current_actor = _fresh_actor(actor)
    announcements = _announcements_in(envelope)
    recovery = _recovery_facts_for(announcements)
    frozen = _marketing_frozen()
    actions = tuple(
        action
        for announcement in announcements
        for action in _announcement_actions(
            announcement,
            actor=current_actor,
            recovery=recovery[announcement.ref],
            frozen=frozen,
            now=clock,
        )
    )
    return replace(envelope, actions=actions)


def resolve_actions(
    resource,
    *,
    actor,
    now: datetime | None = None,
) -> tuple[MarketingActionProjectionV2, ...]:
    """Resolve every supported Marketing/alert resource through one dispatch point."""

    return _resolve_actions(
        resource,
        actor=_fresh_actor(actor),
        now=_aware_clock(now),
    )


def resolve_actions_for(
    resources,
    *,
    actor,
    now: datetime | None = None,
) -> tuple[tuple[MarketingActionProjectionV2, ...], ...]:
    """Resolve a collection with one fresh authority lookup, never N per row."""

    items = tuple(resources)
    if not items:
        return ()
    current_actor = _fresh_actor(actor)
    clock = _aware_clock(now)
    if all(isinstance(resource, AnnouncementProjectionV2) for resource in items):
        announcements = tuple(items)
        recovery = _recovery_facts_for(announcements)
        frozen = _marketing_frozen()
        return tuple(
            _announcement_actions(
                announcement,
                actor=current_actor,
                recovery=recovery[announcement.ref],
                frozen=frozen,
                now=clock,
            )
            for announcement in announcements
        )
    if all(isinstance(resource, UserNotification) for resource in items):
        notification_ids = {
            announcement_id
            for notification in items
            if (announcement_id := _notification_announcement_id(notification)) > 0
        }
        announcements = {
            announcement.pk: announcement
            for announcement in Announcement.objects.filter(
                pk__in=notification_ids,
            ).only("pk", "version", "status", "expires_at")
        }
        return tuple(
            _notification_actions(
                notification,
                actor=current_actor,
                announcement=announcements.get(
                    _notification_announcement_id(notification)
                ),
            )
            for notification in items
        )
    return tuple(
        _resolve_actions(resource, actor=current_actor, now=clock)
        for resource in items
    )


def _resolve_actions(
    resource,
    *,
    actor,
    now: datetime,
) -> tuple[MarketingActionProjectionV2, ...]:

    if isinstance(resource, AnnouncementProjectionV2):
        recovery = _recovery_facts_for((resource,))[resource.ref]
        return _announcement_actions(
            resource,
            actor=actor,
            recovery=recovery,
            frozen=_marketing_frozen(),
            now=now,
        )
    if isinstance(resource, CampaignActionContext):
        return _campaign_actions(resource, actor=actor)
    if isinstance(resource, Campaign):
        return _campaign_actions(
            CampaignActionContext(
                ref=f"campaign:{resource.pk}",
                version=resource.version,
                active=resource.is_active,
            ),
            actor=actor,
        )
    if isinstance(resource, PlatformActionContext):
        return _platform_actions(resource, actor=actor)
    if isinstance(resource, UserNotification):
        return _notification_actions(resource, actor=actor)

    from shopman.backstage.models import OperatorAlert

    if isinstance(resource, OperatorAlert):
        return _operator_alert_actions(resource, actor=actor)
    raise TypeError(f"Unsupported Marketing Action resource: {type(resource).__name__}")


def resolve_notification_actions(
    notification: UserNotification,
    *,
    actor,
    announcement: Announcement | None | object = _NOT_PROVIDED,
) -> tuple[MarketingActionProjectionV2, ...]:
    """Resolve an alert without an implicit approve or arbitrary stored href."""

    return _notification_actions(
        notification,
        actor=_fresh_actor(actor),
        announcement=announcement,
    )


def resolve_notification_actions_for(
    notifications,
    *,
    actor,
    announcements: dict[int, Announcement],
) -> dict[int, tuple[MarketingActionProjectionV2, ...]]:
    """Resolve one notification page with constant authority/source queries."""

    current_actor = _fresh_actor(actor)
    return {
        notification.pk: _notification_actions(
            notification,
            actor=current_actor,
            announcement=announcements.get(_notification_announcement_id(notification)),
        )
        for notification in notifications
    }


def _announcement_actions(
    announcement: AnnouncementProjectionV2,
    *,
    actor,
    recovery: _RecoveryFacts,
    frozen: bool,
    now: datetime,
) -> tuple[MarketingActionProjectionV2, ...]:
    actions: list[MarketingActionProjectionV2] = []
    resource_ref = announcement.ref
    version = announcement.version
    pk = _resource_id(resource_ref, "announcement")
    page = f"/announcements/{pk}"
    command = f"/api/v1/backstage/marketing/announcements/{pk}"

    actions.append(_action(
        resource_ref=resource_ref,
        version=version,
        kind="open_announcement",
        priority=("primary" if announcement.state == AnnouncementStatus.PENDING_REVIEW else "quiet"),
        href=page,
        method="GET",
        idempotency="none",
        capabilities=("shop.view_marketing",),
        actor=actor,
    ))

    if announcement.state in {
        AnnouncementStatus.DRAFT,
        AnnouncementStatus.PENDING_REVIEW,
        AnnouncementStatus.EXPIRED,
    }:
        editable_reason = (
            "" if announcement.state != AnnouncementStatus.EXPIRED else "review_window_expired"
        )
        actions.append(_action(
            resource_ref=resource_ref,
            version=version,
            kind="edit_announcement",
            priority="secondary",
            href=f"{page}#content",
            method="GET",
            idempotency="none",
            capabilities=("shop.edit_marketing_campaigns",),
            actor=actor,
            unavailable_reason=editable_reason,
        ))

    if announcement.state in {
        AnnouncementStatus.PENDING_REVIEW,
        AnnouncementStatus.EXPIRED,
    }:
        approval_reason = _approval_reason(announcement)
        now_confirmation, now_policy_reason = _confirmation(
            action=ACTION_APPROVE,
            resource_ref=resource_ref,
            version=version,
            audience_count=announcement.audience.eligible_count,
            consequence="publishes_now_to_eligible_audience",
            now=now,
        )
        schedule_confirmation, schedule_policy_reason = _confirmation(
            action=ACTION_APPROVE,
            resource_ref=resource_ref,
            version=version,
            audience_count=announcement.audience.eligible_count,
            consequence="schedules_eligible_audience",
            scheduled_for=now + MIN_LARGE_SCHEDULE_DELAY,
            now=now,
        )
        actions.extend((
            _action(
                resource_ref=resource_ref,
                version=version,
                kind="publish_announcement_now",
                priority="secondary",
                href=f"{command}/approve/",
                method="POST",
                payload_schema="marketing.command.approve-now.v2",
                idempotency="required",
                confirmation=now_confirmation,
                eligible_count=announcement.audience.eligible_count,
                capabilities=(
                    "shop.approve_marketing_announcements",
                    "shop.publish_marketing_announcements",
                ),
                actor=actor,
                unavailable_reason=now_policy_reason or approval_reason,
                frozen=frozen,
                blocked_by_freeze=True,
                creates_external_effect=True,
            ),
            _action(
                resource_ref=resource_ref,
                version=version,
                kind="schedule_announcement",
                priority="secondary",
                href=f"{command}/approve/",
                method="POST",
                payload_schema="marketing.command.approve-scheduled.v2",
                idempotency="required",
                confirmation=schedule_confirmation,
                eligible_count=announcement.audience.eligible_count,
                capabilities=(
                    "shop.approve_marketing_announcements",
                    "shop.publish_marketing_announcements",
                ),
                actor=actor,
                unavailable_reason=schedule_policy_reason or approval_reason,
                frozen=frozen,
                blocked_by_freeze=True,
                creates_external_effect=True,
            ),
            _action(
                resource_ref=resource_ref,
                version=version,
                kind="reject_announcement",
                priority="danger",
                href=f"{command}/reject/",
                method="POST",
                payload_schema="marketing.command.reject.v2",
                idempotency="required",
                confirmation=replace(_EMPTY_CONFIRMATION, mode="simple"),
                capabilities=("shop.approve_marketing_announcements",),
                actor=actor,
                unavailable_reason=(
                    "review_window_expired"
                    if announcement.state == AnnouncementStatus.EXPIRED
                    else ""
                ),
            ),
        ))

    cancellable = (
        announcement.state in {AnnouncementStatus.APPROVED, AnnouncementStatus.PUBLISHING}
        and announcement.scheduled_for is not None
        and announcement.delivery.state == "not_started"
    )
    if announcement.scheduled_for is not None or announcement.state == AnnouncementStatus.APPROVED:
        unavailable_reason = "" if cancellable else "dispatch_already_started"
        cancel_confirmation, _cancel_policy_reason = _confirmation(
            action=ACTION_CANCEL,
            resource_ref=resource_ref,
            version=version,
            audience_count=announcement.audience.eligible_count,
            consequence="cancels_only_reversible_delivery_lanes",
            scheduled_for=announcement.scheduled_for,
            now=now,
        )
        actions.append(_action(
            resource_ref=resource_ref,
            version=version,
            kind="cancel_announcement",
            priority="danger",
            href=f"{command}/cancel/",
            method="POST",
            payload_schema="marketing.command.cancel.v2",
            idempotency="required",
            confirmation=cancel_confirmation,
            eligible_count=announcement.delivery.fanout_expected,
            capabilities=("shop.publish_marketing_announcements",),
            actor=actor,
            unavailable_reason=unavailable_reason,
            frozen=frozen,
            blocked_by_freeze=True,
        ))
        if announcement.state == AnnouncementStatus.APPROVED:
            reschedule_confirmation, _reschedule_policy_reason = _confirmation(
                action=ACTION_RESCHEDULE,
                resource_ref=resource_ref,
                version=version,
                audience_count=announcement.audience.eligible_count,
                consequence="changes_scheduled_delivery_time",
                scheduled_for=now + MIN_LARGE_SCHEDULE_DELAY,
                now=now,
            )
            actions.append(_action(
                resource_ref=resource_ref,
                version=version,
                kind="reschedule_announcement",
                priority="primary",
                href=f"{command}/reschedule/",
                method="POST",
                payload_schema="marketing.command.reschedule.v2",
                idempotency="required",
                confirmation=reschedule_confirmation,
                eligible_count=announcement.delivery.fanout_expected,
                capabilities=("shop.publish_marketing_announcements",),
                actor=actor,
                unavailable_reason=unavailable_reason,
                frozen=frozen,
                blocked_by_freeze=True,
            ))

    if recovery.retryable_count:
        retry_confirmation, retry_policy_reason = _confirmation(
            action=ACTION_RETRY,
            resource_ref=resource_ref,
            version=version,
            audience_count=recovery.retryable_count,
            consequence="retries_only_failed_retryable_targets",
            now=now,
        )
        actions.append(_action(
            resource_ref=resource_ref,
            version=version,
            kind="retry_failed_delivery",
            priority=("secondary" if recovery.reconcile_count else "primary"),
            href=f"{command}/retry-deliveries/",
            method="POST",
            payload_schema="marketing.command.retry-delivery.v2",
            idempotency="required",
            confirmation=retry_confirmation,
            eligible_count=recovery.retryable_count,
            capabilities=("shop.retry_failed_marketing",),
            actor=actor,
            unavailable_reason=retry_policy_reason,
            frozen=frozen,
            blocked_by_freeze=True,
            creates_external_effect=True,
        ))

    unknown_count = announcement.delivery.counts.unknown
    if unknown_count:
        reconcile_confirmation, reconcile_policy_reason = _confirmation(
            action=ACTION_RECONCILE,
            resource_ref=resource_ref,
            version=version,
            audience_count=recovery.reconcile_count,
            consequence="looks_up_unknown_without_resend",
            now=now,
        )
        reconcile_reason = reconcile_policy_reason
        if not recovery.reconcile_count:
            reconcile_reason = (
                "reconciliation_pending"
                if recovery.reconciliation_pending_count
                else "unknown_not_reconcilable"
            )
        actions.append(_action(
            resource_ref=resource_ref,
            version=version,
            kind="reconcile_unknown_delivery",
            priority="primary",
            href=f"{command}/reconcile-deliveries/",
            method="POST",
            payload_schema="marketing.command.reconcile-delivery.v2",
            idempotency="required",
            confirmation=reconcile_confirmation,
            eligible_count=recovery.reconcile_count,
            capabilities=("shop.reconcile_unknown_marketing",),
            actor=actor,
            unavailable_reason=reconcile_reason,
        ))
    return tuple(actions)


def _campaign_actions(
    campaign: CampaignActionContext,
    *,
    actor,
) -> tuple[MarketingActionProjectionV2, ...]:
    campaign_id = _resource_id(campaign.ref, "campaign")
    return (
        _action(
            resource_ref=campaign.ref,
            version=campaign.version,
            kind="edit_campaign",
            priority="primary",
            href=f"/campaigns#campaign-{campaign_id}",
            method="GET",
            idempotency="none",
            capabilities=("shop.edit_marketing_campaigns",),
            actor=actor,
        ),
        _action(
            resource_ref=campaign.ref,
            version=campaign.version,
            kind="fire_campaign",
            priority="secondary",
            href=f"/api/v1/backstage/marketing/rules/{campaign_id}/fire/",
            method="POST",
            payload_schema="marketing.command.fire-campaign.v2",
            idempotency="required",
            confirmation=replace(
                _EMPTY_CONFIRMATION,
                mode="summary",
                token_required=True,
                consequence_code="creates_campaign_announcement",
            ),
            capabilities=("shop.fire_marketing_campaigns",),
            actor=actor,
            unavailable_reason=("" if campaign.active else "campaign_inactive"),
            creates_external_effect=True,
        ),
    )


def _platform_actions(
    platform: PlatformActionContext,
    *,
    actor,
) -> tuple[MarketingActionProjectionV2, ...]:
    page = f"/platforms#{platform.platform_ref}"
    resource_ref = f"platform:{platform.platform_ref}"
    actions = [
        _action(
            resource_ref=resource_ref,
            version=platform.version,
            kind="open_platform",
            priority="primary",
            href=page,
            method="GET",
            idempotency="none",
            capabilities=("shop.view_marketing",),
            actor=actor,
        ),
    ]
    if platform.platform_ref == "whatsapp":
        actions.append(_action(
            resource_ref=resource_ref,
            version=platform.version,
            kind="configure_platform",
            priority="secondary",
            href="/api/v1/backstage/marketing/whatsapp-template/",
            method="POST",
            payload_schema="marketing.command.configure-platform.v1",
            idempotency="required",
            confirmation=replace(
                _EMPTY_CONFIRMATION,
                mode="summary",
                token_required=True,
                consequence_code="changes_whatsapp_flow",
                step_up="totp",
            ),
            capabilities=("shop.configure_marketing_platforms",),
            actor=actor,
            unavailable_reason=(
                "platform_readiness_unknown"
                if platform.state == "unknown"
                else ""
            ),
        ))
        actions.append(_action(
            resource_ref=resource_ref,
            version=platform.version,
            kind="send_platform_test",
            priority="secondary",
            href="/platforms#whatsapp-test",
            method="GET",
            idempotency="none",
            capabilities=("shop.send_marketing_test",),
            actor=actor,
        ))
    return tuple(actions)


def _notification_actions(
    notification: UserNotification,
    *,
    actor,
    announcement: Announcement | None | object = _NOT_PROVIDED,
) -> tuple[MarketingActionProjectionV2, ...]:
    if getattr(actor, "pk", None) != notification.user_id:
        return ()
    if notification.lifecycle in {
        NotificationLifecycle.RESOLVED,
        NotificationLifecycle.EXPIRED,
    }:
        return ()
    actions = []
    if notification.lifecycle == NotificationLifecycle.UNSEEN:
        actions.append(_action(
            resource_ref=f"notification:{notification.pk}",
            version=notification.version,
            kind="mark_notification_seen",
            priority="quiet",
            href=f"/api/v1/backstage/notifications/{notification.pk}/read/",
            method="POST",
            idempotency="supported",
            actor=actor,
        ))
    if notification.lifecycle in {
        NotificationLifecycle.UNSEEN,
        NotificationLifecycle.SEEN,
    }:
        actions.append(_action(
            resource_ref=f"notification:{notification.pk}",
            version=notification.version,
            kind="acknowledge_notification",
            priority="quiet",
            href=f"/api/v1/backstage/notifications/{notification.pk}/acknowledge/",
            method="POST",
            idempotency="supported",
            actor=actor,
        ))
    announcement_id = _notification_announcement_id(notification)
    if announcement_id <= 0:
        return tuple(actions)
    if announcement is _NOT_PROVIDED:
        announcement = Announcement.objects.filter(pk=announcement_id).only(
            "pk",
            "version",
            "status",
            "expires_at",
        ).first()
    if not isinstance(announcement, Announcement):
        return tuple(actions)
    expired = announcement.is_expired()
    actions.insert(0, _action(
        resource_ref=f"announcement:{announcement.pk}",
        version=announcement.version,
        kind="open_announcement",
        priority="primary",
        href=f"/announcements/{announcement.pk}#review",
        method="GET",
        idempotency="none",
        capabilities=("shop.view_marketing",),
        actor=actor,
        unavailable_reason=(
            "review_window_expired"
            if expired
            else (
                "source_version_changed"
                if announcement.version != notification.source_version
                else (
                "announcement_no_longer_actionable"
                if announcement.status != AnnouncementStatus.PENDING_REVIEW
                else ""
                )
            )
        ),
    ))
    return tuple(actions)


def _operator_alert_actions(alert, *, actor) -> tuple[MarketingActionProjectionV2, ...]:
    return (
        _action(
            resource_ref=f"operator_alert:{alert.pk}",
            version=1,
            kind="acknowledge_alert",
            priority="quiet",
            href=f"/api/v1/backstage/alerts/{alert.pk}/ack/",
            method="POST",
            idempotency="supported",
            actor=actor,
            allowed_override=can_view_operator_alerts(actor),
            unavailable_reason="alert_already_acknowledged" if alert.acknowledged else "",
        ),
    )


def _action(
    *,
    resource_ref: str,
    version: int,
    kind: str,
    priority: str,
    href: str,
    method: str,
    actor,
    payload_schema: str = "",
    idempotency: str = "required",
    confirmation: ActionConfirmationProjectionV2 = _EMPTY_CONFIRMATION,
    eligible_count: int = 0,
    capabilities: tuple[str, ...] = (),
    unavailable_reason: str = "",
    frozen: bool = False,
    blocked_by_freeze: bool = False,
    creates_external_effect: bool = False,
    allowed_override: bool | None = None,
) -> MarketingActionProjectionV2:
    allowed = (
        allowed_override
        if allowed_override is not None
        else all(_has_perm(actor, capability) for capability in capabilities)
    )
    reason = ""
    if not allowed:
        reason = "missing_capability"
    elif frozen and blocked_by_freeze:
        reason = "marketing_frozen"
    elif unavailable_reason:
        reason = unavailable_reason
    return MarketingActionProjectionV2(
        ref=f"{resource_ref}:{kind}:v{max(0, int(version))}",
        resource_ref=resource_ref,
        kind=kind,
        label=f"presentation.marketing.action.{kind}",
        priority=priority,
        enabled=not reason,
        reason=reason,
        href=href,
        method=method,
        payload_schema=payload_schema,
        idempotency=idempotency,
        confirmation=confirmation,
        eligible_count=max(0, int(eligible_count)),
        required_capabilities=capabilities,
        creates_external_effect=creates_external_effect,
    )


def _approval_reason(announcement: AnnouncementProjectionV2) -> str:
    if announcement.state == AnnouncementStatus.EXPIRED:
        return "review_window_expired"
    if announcement.audience.freshness.state != "fresh":
        return f"audience_{announcement.audience.freshness.state}"
    if not announcement.platform_refs:
        return "no_platform_selected"
    public_only = all(
        platform_ref in POSTING_PLATFORMS
        for platform_ref in announcement.platform_refs
    )
    if announcement.audience.eligible_count <= 0 and not public_only:
        return "no_eligible_audience"
    if announcement.readiness.state != "ready":
        return f"platform_readiness_{announcement.readiness.state}"
    return ""


def _confirmation(
    *,
    action: str,
    resource_ref: str,
    version: int,
    audience_count: int,
    consequence: str,
    now: datetime,
    scheduled_for: datetime | None = None,
) -> tuple[ActionConfirmationProjectionV2, str]:
    try:
        context = authorization_context(
            action=action,
            resource_ref=resource_ref,
            base_version=version,
            audience_count=audience_count,
            scheduled_for=scheduled_for,
            consequence=consequence,
        )
        requirement = requirement_for(context, now=now)
    except MarketingAuthorizationError as exc:
        return _EMPTY_CONFIRMATION, exc.code
    return (
        ActionConfirmationProjectionV2(
            mode=requirement.confirmation_mode,
            token_required=True,
            consequence_code=consequence,
            step_up=requirement.step_up_level,
            dual_control=requirement.dual_control,
        ),
        "",
    )


def _recovery_facts_for(
    announcements: tuple[AnnouncementProjectionV2, ...],
) -> dict[str, _RecoveryFacts]:
    facts = {
        announcement.ref: _RecoveryFacts(
            retryable_count=announcement.delivery.counts.failed_retryable,
            unreconcilable_unknown_count=announcement.delivery.counts.unknown,
        )
        for announcement in announcements
    }
    ids = {
        _resource_id(announcement.ref, "announcement"): announcement.ref
        for announcement in announcements
    }
    if not ids:
        return facts

    active_reconciliation = DeliveryReconciliation.objects.filter(
        target_id=OuterRef("pk"),
        state__in=(
            DeliveryReconciliation.State.PENDING,
            DeliveryReconciliation.State.CLAIMED,
        ),
    )
    rows = (
        DeliveryTarget.objects.filter(
            announcement_id__in=ids,
            state=DeliveryTarget.State.UNKNOWN,
            attempts__state=DeliveryAttempt.State.COMPLETED,
            attempts__outcome_kind=ProviderOutcomeKind.UNKNOWN.value,
        )
        .annotate(reconciliation_active=Exists(active_reconciliation))
        .values("announcement_id", "reconciliation_active")
        .annotate(total=Count("pk", distinct=True))
    )
    mutable = {
        ref: {
            "retryable_count": value.retryable_count,
            "reconcile_count": 0,
            "reconciliation_pending_count": 0,
            "unreconcilable_unknown_count": value.unreconcilable_unknown_count,
        }
        for ref, value in facts.items()
    }
    for row in rows:
        ref = ids[row["announcement_id"]]
        count = int(row["total"])
        mutable[ref]["unreconcilable_unknown_count"] -= count
        key = (
            "reconciliation_pending_count"
            if row["reconciliation_active"]
            else "reconcile_count"
        )
        mutable[ref][key] += count
    return {
        ref: _RecoveryFacts(
            **values
            | {
                "unreconcilable_unknown_count": max(
                    0,
                    values["unreconcilable_unknown_count"],
                )
            }
        )
        for ref, values in mutable.items()
    }


def _announcements_in(
    envelope: MarketingEnvelopeV2,
) -> tuple[AnnouncementProjectionV2, ...]:
    if isinstance(envelope.data, MarketingBoardDataV2):
        return (*envelope.data.pending, *envelope.data.recent)
    if isinstance(envelope.data, MarketingAnnouncementDataV2):
        return (envelope.data.announcement,)
    if isinstance(envelope.data, MarketingHistoryDataV2):
        return envelope.data.items
    return ()


def _marketing_frozen() -> bool:
    return MarketingSafetyState.objects.filter(scope="default", frozen=True).exists()


def _resource_id(resource_ref: str, prefix: str) -> int:
    head, separator, raw_id = str(resource_ref).partition(":")
    if head != prefix or not separator or not raw_id.isdigit() or int(raw_id) <= 0:
        raise ValueError(f"Invalid {prefix} resource ref")
    return int(raw_id)


def _has_perm(actor, capability: str) -> bool:
    return bool(
        getattr(actor, "is_active", False)
        and getattr(actor, "has_perm", lambda _code: False)(capability)
    )


def _fresh_actor(actor):
    actor_id = getattr(actor, "pk", None)
    if actor_id is None:
        return None
    return get_user_model().objects.filter(pk=actor_id, is_active=True).first()


def _notification_announcement_id(notification: UserNotification) -> int:
    source_id = None
    if notification.source_condition == "announcement_review":
        try:
            source_id = _resource_id(notification.source_ref, "announcement")
        except ValueError:
            source_id = None
    if source_id is not None:
        return source_id
    raw_id = (
        (notification.action_data or {}).get("announcement_id")
        if notification.is_actionable and isinstance(notification.action_data, dict)
        else None
    )
    try:
        value = int(raw_id)
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


def _aware_clock(value: datetime | None) -> datetime:
    clock = value or timezone.now()
    if timezone.is_naive(clock):
        raise ValueError("Marketing Action resolution requires an aware clock.")
    return clock
