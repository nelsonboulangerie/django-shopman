"""Persist the MKT-CAP-01 destination identity through outbox and ledger."""

from django.db import migrations, models

DESTINATIONS = {
    "instagram": ("publication", "story"),
    "facebook": ("publication", "feed"),
    "google_business": ("publication", "standard"),
    "whatsapp": ("direct_message", "message"),
}


def set_migration_timeouts(apps, schema_editor):
    """Fail fast instead of leaving a production release waiting on DDL locks."""

    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '30s'")


def _artifact_format(outbox, fallback: str) -> str:
    payload = outbox.artifact.payload
    if not isinstance(payload, dict):
        return fallback
    resolved = payload.get("resolved_artifacts")
    if not isinstance(resolved, dict):
        return fallback
    platform_payload = resolved.get(outbox.platform)
    if not isinstance(platform_payload, dict):
        return fallback
    explicit = str(platform_payload.get("format") or "").strip().lower()
    if explicit:
        return explicit
    provider_fields = platform_payload.get("provider_fields")
    if isinstance(provider_fields, dict):
        publication_format = str(provider_fields.get("publication_format") or "").strip().lower()
        if publication_format:
            return publication_format
    return fallback


def populate_identity(apps, schema_editor):
    MarketingOutbox = apps.get_model("shop", "MarketingOutbox")
    DeliveryTarget = apps.get_model("shop", "DeliveryTarget")

    for outbox in MarketingOutbox.objects.select_related("artifact").iterator(chunk_size=500):
        identity = DESTINATIONS.get(outbox.platform)
        if identity is None:
            continue
        delivery_kind, fallback = identity
        delivery_format = _artifact_format(outbox, fallback)
        MarketingOutbox.objects.filter(pk=outbox.pk).update(
            delivery_kind=delivery_kind,
            format=delivery_format,
        )
        DeliveryTarget.objects.filter(outbox_id=outbox.pk).update(
            delivery_kind=delivery_kind,
            format=delivery_format,
        )


def clear_identity(apps, schema_editor):
    apps.get_model("shop", "DeliveryTarget").objects.update(
        delivery_kind="",
        format="",
    )
    apps.get_model("shop", "MarketingOutbox").objects.update(
        delivery_kind="",
        format="",
    )


class Migration(migrations.Migration):
    dependencies = [("shop", "0052_faqentry_historicalfaqentry")]

    operations = [
        migrations.RunPython(
            set_migration_timeouts,
            migrations.RunPython.noop,
        ),
        migrations.AddField(
            model_name="marketingoutbox",
            name="delivery_kind",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AddField(
            model_name="marketingoutbox",
            name="format",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="deliverytarget",
            name="delivery_kind",
            field=models.CharField(blank=True, max_length=24),
        ),
        migrations.AddField(
            model_name="deliverytarget",
            name="format",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.RunPython(populate_identity, clear_identity),
        migrations.RemoveConstraint(
            model_name="marketingoutbox",
            name="shop_marketing_outbox_command_lane_uq",
        ),
        migrations.AddConstraint(
            model_name="marketingoutbox",
            constraint=models.UniqueConstraint(
                fields=(
                    "command",
                    "platform",
                    "delivery_kind",
                    "format",
                    "wave_key",
                ),
                name="shop_marketing_outbox_command_dest_lane_uq",
            ),
        ),
        migrations.AddConstraint(
            model_name="marketingoutbox",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(delivery_kind="", format="")
                    | models.Q(
                        delivery_kind__in=("publication", "direct_message"),
                        format__gt="",
                    )
                ),
                name="shop_marketing_outbox_identity_ck",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="deliverytarget",
            name="shop_delivery_target_snapshot_platform_fp_uq",
        ),
        migrations.AddConstraint(
            model_name="deliverytarget",
            constraint=models.UniqueConstraint(
                fields=(
                    "snapshot",
                    "platform",
                    "delivery_kind",
                    "format",
                    "target_fingerprint",
                ),
                name="shop_delivery_target_snapshot_dest_fp_uq",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliverytarget",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(delivery_kind="", format="")
                    | models.Q(
                        delivery_kind__in=("publication", "direct_message"),
                        format__gt="",
                    )
                ),
                name="shop_delivery_target_identity_ck",
            ),
        ),
    ]
