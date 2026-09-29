"""`sku_history`: para onde foi este código, respondido contra o catálogo vivo.

A porta existe porque três consumidores precisam da mesma resposta — o
cardápio do iFood, o 301 da loja e a herança de peso do B.I. — e dois deles
vivem longe de `config.management.commands`.
"""

from __future__ import annotations

import pytest
from shopman.offerman.models import Product

from shopman.shop.services.sku_history import (
    current_sku,
    live_product_skus,
    rename_map,
    retired_skus,
)


def _product(sku: str) -> Product:
    return Product.objects.create(sku=sku, name=sku, unit="un", base_price_q=1000)


def test_o_mapa_junta_as_duas_levas():
    from config.management.commands.apply_product_skus import AJUSTES, RENAMES
    from config.management.commands.rename_skus_to_real import RENAMES as PRIMEIRA

    mapa = rename_map()
    for tabela in (PRIMEIRA, RENAMES, AJUSTES):
        assert {a for a, _n in tabela} <= set(mapa)


def test_a_cadeia_atravessa_as_duas_levas():
    """`CROISSANT` virou `CT` em agosto e `CT` virou `CRO` em setembro.

    Quem olhasse uma leva só pararia no `CT`, que hoje é 404.
    """
    assert current_sku("CROISSANT", {"CRO"}) == "CRO"
    assert current_sku("CT", {"CRO"}) == "CRO"


def test_a_cadeia_de_tres_saltos_chega_ao_fim():
    """`MICBT` → `FOBM` → `FOBP`: a segunda leva do mesmo dia."""
    assert current_sku("MICBT", {"FOBP"}) == "FOBP"


def test_o_codigo_que_voltou_nao_e_desviado():
    """`FENDU` virou `FE` em agosto e `FE` voltou a `FENDU` em setembro.

    No papel é um ciclo. Contra o catálogo não há dúvida: para-se no que
    existe — e é isso que impede um 301 de mandar a página boa do `FENDU`
    para o `FE`, que é 404.
    """
    assert current_sku("FENDU", {"FENDU"}) == "FENDU"
    assert current_sku("FE", {"FENDU"}) == "FENDU"


def test_codigo_sem_para_onde_ir_devolve_ele_mesmo():
    assert current_sku("NAO-EXISTE", {"CRO"}) == "NAO-EXISTE"


@pytest.mark.django_db
def test_aposentados_lista_so_quem_chega_a_produto_vivo():
    """É o mapa que um 301 quer: a chave não existe, o valor existe."""
    _product("CRO")

    aposentados = retired_skus(live_product_skus())

    assert aposentados["CT"] == "CRO"
    assert aposentados["CROISSANT"] == "CRO"
    # O produto vivo nunca é chave: 301 de página boa para outra é perda.
    assert "CRO" not in aposentados


@pytest.mark.django_db
def test_quem_nao_leva_a_produto_vivo_fica_de_fora():
    """Produto que saiu do catálogo não tem destino honesto — é 410, não 301."""
    _product("CRO")

    aposentados = retired_skus(live_product_skus())

    assert "GL" not in aposentados       # o placeholder de geleia vai ser apagado
    assert "TRADI" not in aposentados    # não existe neste banco: não inventa destino


@pytest.mark.django_db
def test_o_codigo_que_voltou_nao_entra_como_aposentado():
    _product("FENDU")

    aposentados = retired_skus(live_product_skus())

    assert "FENDU" not in aposentados
    assert aposentados["FE"] == "FENDU"
