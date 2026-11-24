"""Grava na loja a retenção do não retirado: 40% provisório (DEV-2026-089).

Decisão do dono (24/11/2026): da encomenda paga e não retirada, a revenda volta
inteira e a loja retém 40% do valor dos itens feitos para a encomenda, "arredondei
pra cima, pois não temos como computar o custo de oportunidade". Provisório até
medir o custo real (fichas × custos do Compras).

A regra mora em ``Shop.defaults["no_show"]["retention"]`` (ADR-042), não no código:
sem ela, o gesto do "Não retirado" recusa com o motivo. Esta migração grava a regra
na loja que já existe; a loja que já tem uma regra fica com a dela. O reverse é
inerte: tirar a regra travaria o gesto.
"""

from django.db import migrations

RETENTION = {"percent": 40, "decided_at": "2026-11-24", "provisional": True}


def add_retention(apps, schema_editor):
    Shop = apps.get_model("shop", "Shop")
    for shop in Shop.objects.all():
        defaults = dict(shop.defaults or {}) if isinstance(shop.defaults, dict) else {}
        block = dict(defaults.get("no_show") or {}) if isinstance(defaults.get("no_show"), dict) else {}
        if "retention" in block:
            continue
        block["retention"] = dict(RETENTION)
        defaults["no_show"] = block
        shop.defaults = defaults
        shop.save(update_fields=["defaults"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0140_proximo_lote_diz_disponivel")]

    operations = [migrations.RunPython(add_retention, migrations.RunPython.noop)]
