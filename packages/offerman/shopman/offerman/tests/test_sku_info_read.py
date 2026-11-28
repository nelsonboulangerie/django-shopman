"""A leitura enxuta mantém todo o contrato do validador, inclusive estados ocultos."""

from dataclasses import asdict
from itertools import product as combinations

import pytest
from shopman.offerman.adapters.sku_validator import SkuValidator
from shopman.offerman.models import Collection, CollectionItem, Product

pytestmark = pytest.mark.django_db


def test_sku_info_preserves_every_field_and_state(django_assert_num_queries):
    primary = Collection.objects.create(ref="primary", name="Primária inativa", is_active=False)
    secondary = Collection.objects.create(ref="secondary", name="Secundária")
    expected = {}
    for index, (active, published, sellable) in enumerate(combinations((False, True), repeat=3)):
        product = Product.objects.create(
            sku=f"INFO-{index}", name=f"Produto {index}", long_description=f"Descrição {index}",
            is_active=active, is_published=published, is_sellable=sellable,
            unit="kg", base_price_q=1234, availability_policy="demand_ok", shelf_life_days=index,
        )
        CollectionItem.objects.create(product=product, collection=secondary, sort_order=0)
        if index % 2:
            CollectionItem.objects.create(product=product, collection=primary, is_primary=True, sort_order=10)
        expected[product.sku] = {
            "sku": product.sku, "name": product.name, "description": product.long_description,
            "is_published": active and published, "is_sellable": active and sellable,
            "unit": "kg", "category": primary.name if index % 2 else None,
            "base_price_q": 1234, "availability_policy": "demand_ok", "shelflife_days": index,
            "metadata": None,
        }
    orphan = Product.objects.create(sku="NO-COLLECTION", name="Sem coleção")
    validator = SkuValidator()
    skus = [*expected, orphan.sku, "UNKNOWN", "INFO-0"]
    with django_assert_num_queries(1):
        result = validator.get_sku_infos(skus)
    assert list(result) == list(dict.fromkeys(skus))
    assert {sku: asdict(result[sku]) for sku in expected} == expected
    assert result[orphan.sku].category is None
    assert result["UNKNOWN"] is None
    for sku in result:
        with django_assert_num_queries(1):
            assert validator.get_sku_info(sku) == result[sku]


def test_empty_sku_info_does_not_query(django_assert_num_queries):
    with django_assert_num_queries(0):
        assert SkuValidator().get_sku_infos([]) == {}
