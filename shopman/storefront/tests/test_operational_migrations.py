"""Isolated expansion rehearsal; never a production down-migration recipe."""

import uuid
from datetime import timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_web_phone_only_alerts_are_quarantined_without_touching_verified_channels_or_history():
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    previous = [("storefront", "0007_stock_alerts_persist_until_cancelled")]
    executor.migrate(previous)
    try:
        apps = executor.loader.project_state(previous).apps
        LegacySub = apps.get_model("storefront", "StockAlertSubscription")
        LegacyOccurrence = apps.get_model("storefront", "StockAlertOccurrence")
        LegacyDelivery = apps.get_model("storefront", "StockAlertDelivery")

        def make(*, evidence, channel="web", customer_ref="", revoked=False):
            return LegacySub.objects.create(
                ref=uuid.uuid4(),
                sku=f"PHONE-PROOF-{evidence}",
                channel_ref=channel,
                customer_ref=customer_ref,
                contact_phone=f"+55439999{evidence[-4:]}",
                evidence_hash=evidence,
                target_key=f"target-{evidence}",
                proof_status="verified",
                revoked_at=timezone.now() if revoked else None,
            )

        typed_web = make(evidence="typed-web-0001")
        account_web = make(evidence="account-web-0002", customer_ref="CUS-PROVEN")
        trusted_channel = make(evidence="whatsapp-0003", channel="whatsapp")
        historical = make(evidence="revoked-web-0004", revoked=True)
        occurrence = LegacyOccurrence.objects.create(
            sku=typed_web.sku,
            event_type="stock_back",
            semantic_key="phone-proof-preserved-occurrence",
            status="closed",
            closed_at=timezone.now(),
        )
        receipt = LegacyDelivery.objects.create(
            subscription_id=typed_web.pk,
            occurrence_id=occurrence.pk,
            status="accepted",
            provider_receipt_ref="synthetic-preserved-receipt",
        )

        MigrationExecutor(connection).migrate(latest)
        from shopman.storefront.models import StockAlertSubscription

        current_typed_web = StockAlertSubscription.objects.get(pk=typed_web.pk)
        current_account_web = StockAlertSubscription.objects.get(pk=account_web.pk)
        current_trusted_channel = StockAlertSubscription.objects.get(pk=trusted_channel.pk)
        current_historical = StockAlertSubscription.objects.get(pk=historical.pk)
        assert current_typed_web.proof_status == "legacy_unverified"
        assert current_account_web.proof_status == "verified"
        assert current_trusted_channel.proof_status == "verified"
        assert current_historical.proof_status == "verified"
        # Expansion never fabricates an age declaration. Even identity-verified
        # rows stay inactive until a new explicit confirmation is recorded.
        assert current_typed_web.adult_declared is False
        assert current_account_web.adult_declared is False
        assert current_trusted_channel.adult_declared is False
        assert current_historical.adult_declared is False
        assert current_typed_web.is_active is False
        assert current_account_web.is_active is False
        assert current_trusted_channel.is_active is False
        assert StockAlertSubscription.objects.get(pk=typed_web.pk).deliveries.get(pk=receipt.pk).status == "accepted"
    finally:
        MigrationExecutor(connection).migrate(latest)


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
            expires_at=timezone.now() + timedelta(days=5),
        )
        unverified = LegacySub.objects.create(
            ref=uuid.uuid4(),
            sku="DUPLICATE-MIGRATION",
            contact_phone="+5543999990010",
            evidence_hash="unverified-migration-evidence",
            target_key="duplicate-migration-target",
            proof_status="legacy_unverified",
        )
        unverified_only = LegacySub.objects.create(
            ref=uuid.uuid4(),
            sku="UNVERIFIED-MIGRATION",
            contact_phone="+5543999990011",
            evidence_hash="unverified-only-migration-evidence",
            target_key="unverified-only-migration-target",
            proof_status="legacy_unverified",
            expires_at=timezone.now() + timedelta(days=5),
        )
        cancelled_expiry = timezone.now() + timedelta(days=5)
        cancelled = LegacySub.objects.create(
            ref=uuid.uuid4(),
            sku="CANCELLED-MIGRATION",
            contact_phone="+5543999990012",
            evidence_hash="cancelled-migration-evidence",
            target_key="cancelled-migration-target",
            proof_status="verified",
            expires_at=cancelled_expiry,
            revoked_at=timezone.now(),
            revoke_reason="customer_request",
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
        current_unverified_only = StockAlertSubscription.objects.get(pk=unverified_only.pk)
        current_cancelled = StockAlertSubscription.objects.get(pk=cancelled.pk)
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
        assert current_verified.expires_at is None
        assert current_unverified.revoked_at is not None
        assert current_unverified.revoke_reason == "superseded_during_persistent_migration"
        assert current_unverified.revocation_evidence_hash
        assert current_unverified_only.revoked_at is None
        assert current_unverified_only.expires_at is not None
        assert current_cancelled.revoked_at is not None
        assert current_cancelled.expires_at == cancelled_expiry
        mixed_worker = StockAlertSubscription.objects.get(evidence_hash="mixed-worker-evidence")
        assert mixed_worker.pause_reason == ""
        assert mixed_worker.adult_declared is False
        assert mixed_worker.is_active is False
    finally:
        MigrationExecutor(connection).migrate(latest)
