"""O SKU aparece UMA vez por linha — no campo dele, não dentro do nome.

Na lista de insumos do mise en place cada linha já tem `sku` próprio, renderizado
logo abaixo do nome. O nome vinha como "Massa Tradição (MASSA-TRADICAO)", então o
código saía duas vezes na mesma linha.

A etiqueta de pesagem é o caso oposto e continua com o rótulo composto: ali há uma
linha por insumo e nada mais, e distinguir dois pré-preparos de nome parecido
depende do código estar à vista.
"""

from __future__ import annotations

import pytest

from shopman.backstage.projections.production import (
    _ingredient_label,
    _ingredient_name,
)


class _Recipe:
    def __init__(self, name):
        self.name = name


PRE_PREPARO = {"MASSA-TRADICAO": _Recipe("Massa Tradição")}
CATALOGO = {"FAR-TRIGO": "Farinha de trigo"}


def _name(sku):
    return _ingredient_name(sku, active_recipes=PRE_PREPARO, product_names=CATALOGO)


def _label(sku):
    return _ingredient_label(sku, active_recipes=PRE_PREPARO, product_names=CATALOGO)


@pytest.mark.parametrize("sku,esperado", [
    ("MASSA-TRADICAO", "Massa Tradição"),
    ("FAR-TRIGO", "Farinha de trigo"),
])
def test_o_nome_nao_carrega_o_sku(sku, esperado):
    assert _name(sku) == esperado
    assert sku not in _name(sku)


def test_sem_cadastro_o_sku_e_o_nome_e_a_linha_continua_existindo():
    assert _name("SEM-CADASTRO") == "SEM-CADASTRO"


def test_a_etiqueta_de_pesagem_mantem_o_codigo_a_vista():
    assert _label("MASSA-TRADICAO") == "Massa Tradição (MASSA-TRADICAO)"
    assert _label("FAR-TRIGO") == "Farinha de trigo (FAR-TRIGO)"


def test_a_etiqueta_nao_repete_quando_o_nome_ja_e_o_sku():
    assert _label("SEM-CADASTRO") == "SEM-CADASTRO"
