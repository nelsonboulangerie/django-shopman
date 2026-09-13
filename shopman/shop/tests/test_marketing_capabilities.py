from __future__ import annotations

from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from shopman.shop.services import marketing_artifacts, marketing_capabilities
from shopman.shop.services.marketing_contracts import MarketingContractError


def test_catalog_has_unique_complete_destination_identities():
    identities = {
        (destination.platform, destination.delivery_kind, format_.ref)
        for destination in marketing_capabilities.DESTINATIONS
        for format_ in destination.formats
    }

    assert len(identities) == sum(
        len(destination.formats)
        for destination in marketing_capabilities.DESTINATIONS
    )
    assert marketing_capabilities.platform_refs() == (
        "instagram",
        "facebook",
        "google_business",
        "whatsapp",
    )
    assert marketing_capabilities.publication_platform_refs() == (
        "instagram",
        "facebook",
        "google_business",
    )


def test_every_default_format_belongs_to_its_destination():
    for destination in marketing_capabilities.DESTINATIONS:
        assert destination.format(destination.default_format) is not None


def test_new_content_rejects_a_provider_option_with_no_effect():
    with pytest.raises(MarketingContractError) as caught:
        marketing_artifacts.normalize_platform_content(
            platforms=("instagram",),
            platform_content={
                "instagram": {
                    "publication_format": "story",
                    "sticker_link": "https://example.com/item",
                }
            },
        )

    assert caught.value.code == "unsupported_provider_field"
    assert (
        "platform_content.instagram.sticker_link" in caught.value.field_errors
    )


def test_closed_schema_keeps_content_fields_and_supported_whatsapp_metadata():
    normalized = marketing_artifacts.normalize_platform_content(
        platforms=("whatsapp",),
        platform_content={
            "whatsapp": {
                "body": "Fornada pronta",
                "image_url": "https://example.com/foto.jpg",
                "template_name": "fornada",
            }
        },
    )

    assert normalized == {
        "whatsapp": {
            "body": "Fornada pronta",
            "image_url": "https://example.com/foto.jpg",
            "template_name": "fornada",
        }
    }


def test_publication_defaults_still_come_from_the_catalog():
    normalized = marketing_artifacts.normalize_platform_content(
        platforms=("instagram", "facebook", "google_business"),
        platform_content={},
    )

    assert normalized == {
        "instagram": {"publication_format": "story"},
        "facebook": {"publication_format": "feed"},
        "google_business": {"publication_format": "standard"},
    }


def test_resolved_artifact_carries_the_complete_destination_identity():
    artifact = marketing_artifacts.resolve_dispatch_artifact(
        platform="instagram",
        content={"body": "Fornada pronta", "image_url": "/media/fornada.jpg"},
        platform_content={"instagram": {"publication_format": "feed"}},
        content_version=2,
    )

    assert (artifact.platform, artifact.delivery_kind, artifact.format) == (
        "instagram",
        "publication",
        "feed",
    )
    assert artifact.as_payload()["delivery_kind"] == "publication"
    assert artifact.as_payload()["format"] == "feed"


def test_new_identity_must_be_complete_and_match_the_catalog():
    with pytest.raises(MarketingContractError) as missing:
        marketing_capabilities.resolve_identity("instagram")
    assert missing.value.code == "delivery_identity_missing"

    with pytest.raises(MarketingContractError) as mismatched:
        marketing_capabilities.resolve_identity(
            "instagram",
            delivery_kind="direct_message",
            format_ref="story",
        )
    assert mismatched.value.code == "delivery_kind_mismatch"

    assert marketing_capabilities.resolve_identity(
        "whatsapp",
        allow_legacy_missing=True,
    ) == ("direct_message", "message")


def test_backfill_preserves_an_explicit_historical_instagram_format():
    migration = import_module("shopman.shop.migrations.0053_marketing_delivery_identity")
    outbox = SimpleNamespace(
        platform="instagram",
        artifact=SimpleNamespace(
            payload={"resolved_artifacts": {"instagram": {"provider_fields": {"publication_format": "feed"}}}}
        ),
    )

    assert migration._artifact_format(outbox, "story") == "feed"


@pytest.mark.django_db(transaction=True)
def test_delivery_identity_migration_reverses_and_reapplies_cleanly():
    before = [("shop", "0052_faqentry_historicalfaqentry")]
    after = [("shop", "0053_marketing_delivery_identity")]

    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old_outbox = executor.loader.project_state(before).apps.get_model("shop", "MarketingOutbox")
    assert "delivery_kind" not in {field.name for field in old_outbox._meta.concrete_fields}

    old_apps = executor.loader.project_state(before).apps
    Announcement = old_apps.get_model("shop", "Announcement")
    Artifact = old_apps.get_model("shop", "MarketingContentArtifact")
    Snapshot = old_apps.get_model("shop", "AudienceSnapshot")
    Receipt = old_apps.get_model("shop", "MarketingCommandReceipt")
    Outbox = old_apps.get_model("shop", "MarketingOutbox")
    Target = old_apps.get_model("shop", "DeliveryTarget")
    now = timezone.now()
    retention = now + timedelta(days=30)
    announcement = Announcement.objects.create(
        content={"body": "Registro histórico"},
        platforms=["instagram"],
    )
    artifact = Artifact.objects.create(
        announcement=announcement,
        version=1,
        schema_version=3,
        payload={"resolved_artifacts": {"instagram": {"provider_fields": {"publication_format": "feed"}}}},
        artifact_hash="a" * 64,
        retention_until=retention,
    )
    snapshot = Snapshot.objects.create(
        announcement=announcement,
        version=1,
        summary={},
        rule_summary={},
        rule_hash="b" * 64,
        cohort_hash="c" * 64,
        policy_version="test-v1",
        calculated_at=now,
        expires_at=retention,
        retention_until=retention,
    )
    receipt = Receipt.objects.create(
        kind="approve",
        state="completed",
        announcement=announcement,
        resource_ref=f"announcement:{announcement.pk}",
        actor_ref="system:test",
        idempotency_key_hash="d" * 64,
        payload_hash="e" * 64,
        base_version=1,
        resulting_version=2,
        retention_until=retention,
    )
    outbox = Outbox.objects.create(
        command=receipt,
        announcement=announcement,
        snapshot=snapshot,
        artifact=artifact,
        platform="instagram",
        available_at=now,
    )
    target = Target.objects.create(
        outbox=outbox,
        announcement=announcement,
        snapshot=snapshot,
        artifact=artifact,
        platform="instagram",
        target_fingerprint="f" * 64,
        fingerprint_key_version=1,
        next_attempt_at=now,
        identity_retention_until=retention,
        record_retention_until=retention,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    new_apps = executor.loader.project_state(after).apps
    new_outbox = new_apps.get_model("shop", "MarketingOutbox")
    new_target = new_apps.get_model("shop", "DeliveryTarget")
    assert {"delivery_kind", "format"} <= {field.name for field in new_outbox._meta.concrete_fields}
    assert {"delivery_kind", "format"} <= {field.name for field in new_target._meta.concrete_fields}
    migrated_outbox = new_outbox.objects.get(pk=outbox.pk)
    migrated_target = new_target.objects.get(pk=target.pk)
    assert (migrated_outbox.delivery_kind, migrated_outbox.format) == (
        "publication",
        "feed",
    )
    assert (migrated_target.delivery_kind, migrated_target.format) == (
        "publication",
        "feed",
    )

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
