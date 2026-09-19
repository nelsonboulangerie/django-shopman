from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customer_merge", "0002_rotulos_em_portugues"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mergeaudit",
            name="status",
            field=models.CharField(
                choices=[
                    ("completed", "Unificada"),
                    ("reverted", "Desfeita"),
                    ("redacted", "Redigida por privacidade"),
                ],
                default="completed",
                max_length=20,
                verbose_name="situação",
            ),
        ),
    ]
