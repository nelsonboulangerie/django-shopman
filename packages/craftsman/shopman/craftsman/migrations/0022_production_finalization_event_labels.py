from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("craftsman", "0021_workorderevent_formula_deviation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workorderevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("planned", "Planejado"),
                    ("planning_confirmed", "Planejamento confirmado"),
                    ("adjusted", "Ajustado"),
                    ("started", "Produção"),
                    ("step_advanced", "Etapa avançada"),
                    ("oven_armed", "Enfornado"),
                    ("oven_concluded", "Retirado do forno"),
                    ("oven_abandoned", "Medição de forno abandonada"),
                    ("shortage_overridden", "Falta sobreposta"),
                    ("formula_deviation", "Desvio da fórmula autorizado"),
                    ("finished", "Finalização"),
                    ("quality_corrected", "Qualidade corrigida"),
                    ("quality_reviewed", "Qualidade revisada"),
                    ("voided", "Cancelado"),
                ],
                max_length=20,
                verbose_name="Tipo",
            ),
        ),
    ]
