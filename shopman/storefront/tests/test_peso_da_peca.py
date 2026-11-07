"""Beta 05/11 (LOJA-11): o peso aproximado repetia a medida que o nome já dizia.

E aparecia em bebida: Espresso "~40 g/un.", Chá "~400 g/un.".
"""

from types import SimpleNamespace

import pytest

from shopman.storefront.presentation.catalog import unit_weight_label

pytestmark = pytest.mark.django_db


def _product(name, weight, natureza=None):
    metadata = {"attributes": {"natureza": {"value": natureza}}} if natureza else {}
    return SimpleNamespace(sku="X", name=name, unit_weight_g=weight, metadata=metadata)


@pytest.mark.parametrize(
    ("name", "weight", "expected"),
    [
        ("Baguette de Tradition", 250, "peça de ~250 g"),
        ("Queijo Camembert Président 125g", 125, None),
        ("Água Mineral Prata 310ml", 310, None),
        ("Geleia 1,5 kg", 1500, None),
        ("Croissant", None, None),
    ],
)
def test_o_peso_aparece_so_quando_acrescenta(name, weight, expected):
    assert unit_weight_label(_product(name, weight)) == expected


def test_bebida_nao_tem_peso_de_peca():
    assert unit_weight_label(_product("Espresso", 40, natureza="bebida")) is None
    assert unit_weight_label(_product("Chá Camille", 400, natureza="bebida")) is None


def test_comida_com_natureza_declarada_continua_com_peso():
    assert unit_weight_label(_product("Croissant", 70, natureza="comida")) == "peça de ~70 g"
