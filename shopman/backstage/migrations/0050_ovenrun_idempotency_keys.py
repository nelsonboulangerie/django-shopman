from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0049_operator_alert_audience"),
    ]

    operations = [
        migrations.AddField(
            model_name="ovenrun",
            name="arm_idempotency_key",
            field=models.CharField(
                blank=True,
                max_length=160,
                null=True,
                unique=True,
                verbose_name="chave idempotente do arm",
            ),
        ),
        migrations.AddField(
            model_name="ovenrun",
            name="conclude_idempotency_key",
            field=models.CharField(
                blank=True,
                max_length=160,
                null=True,
                unique=True,
                verbose_name="chave idempotente da conclusão",
            ),
        ),
    ]
