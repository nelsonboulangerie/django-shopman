from django.db import migrations


def quarantine_unverified_web_alerts(apps, schema_editor):
    """Stop web deliveries whose only identity evidence was typed phone text.

    Historical rows and receipts remain available for audit. A verified login
    can create a fresh customer-bound subscription without reviving this proof.
    """
    Subscription = apps.get_model("storefront", "StockAlertSubscription")
    Subscription.objects.filter(
        channel_ref="web",
        customer_ref="",
        proof_status="verified",
        revoked_at__isnull=True,
    ).update(proof_status="legacy_unverified")


class Migration(migrations.Migration):
    dependencies = [
        ("storefront", "0007_stock_alerts_persist_until_cancelled"),
    ]

    operations = [
        migrations.RunPython(quarantine_unverified_web_alerts, migrations.RunPython.noop),
    ]
