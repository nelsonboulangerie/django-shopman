from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orderman", "0004_alter_sessionitem_sku")]
    operations = [
        migrations.AddField(
            model_name="idempotencykey",
            name="request_fingerprint",
            field=models.CharField(max_length=64, blank=True, default=""),
        )
    ]
