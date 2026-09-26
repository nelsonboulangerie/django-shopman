from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_migration_creates_missing_reschedule_template_and_preserves_curated_row():
    from shopman.shop.notification_copy import CUSTOMER_COPY

    before = [("shop", "0079_confirmado_com_todo_carinho")]
    after = [("shop", "0080_order_rescheduled_notification_template")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old_apps = executor.loader.project_state(before).apps
    OldTemplate = old_apps.get_model("shop", "NotificationTemplate")
    OldTemplate.objects.filter(event="order_rescheduled").delete()

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    new_apps = executor.loader.project_state(after).apps
    MigratedTemplate = new_apps.get_model("shop", "NotificationTemplate")
    created = MigratedTemplate.objects.get(event="order_rescheduled")
    assert created.subject == CUSTOMER_COPY["order_rescheduled"]["subject"]
    assert created.body == CUSTOMER_COPY["order_rescheduled"]["body"]
    assert created.whatsapp_flow_ns == ""

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old_apps = executor.loader.project_state(before).apps
    OldTemplate = old_apps.get_model("shop", "NotificationTemplate")
    assert not OldTemplate.objects.filter(event="order_rescheduled").exists()
    curated = OldTemplate.objects.create(
        event="order_rescheduled",
        subject="Texto aprovado pela loja",
        body="Corpo aprovado pela loja",
        whatsapp_flow_ns="content_curated",
        is_active=False,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    new_apps = executor.loader.project_state(after).apps
    preserved = new_apps.get_model("shop", "NotificationTemplate").objects.get(
        pk=curated.pk
    )
    assert preserved.subject == "Texto aprovado pela loja"
    assert preserved.body == "Corpo aprovado pela loja"
    assert preserved.whatsapp_flow_ns == "content_curated"
    assert preserved.is_active is False

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old_apps = executor.loader.project_state(before).apps
    rollback_preserved = old_apps.get_model("shop", "NotificationTemplate").objects.get(
        pk=curated.pk
    )
    assert rollback_preserved.subject == "Texto aprovado pela loja"
    assert rollback_preserved.whatsapp_flow_ns == "content_curated"
    assert rollback_preserved.is_active is False

    MigrationExecutor(connection).migrate(after)
