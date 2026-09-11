"""Isolated expansion rehearsal; never a production down-migration recipe."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_additive_migrations_preserve_legacy_unknown_receipts_and_subscriptions():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [("orderman", "0004_alter_sessionitem_sku"), ("storefront", "0002_rotulos_em_portugues")]
    executor.migrate(previous)
    try:
        apps = executor.loader.project_state(previous).apps
        LegacyReceipt = apps.get_model("orderman", "IdempotencyKey")
        LegacySub = apps.get_model("storefront", "StockAlertSubscription")
        old = LegacyReceipt.objects.create(
            scope="legacy-test", key="legacy-key", status="done", response_body={"ok": True}
        )
        sub = LegacySub.objects.create(sku="LEGACY-MIGRATION", contact_phone="+5543999990008")
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        # Repeating a completed expansion is safe; it must not synthesize proof.
        MigrationExecutor(connection).migrate(latest)
        from shopman.orderman.models import IdempotencyKey

        from shopman.storefront.models import StockAlertSubscription

        receipt = IdempotencyKey.objects.get(pk=old.pk)
        current = StockAlertSubscription.objects.get(pk=sub.pk)
        assert receipt.request_fingerprint == ""
        assert receipt.response_body == {"ok": True}
        assert current.dispatch_claimed_at is None
        assert current.dispatch_accepted_at is None
        assert current.notified_at is None
    finally:
        MigrationExecutor(connection).migrate(latest)
