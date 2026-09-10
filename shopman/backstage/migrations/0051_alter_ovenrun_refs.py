from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0050_ovenrun_idempotency_keys"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ovenrun",
            name="operator_ref",
            field=models.CharField(blank=True, max_length=100, verbose_name="operador"),
        ),
        migrations.AlterField(
            model_name="ovenrun",
            name="oven_ref",
            field=models.CharField(
                blank=True,
                help_text="Snapshot de WorkOrder.position_ref no momento do arm.",
                max_length=100,
                verbose_name="forno",
            ),
        ),
    ]
