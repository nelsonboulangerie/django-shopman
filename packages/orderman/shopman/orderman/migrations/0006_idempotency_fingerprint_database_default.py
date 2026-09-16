from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orderman", "0005_idempotency_request_fingerprint")]
    operations = [
        migrations.AlterField(
            model_name="idempotencykey",
            name="request_fingerprint",
            field=models.CharField(max_length=64, blank=True, default="", db_default=""),
        )
    ]
