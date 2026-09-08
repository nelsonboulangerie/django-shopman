from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("craftsman", "0007_recipe_book"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workorderevent",
            name="kind",
            field=models.CharField(
                choices=[
                    ("planned", "Planejado"),
                    ("adjusted", "Ajustado"),
                    ("started", "Iniciado"),
                    ("step_advanced", "Passo avançado"),
                    ("oven_armed", "Enfornado"),
                    ("oven_concluded", "Retirado do forno"),
                    ("finished", "Concluído"),
                    ("voided", "Cancelado"),
                ],
                max_length=20,
                verbose_name="Tipo",
            ),
        ),
    ]
