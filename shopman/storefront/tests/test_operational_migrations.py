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
        LegacyReceipt.objects.bulk_create(
            [
                LegacyReceipt(scope="synthetic-volume", key=f"receipt-{i}", status="in_progress" if i % 2 else "done")
                for i in range(1000)
            ]
        )
        sub = LegacySub.objects.create(sku="LEGACY-MIGRATION", contact_phone="+5543999990008")
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        # An old worker may still write after schema expansion. Exercise the
        # historical ORM, which cannot include the new columns in INSERT.
        mixed = LegacyReceipt.objects.create(scope="mixed-worker", key="legacy-write", status="in_progress")
        LegacySub.objects.create(sku="MIXED-WORKER", contact_phone="+5543999990007")
        # Repeating a completed expansion is safe; it must not synthesize proof.
        MigrationExecutor(connection).migrate(latest)
        from shopman.orderman.models import IdempotencyKey

        from shopman.storefront.models import StockAlertSubscription

        receipt = IdempotencyKey.objects.get(pk=old.pk)
        current = StockAlertSubscription.objects.get(pk=sub.pk)
        assert IdempotencyKey.objects.get(pk=mixed.pk).request_fingerprint == ""
        assert IdempotencyKey.objects.filter(scope="synthetic-volume", request_fingerprint="").count() == 1000
        # A new worker may claim an intention immediately before a code rollback.
        # The old worker must be able to finish that in-flight job without
        # clearing the fingerprint that binds retries to the original request.
        bound = IdempotencyKey.objects.create(
            scope="new-worker",
            key="bound",
            request_fingerprint="a" * 64,
            status="in_progress",
        )
        legacy_view = LegacyReceipt.objects.get(pk=bound.pk)
        legacy_view.status = "done"
        legacy_view.response_code = 201
        legacy_view.response_body = {"order_ref": "synthetic"}
        legacy_view.save(update_fields=["status", "response_code", "response_body"])
        bound.refresh_from_db()
        assert bound.request_fingerprint == "a" * 64
        assert bound.status == "done"
        assert bound.response_code == 201
        assert bound.response_body == {"order_ref": "synthetic"}
        assert receipt.request_fingerprint == ""
        assert receipt.response_body == {"ok": True}
        assert current.dispatch_claimed_at is None
        assert current.dispatch_accepted_at is None
        assert current.notified_at is None
    finally:
        MigrationExecutor(connection).migrate(latest)
