from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shop", "0037_contact_release")]

    operations = [
        migrations.AddField(
            model_name="qualitygrade",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Graus inativos permanecem no histórico, mas não podem "
                    "classificar novas fornadas."
                ),
                verbose_name="ativo",
            ),
        ),
    ]
