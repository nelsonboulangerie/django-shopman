"""Custo sem conversão de insumo em g/mg/ml passa a ser do kg ou do litro.

Antes, ``cost_q`` sem conversão era centavo inteiro por grama (ou mililitro), e
R$ 110 por 1200 g virava R$ 0,09/g (o real é 0,0917). Agora é o custo da unidade
de leitura: R$ 91,67/kg. O que já existe é convertido multiplicando pelo fator
(beta 05/11, CMP-07). O arredondamento antigo não volta: o número convertido é o
mesmo dinheiro que estava gravado, só na unidade nova.
"""

from decimal import Decimal

from django.db import migrations, models

_SCALE = {"g": 1000, "mg": 1_000_000, "ml": 1000}


def _rescale(apps, *, forward: bool) -> None:
    Cost = apps.get_model("buyman", "SupplierMaterialCost")
    rows = Cost.objects.filter(conversion__isnull=True, material__unit__in=list(_SCALE)).select_related("material")
    for row in rows:
        scale = _SCALE[row.material.unit]
        if forward:
            row.cost_q = row.cost_q * scale
        else:
            row.cost_q = max(int((Decimal(row.cost_q) / scale).to_integral_value()), 1)
        row.save(update_fields=["cost_q"])


def forward(apps, schema_editor):
    _rescale(apps, forward=True)


def backward(apps, schema_editor):
    _rescale(apps, forward=False)


class Migration(migrations.Migration):

    dependencies = [
        ("buyman", "0011_alter_material_sku"),
    ]

    operations = [
        migrations.AlterField(
            model_name="suppliermaterialcost",
            name="cost_q",
            field=models.BigIntegerField(
                help_text=(
                    "Custo de UMA unidade de compra (a embalagem da conversão) em "
                    "centavos: o número da nota. Sem conversão, o custo do kg (insumo em "
                    "g) ou do litro (insumo em ml), ou da própria unidade."
                ),
                verbose_name="Custo (centavos)",
            ),
        ),
        migrations.RunPython(forward, backward),
    ]
