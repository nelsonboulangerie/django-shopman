"""Busca, ordenação e paginação do Compras acontecem antes da projeção."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.buyman.models import Material, Supplier, SupplierContact

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


def test_default_lists_hide_archived_materials_and_suppliers():
    Material.objects.create(sku="ATIVO", name="Ativo", unit="kg", is_active=True)
    Material.objects.create(sku="ARQUIVADO", name="Arquivado", unit="kg", is_active=False)
    Supplier.objects.create(ref="em-uso", name="Em uso", is_active=True)
    Supplier.objects.create(ref="arquivado", name="Arquivado", is_active=False)

    result = build_purchase(paginate=True)

    assert result.materials.total == 1
    assert [item.sku for item in result.materials.items] == ["ATIVO"]
    assert result.suppliers.total == 1
    assert [item.ref for item in result.suppliers.items] == ["em-uso"]


def test_archived_filters_return_only_archived_before_pagination():
    Material.objects.create(sku="ATIVO", name="Ativo", unit="kg", is_active=True)
    Material.objects.create(sku="ARQUIVADO", name="Arquivado", unit="kg", is_active=False)
    Supplier.objects.create(ref="em-uso", name="Em uso", is_active=True)
    Supplier.objects.create(ref="arquivado", name="Arquivado", is_active=False)

    result = build_purchase(
        paginate=True,
        material_filters={"archive": ["archived"]},
        supplier_filters={"archive": ["archived"]},
    )

    assert result.materials.total == 1
    assert [item.sku for item in result.materials.items] == ["ARQUIVADO"]
    assert result.materials.items[0].isActive is False
    assert result.suppliers.total == 1
    assert [item.ref for item in result.suppliers.items] == ["arquivado"]
    assert result.suppliers.items[0].isActive is False


def test_archived_filter_does_not_add_queries():
    Material.objects.create(sku="ATIVO", name="Ativo", unit="kg", is_active=True)
    Material.objects.create(sku="ARQUIVADO", name="Arquivado", unit="kg", is_active=False)
    Supplier.objects.create(ref="em-uso", name="Em uso", is_active=True)
    Supplier.objects.create(ref="arquivado", name="Arquivado", is_active=False)

    with CaptureQueriesContext(connection) as current:
        build_purchase(paginate=True)
    with CaptureQueriesContext(connection) as archived:
        build_purchase(
            paginate=True,
            material_filters={"archive": ["archived"]},
            supplier_filters={"archive": ["archived"]},
        )

    assert len(archived) == len(current)


def test_material_category_and_supplier_contact_filters_run_before_pagination():
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
    commercial = Supplier.objects.create(ref="com-contato", name="Com contato")
    SupplierContact.objects.create(
        supplier=commercial, name="Ana", role="sales", email="compras@example.test",
    )
    Supplier.objects.create(ref="sem-contato", name="Sem contato")

    result = build_purchase(
        paginate=True,
        page_size=1,
        material_filters={"category": ["Chocolate"]},
        supplier_filters={"contact": ["without"]},
    )

    assert result.materials.total == 1
    assert result.materials.items[0].sku == "CACAU"
    assert result.suppliers.total == 1
    assert result.suppliers.items[0].ref == "sem-contato"


def test_commercial_filter_matches_the_contact_shown_in_the_supplier_card():
    for ref, role, active, primary in (
        ("sales", "sales", True, False),
        ("general", "general", True, False),
        ("finance", "finance", True, True),
        ("inactive", "sales", False, False),
    ):
        supplier = Supplier.objects.create(ref=ref, name=ref)
        SupplierContact.objects.create(
            supplier=supplier, name=ref, role=role, is_active=active,
            is_primary=primary, email=f"{ref}@example.test",
        )
    Supplier.objects.create(ref="central", name="Central", email="central@example.test")
    Supplier.objects.create(ref="empty", name="Empty")

    all_suppliers = build_purchase().suppliers
    expected = {item.ref for item in all_suppliers if item.orderContactName}
    assert expected == {"sales", "general"}
    for value, refs in (("with", expected), ("without", {"central", "empty", "finance", "inactive"})):
        result = build_purchase(paginate=True, supplier_filters={"contact": [value]})
        assert result.suppliers.total == len(refs)
        assert {item.ref for item in result.suppliers.items} == refs

    both = build_purchase(paginate=True, supplier_filters={"contact": ["with", "without"]})
    assert both.suppliers.total == 6
