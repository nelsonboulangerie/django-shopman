from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0092_kdsticket_ciente_por_e_prontos_desfeitos"),
    ]

    operations = [
        migrations.AddField(
            model_name="kdsticket",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="iniciado em"),
        ),
        migrations.AddField(
            model_name="kdsticket",
            name="started_by",
            field=models.CharField(blank=True, default="", max_length=150, verbose_name="iniciado por"),
        ),
        migrations.AddField(
            model_name="kdsticket",
            name="open_tickets_at_start",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Carga da Cozinha quando o preparo começou: tickets abertos em todas as estações, fora este.",
                null=True,
                verbose_name="tickets abertos no início",
            ),
        ),
    ]
