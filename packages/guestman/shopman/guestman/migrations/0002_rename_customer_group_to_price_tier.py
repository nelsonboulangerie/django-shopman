"""CustomerGroup → PriceTier, e Customer.group → Customer.price_tier.

⚠️ Escrita à mão de propósito. O `makemigrations` deduziu **criar PriceTier + apagar
CustomerGroup** (ele não tem como saber que os dois nomes são a mesma coisa), e isso
DERRUBARIA as faixas existentes junto com o vínculo de cada cliente — quem estava em
atacado voltaria ao preço de varejo, calado.

`RenameModel` + `RenameField` preservam a tabela e os dados. As migrações são append-only
desde o reset de 2026-08, então a única correção possível aqui é escrever a certa.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("guestman", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(old_name="CustomerGroup", new_name="PriceTier"),
        migrations.RenameField(
            model_name="customer", old_name="group", new_name="price_tier",
        ),
        migrations.AlterModelOptions(
            name="pricetier",
            options={
                "ordering": ["-priority", "name"],
                "verbose_name": "faixa de preço",
                "verbose_name_plural": "faixas de preço",
            },
        ),
        migrations.AlterField(
            model_name="pricetier",
            name="is_default",
            field=models.BooleanField(
                default=False, help_text="Faixa padrão para novos clientes", verbose_name="padrão",
            ),
        ),
        migrations.AlterField(
            model_name="pricetier",
            name="metadata",
            field=models.JSONField(
                blank=True, default=dict,
                help_text='Metadados da faixa. Ex: {"discount_percent": 10, "min_order_q": 5000}',
                verbose_name="metadados",
            ),
        ),
        migrations.AlterField(
            model_name="customer",
            name="price_tier",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="customers",
                to="guestman.pricetier",
                verbose_name="faixa de preço",
            ),
        ),
    ]
