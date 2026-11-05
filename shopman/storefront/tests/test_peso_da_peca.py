"""Beta 05/11 (LOJA-11): o peso aproximado repetia a medida que o nome já dizia."""

from types import SimpleNamespace

import pytest
from shopman.storefront.presentation.catalog import unit_weight_label


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
    assert unit_weight_label(SimpleNamespace(name=name, unit_weight_g=weight)) == expected
