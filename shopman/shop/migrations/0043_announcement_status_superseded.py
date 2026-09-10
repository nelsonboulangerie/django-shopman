from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0042_freeze_active_hold_quality_policy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="announcement",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "rascunho"),
                    ("pending_review", "aguardando aprovação"),
                    ("approved", "aprovado"),
                    ("publishing", "publicando"),
                    ("published", "publicado"),
                    ("failed", "falhou"),
                    ("rejected", "recusado"),
                    ("expired", "expirado"),
                    ("superseded", "Substituído"),
                ],
                default="draft",
                max_length=16,
                verbose_name="situação",
            ),
        ),
    ]
