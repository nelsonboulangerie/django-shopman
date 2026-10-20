"""Busca, ordenação e paginação do Compras acontecem antes da projeção."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.buyman.models import Material, Supplier

from shopman.backstage.projections.purchase import build_purchase

pytestmark = pytest.mark.django_db


def _materials(count: int, prefix: str) -> None:
    Material.objects.bulk_create(
        [Material(sku=f"{prefix}-{index:04d}", name=f"{prefix} {index:04d}", unit="kg") for index in range(count)]
    )


def test_query_count_is_constant_for_five_and_five_hundred_materials():
    _materials(5, "CINCO")
    with CaptureQueriesContext(connection) as five:
        first = build_purchase(paginate=True, page_size=5, query="CINCO")

    _materials(500, "MUITOS")
    with CaptureQueriesContext(connection) as five_hundred:
        second = build_purchase(paginate=True, page_size=5, query="MUITOS")

    assert first.materials.total == 5
    assert second.materials.total == 500
    assert len(second.materials.items) == 5
    assert len(five_hundred.captured_queries) == len(five.captured_queries), (
        len(five.captured_queries),
        len(five_hundred.captured_queries),
    )


def test_search_order_and_page_are_database_side():
    _materials(12, "PAGINA")
    result = build_purchase(
        paginate=True,
        query="PAGINA",
        order="-name",
        page=2,
        page_size=5,
    )

    assert result.materials.total == 12
    assert result.materials.page == 2
    assert result.materials.has_next is True
    assert [item.name for item in result.materials.items] == [
        "PAGINA 0006",
        "PAGINA 0005",
        "PAGINA 0004",
        "PAGINA 0003",
        "PAGINA 0002",
    ]


def test_page_outside_range_is_empty_and_coherent():
    _materials(3, "CURTA")
    result = build_purchase(paginate=True, query="CURTA", page=9, page_size=2)

    assert result.materials.items == ()
    assert result.materials.total == 3
    assert result.materials.page == 9
    assert result.materials.has_next is False


def test_material_category_and_supplier_status_filters_run_before_pagination():
    Material.objects.create(
        sku="CACAU",
        name="Cacau",
        unit="kg",
        metadata={"purchase": {"category": "Chocolate"}},
    )
    Material.objects.create(
        sku="FARINHA",
        name="Farinha",
        unit="kg",
        metadata={"purchase": {"category": "Farinhas"}},
    )
    Supplier.objects.create(ref="ativo", name="Ativo", is_active=True)
    Supplier.objects.create(ref="inativo", name="Inativo", is_active=False)

    result = build_purchase(
        paginate=True,
        page_size=1,
        material_filters={"category": ["Chocolate"]},
        supplier_filters={"status": ["inactive"]},
    )

    assert result.materials.total == 1
    assert result.materials.items[0].sku == "CACAU"
    assert result.suppliers.total == 1
    assert result.suppliers.items[0].ref == "inativo"
