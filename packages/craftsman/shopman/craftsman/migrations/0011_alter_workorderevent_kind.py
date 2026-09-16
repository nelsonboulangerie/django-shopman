from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("craftsman", "0010_alter_recipeentry_kind")]

    operations = [
        migrations.AlterField(
            model_name="workorderevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("planned", "Planejado"),
                    ("planning_confirmed", "Planejamento confirmado"),
                    ("adjusted", "Ajustado"),
                    ("started", "Iniciado"),
                    ("step_advanced", "Passo avançado"),
                    ("oven_armed", "Enfornado"),
                    ("oven_concluded", "Retirado do forno"),
                    ("oven_abandoned", "Medição de forno abandonada"),
                    ("shortage_overridden", "Falta sobreposta"),
                    ("finished", "Concluído"),
                    ("quality_corrected", "Qualidade corrigida"),
                    ("quality_reviewed", "Qualidade revisada"),
                    ("voided", "Cancelado"),
                ],
                max_length=20,
                verbose_name="Tipo",
            ),
        )
    ]
