"""Evidence that the alert migration never equates legacy read with resolved."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def test_legacy_read_maps_to_seen_while_unmapped_rows_expire_explicitly():
    executor = MigrationExecutor(connection)
    old_target = [("shop", "0036_marketing_platform_configuration")]
    new_target = [("shop", "0037_user_notification_lifecycle")]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps

    User = old_apps.get_model("auth", "User")
    Template = old_apps.get_model("shop", "AnnouncementTemplate")
    Campaign = old_apps.get_model("shop", "Campaign")
    Announcement = old_apps.get_model("shop", "Announcement")
    Notification = old_apps.get_model("shop", "UserNotification")

    owner = User.objects.create(username="migration-owner")
    template = Template.objects.create(name="Migração", body="{{product_name}}")
    campaign = Campaign.objects.create(
        name="Migração",
        trigger="production_finished",
        template=template,
        platforms=["instagram"],
    )
    announcement = Announcement.objects.create(
        rule=campaign,
        template=template,
        status="pending_review",
        content={"body": "Saiu do forno"},
        platforms=["instagram"],
    )
    mapped = Notification.objects.create(
        user=owner,
        category="campaign",
        title="Revisão",
        action_data={"announcement_id": announcement.pk},
        is_actionable=True,
        is_read=True,
    )
    unmapped = Notification.objects.create(
        user=owner,
        category="system",
        title="Legado sem origem",
        is_read=False,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    MigratedNotification = new_apps.get_model("shop", "UserNotification")
    Event = new_apps.get_model("shop", "UserNotificationEvent")

    mapped = MigratedNotification.objects.get(pk=mapped.pk)
    assert mapped.lifecycle == "seen"
    assert mapped.resolved_at is None
    assert mapped.source_condition == "announcement_review"
    assert mapped.source_ref == f"announcement:{announcement.pk}"
    assert mapped.owner_role == "product"
    assert mapped.escalation_role == "ops"
    assert mapped.dedupe_key.endswith(f":owner:{owner.pk}")

    unmapped = MigratedNotification.objects.get(pk=unmapped.pk)
    assert unmapped.lifecycle == "expired"
    assert unmapped.resolved_at is not None
    assert unmapped.source_condition == "legacy_unmapped"
    assert Event.objects.filter(
        notification_id=unmapped.pk,
        event_type="expired",
        outcome_code="legacy_backfill_unmapped",
    ).exists()
