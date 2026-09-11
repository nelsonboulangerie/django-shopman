"""Isolated expansion rehearsal; never a production down-migration recipe."""

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_additive_migrations_preserve_legacy_unknown_receipts_and_subscriptions():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [
        ("orderman", "0004_alter_sessionitem_sku"),
        ("storefront", "0003_stock_alert_consent_evidence"),
    ]
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
        sub = LegacySub.objects.create(
            sku="LEGACY-MIGRATION",
            contact_phone="+5543999990008",
            evidence_hash="legacy-migration-evidence",
            target_key="legacy-migration-target",
        )
        verified = LegacySub.objects.create(
            ref=uuid.uuid4(),
            sku="DUPLICATE-MIGRATION",
            contact_phone="+5543999990010",
            evidence_hash="verified-migration-evidence",
            target_key="duplicate-migration-target",
            proof_status="verified",
            notified_at=timezone.now(),
        )
        unverified = LegacySub.objects.create(
            ref=uuid.uuid4(),
            sku="DUPLICATE-MIGRATION",
            contact_phone="+5543999990010",
            evidence_hash="unverified-migration-evidence",
            target_key="duplicate-migration-target",
            proof_status="legacy_unverified",
        )
        executor = MigrationExecutor(connection)
        executor.migrate(latest)
        # An old worker may still write after schema expansion. Exercise the
        # historical ORM, which cannot include the new columns in INSERT.
        mixed = LegacyReceipt.objects.create(scope="mixed-worker", key="legacy-write", status="in_progress")
        LegacySub.objects.create(
            ref=uuid.uuid4(),
            sku="MIXED-WORKER",
            contact_phone="+5543999990007",
            evidence_hash="mixed-worker-evidence",
            target_key="mixed-worker-target",
        )
        # Repeating a completed expansion is safe; it must not synthesize proof.
        MigrationExecutor(connection).migrate(latest)
        from shopman.orderman.models import IdempotencyKey

        from shopman.storefront.models import StockAlertSubscription

        receipt = IdempotencyKey.objects.get(pk=old.pk)
        current = StockAlertSubscription.objects.get(pk=sub.pk)
        current_verified = StockAlertSubscription.objects.get(pk=verified.pk)
        current_unverified = StockAlertSubscription.objects.get(pk=unverified.pk)
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
        assert current_verified.revoked_at is None
        assert current_unverified.revoked_at is not None
        assert current_unverified.revoke_reason == "superseded_during_persistent_migration"
        assert current_unverified.revocation_evidence_hash
        assert StockAlertSubscription.objects.get(evidence_hash="mixed-worker-evidence").pause_reason == ""
    finally:
        MigrationExecutor(connection).migrate(latest)
