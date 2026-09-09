"""MKT-022 — one authoritative Action resolver for every operator surface."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.marketing_actions import (
    CampaignActionContext,
    PlatformActionContext,
    resolve_actions,
    resolve_notification_actions,
    with_resolved_actions,
)
from shopman.backstage.projections.marketing_v2 import (
    PlatformReadinessProjectionV2,
    ReadinessProjectionV2,
    build_announcement,
    build_board,
)
from shopman.shop.models import (
    Announcement,
    AnnouncementStatus,
    UserNotification,
)
from shopman.shop.services.marketing_delivery_recovery import (
    request_reconciliation_command,
)
from shopman.shop.services.marketing_security import (
    ACTION_RECONCILE,
    MarketingAuthorizationRequired,
    activate_freeze,
    authorization_context,
    authorize_command,
    issue_confirmation,
)
from shopman.shop.tests.test_marketing_delivery_recovery import _targets

pytestmark = pytest.mark.django_db

User = get_user_model()


def _actor(username: str, *permissions: str):
    actor = User.objects.create_user(
        username=f"actions-{username}",
        password="senha-segura",
        is_staff=True,
    )
    actor.user_permissions.add(
        *Permission.objects.filter(codename__in=permissions)
    )
    return actor


def _action(actions, kind: str):
    return next(action for action in actions if action.kind == kind)


def _pending(*, suffix: str, eligible_count: int = 12) -> Announcement:
    now = timezone.now()
    return Announcement.objects.create(
        status=AnnouncementStatus.PENDING_REVIEW,
        content={"body": f"Conteúdo {suffix}"},
        platforms=["instagram"],
        audience={
            "eligible_count": eligible_count,
            "calculated_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
        },
        expires_at=now + timedelta(minutes=10),
    )


def _ready_projection(announcement: Announcement):
    projected = build_announcement(announcement).data.announcement
    return replace(
        projected,
        readiness=ReadinessProjectionV2(
            state="ready",
            platforms=(
                PlatformReadinessProjectionV2(
                    platform_ref="instagram",
                    state="ready",
                    reason_code="",
                    version=1,
                    checked_at=timezone.now(),
                    facts_as_of=timezone.now(),
                    fresh_until=None,
                    source_status="fresh",
                ),
            ),
        ),
    )


def test_delivery_recovery_actions_carry_current_authority_and_consequence():
    announcement, _targets_list = _targets(
        suffix="canonical-actions",
        states=("failed_retryable", "unknown"),
    )
    projected = build_announcement(announcement).data.announcement
    observer = _actor("observer", "view_marketing")
    operator = _actor(
        "recovery",
        "view_marketing",
        "retry_failed_marketing",
        "reconcile_unknown_marketing",
    )

    observer_actions = resolve_actions(projected, actor=observer)
    operator_actions = resolve_actions(projected, actor=operator)
    retry = _action(operator_actions, "retry_failed_delivery")
    reconcile = _action(operator_actions, "reconcile_unknown_delivery")

    assert _action(observer_actions, retry.kind).reason == "missing_capability"
    assert _action(observer_actions, reconcile.kind).reason == "missing_capability"
    assert retry.enabled is True
    assert retry.eligible_count == 1
    assert retry.idempotency == "required"
    assert retry.confirmation.mode == "typed"
    assert retry.confirmation.step_up == "password"
    assert retry.creates_external_effect is True
    assert reconcile.enabled is True
    assert reconcile.eligible_count == 1
    assert reconcile.confirmation.mode == "summary"
    assert reconcile.confirmation.step_up == "totp"
    assert reconcile.creates_external_effect is False
    assert all(action.href.startswith("/") and not action.href.startswith("//") for action in operator_actions)
    assert all(action.label.startswith("presentation.marketing.action.") for action in operator_actions)

    compatibility_actor = _actor("compatibility-reconcile")
    request_reconciliation_command(
        announcement.pk,
        actor=compatibility_actor,
        idempotency_key="canonical-actions-pending-0001",
        base_version=announcement.version,
    )
    pending = resolve_actions(
        build_announcement(announcement).data.announcement,
        actor=operator,
    )
    assert _action(pending, "reconcile_unknown_delivery").reason == (
        "reconciliation_pending"
    )


def test_pending_decision_uses_readiness_zero_audience_and_fresh_permissions():
    announcement = _pending(suffix="decision")
    publisher = _actor(
        "publisher",
        "view_marketing",
        "edit_marketing_campaigns",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
    )

    blocked = resolve_actions(
        build_announcement(announcement).data.announcement,
        actor=publisher,
    )
    assert _action(blocked, "publish_announcement_now").reason == (
        "platform_readiness_blocked"
    )

    ready = resolve_actions(_ready_projection(announcement), actor=publisher)
    publish = _action(ready, "publish_announcement_now")
    schedule = _action(ready, "schedule_announcement")
    assert publish.enabled is True
    assert publish.confirmation.mode == "typed"
    assert publish.confirmation.step_up == "password"
    assert schedule.enabled is True
    assert schedule.confirmation.mode == "summary"
    assert schedule.confirmation.step_up == "none"

    publisher.user_permissions.remove(
        Permission.objects.get(codename="publish_marketing_announcements")
    )
    revoked = resolve_actions(_ready_projection(announcement), actor=publisher)
    assert _action(revoked, "publish_announcement_now").reason == (
        "missing_capability"
    )

    empty = _pending(suffix="zero", eligible_count=0)
    empty_actions = resolve_actions(_ready_projection(empty), actor=publisher)
    assert _action(empty_actions, "publish_announcement_now").reason == (
        "missing_capability"
    )
    publisher.user_permissions.add(
        Permission.objects.get(codename="publish_marketing_announcements")
    )
    empty_actions = resolve_actions(_ready_projection(empty), actor=publisher)
    assert _action(empty_actions, "publish_announcement_now").reason == (
        "no_eligible_audience"
    )


def test_freeze_blocks_effects_but_keeps_lookup_only_reconciliation_possible():
    announcement, _targets_list = _targets(
        suffix="actions-freeze",
        states=("failed_retryable", "unknown"),
    )
    envelope = build_announcement(announcement)
    operator = _actor(
        "frozen-recovery",
        "view_marketing",
        "retry_failed_marketing",
        "reconcile_unknown_marketing",
    )
    security = _actor("freeze-owner", "freeze_marketing")
    activate_freeze(actor=security, reason="Exercício local do resolver canônico")

    actions = with_resolved_actions(envelope, actor=operator).actions
    assert _action(actions, "retry_failed_delivery").reason == "marketing_frozen"
    assert _action(actions, "reconcile_unknown_delivery").enabled is True

    context = authorization_context(
        action=ACTION_RECONCILE,
        resource_ref=f"announcement:{announcement.pk}",
        base_version=announcement.version,
        audience_count=1,
        consequence="looks_up_unknown_without_resend",
    )
    with pytest.raises(MarketingAuthorizationRequired) as caught:
        authorize_command(
            actor=operator,
            capability="shop.reconcile_unknown_marketing",
            context=context,
            token="",
        )
    challenge = issue_confirmation(caught.value, actor=operator)
    assert challenge["confirmation"]["step_up"] == "totp"


def test_campaign_platform_and_operator_alerts_share_the_canonical_shape():
    operator = _actor(
        "multi-resource",
        "view_marketing",
        "edit_marketing_campaigns",
        "fire_marketing_campaigns",
        "configure_marketing_platforms",
        "send_marketing_test",
        "manage_orders",
    )
    campaign_actions = resolve_actions(
        CampaignActionContext(ref="campaign:17", version=3, active=True),
        actor=operator,
    )
    platform_actions = resolve_actions(
        PlatformActionContext(
            platform_ref="whatsapp",
            version=4,
            state="ready",
            in_use=True,
        ),
        actor=operator,
    )
    alert = OperatorAlert.objects.create(
        type="stock_low",
        severity="warning",
        message="Estoque baixo",
    )
    alert_actions = resolve_actions(alert, actor=operator)

    assert _action(campaign_actions, "edit_campaign").enabled is True
    assert _action(campaign_actions, "fire_campaign").reason == (
        "command_not_available"
    )
    assert _action(platform_actions, "open_platform").enabled is True
    configure = _action(platform_actions, "configure_platform")
    assert configure.enabled is True
    assert configure.method == "POST"
    assert configure.idempotency == "required"
    assert configure.confirmation.step_up == "totp"
    assert _action(platform_actions, "send_platform_test").enabled is True
    assert _action(alert_actions, "acknowledge_alert").enabled is True

    alert.acknowledged = True
    alert.save(update_fields=["acknowledged"])
    assert _action(resolve_actions(alert, actor=operator), "acknowledge_alert").reason == (
        "alert_already_acknowledged"
    )


def test_notification_never_turns_stored_input_into_an_action_or_crosses_owner():
    announcement = _pending(suffix="notification")
    owner = _actor("notification-owner", "view_marketing")
    stranger = _actor("notification-stranger", "view_marketing")
    notification = UserNotification.objects.create(
        user=owner,
        category="campaign",
        title="Revisão",
        message="Anúncio aguardando decisão",
        action_url="https://evil.example/steal",
        action_data={
            "announcement_id": announcement.pk,
            "action": "approve",
            "href": "//evil.example/steal",
        },
        is_actionable=True,
    )

    actions = resolve_notification_actions(notification, actor=owner)
    assert [action.kind for action in actions] == [
        "open_announcement",
        "mark_notification_seen",
        "acknowledge_notification",
    ]
    assert all(action.method in {"GET", "POST"} for action in actions)
    assert all(action.href.startswith("/") and not action.href.startswith("//") for action in actions)
    assert resolve_notification_actions(notification, actor=stranger) == ()


def test_v2_board_attaches_actions_and_does_not_infer_permission(client):
    announcement = _pending(suffix="api")
    reader = _actor("api-reader", "view_marketing")
    client.force_login(reader)

    response = client.get("/api/v1/backstage/marketing/v2/")

    assert response.status_code == 200
    actions = response.json()["actions"]
    related = [
        action
        for action in actions
        if action["resource_ref"] == f"announcement:{announcement.pk}"
    ]
    assert next(
        action for action in related if action["kind"] == "open_announcement"
    )["enabled"] is True
    publish = next(
        action
        for action in related
        if action["kind"] == "publish_announcement_now"
    )
    assert publish["enabled"] is False
    assert publish["reason"] == "missing_capability"
    assert publish["required_capabilities"] == [
        "shop.approve_marketing_announcements",
        "shop.publish_marketing_announcements",
    ]


def test_board_action_resolution_query_budget_is_constant():
    now = timezone.now()
    Announcement.objects.bulk_create(
        Announcement(
            status=AnnouncementStatus.PENDING_REVIEW,
            content={"body": f"Anúncio {index}"},
            platforms=["instagram"],
            audience={
                "eligible_count": index + 1,
                "calculated_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
            },
            expires_at=now + timedelta(minutes=10),
        )
        for index in range(75)
    )
    operator = _actor(
        "query-budget",
        "view_marketing",
        "edit_marketing_campaigns",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
    )
    envelope = build_board(now=now)

    with CaptureQueriesContext(connection) as queries:
        resolved = with_resolved_actions(envelope, actor=operator, now=now)

    assert len(envelope.data.pending) == 75
    assert len(resolved.actions) == 75 * 5
    assert len(queries) <= 5
