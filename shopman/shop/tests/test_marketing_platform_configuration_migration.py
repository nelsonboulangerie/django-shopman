"""The MKT-029 expand migration preserves legacy WhatsApp configuration."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_platform_configuration_migration_preserves_legacy_flow_and_adds_version():
    before = [("shop", "0035_marketing_security_authorization")]
    after = [("shop", "0036_marketing_platform_configuration")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old_apps = executor.loader.project_state(before).apps
    LegacyTemplate = old_apps.get_model("shop", "NotificationTemplate")
    legacy = LegacyTemplate.objects.create(
        event="announcement_published",
        subject="Novidade",
        body="{body}",
        whatsapp_flow_ns="content_legacy_verified_later",
        is_active=True,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    new_apps = executor.loader.project_state(after).apps
    MigratedTemplate = new_apps.get_model("shop", "NotificationTemplate")
    migrated = MigratedTemplate.objects.get(pk=legacy.pk)

    assert migrated.whatsapp_flow_ns == "content_legacy_verified_later"
    assert migrated.version == 1
    assert new_apps.get_model("shop", "MarketingPlatformAuditEvent") is not None

    MigrationExecutor(connection).migrate(after)
