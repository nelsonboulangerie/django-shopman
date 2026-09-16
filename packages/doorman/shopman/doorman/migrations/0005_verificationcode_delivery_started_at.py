from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("doorman", "0004_trusted_device_station"),
    ]

    operations = [
        migrations.AddField(
            model_name="verificationcode",
            name="delivery_started_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Cerca durável: enquanto PENDING e preenchido, a entrega "
                    "externa pode estar em curso."
                ),
                null=True,
                verbose_name="entrega iniciada em",
            ),
        ),
        migrations.AddField(
            model_name="verificationcode",
            name="delivery_reconciled_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="entrega reconciliada em",
            ),
        ),
        migrations.AddField(
            model_name="verificationcode",
            name="delivery_evidence_ref",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Identificador operacional sem telefone, e-mail ou conteúdo da mensagem."
                ),
                max_length=120,
                verbose_name="referência da evidência da entrega",
            ),
        ),
    ]
