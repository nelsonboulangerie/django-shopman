"""O rename de SKU tem de alcançar TODO campo que guarda SKU (SKU-REAL-PLAN F2).

`RefBulk.cascade_rename` só enxerga o que o `RefSourceRegistry` conhece, e o
registro é populado por `RefField.contribute_to_class`. Um `models.CharField`
comum guardando SKU é invisível para ele — e a falha é silenciosa: o rename
"funciona", devolve um número, e deixa linhas órfãs apontando para um produto
que não existe mais.

Foi exatamente esse o estado antes deste plano: 10 dos 18 campos estavam de
fora. O teste existe para que o próximo campo de SKU não nasça órfão.
"""

from __future__ import annotations

import pytest
from django.apps import apps

# `HistoricalSaleItem` é o único que fica de fora, e de propósito: ele guarda o
# export do Yooga, que é registro de terceiro. Renomear ali seria reescrever o
# que a outra casa emitiu — e, no sentido desta troca (inventado → real), ele já
# está do lado certo desde sempre.
FORA_POR_DECISAO = {("backstage.HistoricalSaleItem", "sku")}

NOMES_DE_CAMPO_SKU = {"sku", "output_sku", "input_sku"}


def _campos_que_guardam_sku() -> set[tuple[str, str]]:
    achados = set()
    for model in apps.get_models():
        for field in model._meta.get_fields():
            name = getattr(field, "name", "")
            if name in NOMES_DE_CAMPO_SKU and hasattr(field, "max_length"):
                achados.add((f"{model._meta.app_label}.{model.__name__}", name))
    return achados


def _campos_no_registro() -> set[tuple[str, str]]:
    from shopman.refs.registry import _ref_source_registry

    return set(_ref_source_registry.get_sources_for_type("SKU"))


def test_todo_campo_de_sku_esta_no_cascade():
    orfaos = _campos_que_guardam_sku() - _campos_no_registro() - FORA_POR_DECISAO
    assert not orfaos, (
        "Estes campos guardam SKU mas o cascade_rename não os alcança: "
        f"{sorted(orfaos)}. Declare-os como RefField(ref_type='SKU') — o "
        "deconstruct se disfarça de CharField, então não gera migração. Se o "
        "campo deve mesmo ficar de fora, acrescente a FORA_POR_DECISAO com o "
        "motivo escrito."
    )


def test_historico_do_yooga_segue_fora():
    # Guarda a decisão nos dois sentidos: alguém que "consertar" a omissão
    # transformando-o em RefField passa a reescrever registro de terceiro.
    assert FORA_POR_DECISAO.isdisjoint(_campos_no_registro())


@pytest.mark.django_db
def test_rename_atravessa_catalogo_estoque_e_curadoria():
    """Um rename, três apps — inclusive um que estava fora do cascade até agora."""
    from shopman.offerman.models import Product
    from shopman.refs.bulk import RefBulk
    from shopman.stockman.models import Position, Quant

    from shopman.backstage.models import ConsumptionRole, ProductConsumptionTag

    vitrine = Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)
    Product.objects.create(sku="CROISSANT", name="Croissant", base_price_q=850)
    Quant.objects.create(sku="CROISSANT", position=vitrine)
    papel = ConsumptionRole.objects.create(ref="ambiguo", label="Ambíguo", reading="hybrid")
    ProductConsumptionTag.objects.create(sku="CROISSANT", role=papel)

    RefBulk.cascade_rename("SKU", "CROISSANT", "CT", actor="teste")

    assert Product.objects.filter(sku="CT").exists()
    assert not Product.objects.filter(sku="CROISSANT").exists()
    assert Quant.objects.filter(sku="CT").exists()
    # A etiqueta de consumo era CharField comum: sem a conversão, ela ficaria
    # apontando para um SKU que não existe mais, e o B.I. perderia a curadoria.
    assert ProductConsumptionTag.objects.filter(sku="CT").exists()
