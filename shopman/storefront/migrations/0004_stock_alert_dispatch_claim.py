from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("storefront", "0003_stock_alert_consent_evidence")]
    operations = [
        migrations.AddField(
            model_name="stockalertsubscription",
            name="dispatch_claimed_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="stockalertsubscription",
            name="dispatch_accepted_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
