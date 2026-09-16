from django.db import migrations


def keep_verified_subscriptions(apps, schema_editor):
    """Remove the provisional TTL without reviving revoked or unverified rows."""
    Subscription = apps.get_model("storefront", "StockAlertSubscription")
    Subscription.objects.filter(
        proof_status="verified",
        revoked_at__isnull=True,
    ).exclude(expires_at__isnull=True).update(expires_at=None)


class Migration(migrations.Migration):
    dependencies = [
        ("storefront", "0006_alter_stockalertdelivery_options_and_more"),
    ]

    operations = [
        migrations.RunPython(keep_verified_subscriptions, migrations.RunPython.noop),
    ]
