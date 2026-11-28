from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stockman", "0003_batch_quality_grade_ref"),
    ]

    operations = [
        migrations.AddField(
            model_name="batch",
            name="metadata",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Proveniência imutável do lote, como ordem de produção, versão da receita e composição executada."
                ),
                verbose_name="Metadados",
            ),
        ),
    ]
