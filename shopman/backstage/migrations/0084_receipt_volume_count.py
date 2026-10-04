# Contagem de volumes da NF em conferência, guardada no servidor (V6-COMPRAS, C23).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("backstage", "0083_seating_spot_plan"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReceiptVolumeCount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("invoice_key", models.CharField(max_length=44, unique=True, verbose_name="chave da NF")),
                ("counted", models.PositiveSmallIntegerField(verbose_name="volumes contados")),
                ("counted_by", models.CharField(blank=True, max_length=150, verbose_name="contado por")),
                ("counted_at", models.DateTimeField(auto_now=True, verbose_name="contado em")),
            ],
            options={
                "verbose_name": "contagem de volumes da NF",
                "verbose_name_plural": "contagens de volumes da NF",
            },
        ),
    ]
