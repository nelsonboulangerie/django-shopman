from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("backstage", "0051_alter_ovenrun_refs"),
    ]

    operations = [
        migrations.AddField(
            model_name="operatoralert",
            name="rev",
            field=models.PositiveBigIntegerField(default=0, verbose_name="revisão"),
        ),
        migrations.AddField(
            model_name="operatoralert",
            name="acknowledged_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Vazio em registros legados reconhecidos antes da trilha nominal.",
                null=True,
                verbose_name="reconhecido em",
            ),
        ),
        migrations.AddField(
            model_name="operatoralert",
            name="acknowledged_by",
            field=models.CharField(
                blank=True,
                help_text="Identidade operacional que reconheceu o alerta.",
                max_length=100,
                verbose_name="reconhecido por",
            ),
        ),
        migrations.AddField(
            model_name="operatoralert",
            name="resolved_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Momento em que o sistema confirmou que a causa deixou de existir.",
                null=True,
                verbose_name="resolvido em",
            ),
        ),
        migrations.AddField(
            model_name="operatoralert",
            name="resolved_by",
            field=models.CharField(
                blank=True,
                help_text="Processo ou identidade que confirmou a resolução da causa.",
                max_length=100,
                verbose_name="resolvido por",
            ),
        ),
    ]
