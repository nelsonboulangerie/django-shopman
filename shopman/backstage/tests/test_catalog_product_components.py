"""Composição do combo usa o mesmo escritor versionado do produto."""

from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Product, ProductComponent

from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
shop = fixtures.shop
pytestmark = pytest.mark.django_db
URL = "/api/v1/backstage/catalog/product/PAO/"


def observe(client, operator):
    client.force_login(operator)
    return client.get(URL).json()


def apply(client, observed, rows, key=None, **patch):
    return client.patch(
        URL,
        {**observed["action"]["payload_schema"], "patch": {"components": rows, **patch}},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
    )


def test_component_read_query_count_is_constant(client, operator, catalog):
    client.force_login(operator)
    client.get(URL)
    with CaptureQueriesContext(connection) as small:
        before = client.get(URL)
    extra = Product.objects.bulk_create(
        [Product(sku=f"COMP{i}", name=f"Componente {i}", base_price_q=100) for i in range(60)]
    )
    ProductComponent.objects.bulk_create([ProductComponent(parent=catalog["pao"], component=p, qty=1) for p in extra])
    with CaptureQueriesContext(connection) as large:
        after = client.get(URL)
    print("COMPONENTS_READ", len(small), len(large), before["Server-Timing"], after["Server-Timing"])
    assert before.status_code == after.status_code == 200
    assert len(after.json()["product"]["components"]) == 60
    assert len(small) == len(large), "Ler a composição não pode consultar cada componente separadamente."


def test_components_use_product_intention_revision_and_receipt(client, operator, catalog):
    observed = observe(client, operator)
    assert observed["product"]["components"] == []
    rows = [{"sku": "BOLO", "qty": "1.250"}]
    key = str(uuid4())
    response = apply(client, observed, rows, key)
    assert response.status_code == 200, response.content
    component = response.json()["product"]["components"][0]
    assert component == {"sku": "BOLO", "name": "Bolo", "unit": "un", "qty": "1.250"}
    assert apply(client, observed, rows, key).json()["replayed"] is True
    stale = apply(client, observed, [])
    assert stale.status_code == 409
    assert stale.json()["conflicting_fields"] == ["components"]
    # Token de outro campo não é invalidado pela composição.
    independent = client.patch(
        URL,
        {**observed["action"]["payload_schema"], "patch": {"storage_tip": "Guardar fechado"}},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert independent.status_code == 200
    assert client.patch(URL, {"patch": {"components": []}}, content_type="application/json").status_code == 400


@pytest.mark.parametrize(
    "rows",
    [[{"sku": "BOLO", "qty": value}] for value in ["0", "-1", "NaN", "1.0001", "10000000", True]]
    + [[{"sku": "sumiu", "qty": "1"}], [{"sku": "BOLO", "qty": "1"}, {"sku": "BOLO", "qty": "2"}]],
)
def test_invalid_composition_cannot_change_the_product(client, operator, catalog, rows):
    response = apply(client, observe(client, operator), rows)
    assert response.status_code == 400
    assert not ProductComponent.objects.filter(parent=catalog["pao"]).exists()


def test_self_cycle_and_failed_replacement_are_atomic(client, operator, catalog):
    ProductComponent.objects.create(parent=catalog["pao"], component=catalog["bolo"], qty=2)
    third = Product.objects.create(sku="TERCEIRO", name="Terceiro", base_price_q=100)
    response = apply(
        client,
        observe(client, operator),
        [{"sku": third.sku, "qty": "1"}, {"sku": "PAO", "qty": "1"}],
        name="Não aplicar",
    )
    assert response.status_code == 400
    assert "si mesmo" in response.json()["detail"]
    assert list(ProductComponent.objects.filter(parent=catalog["pao"]).values_list("component__sku", "qty")) == [
        ("BOLO", 2)
    ]
    catalog["pao"].refresh_from_db()
    assert catalog["pao"].name == "Pão"


def test_indirect_cycle_uses_core_validation(client, operator, catalog):
    ProductComponent.objects.create(parent=catalog["bolo"], component=catalog["pao"], qty=1)
    response = apply(client, observe(client, operator), [{"sku": "BOLO", "qty": "1"}])
    assert response.status_code == 400
    assert "ciclo" in response.json()["detail"]
    assert not ProductComponent.objects.filter(parent=catalog["pao"]).exists()


def test_depth_limit_uses_core_configuration(client, operator, catalog, settings):
    settings.OFFERMAN = {"BUNDLE_MAX_DEPTH": 2}
    third = Product.objects.create(sku="TERCEIRO", name="Terceiro", base_price_q=100)
    ProductComponent.objects.create(parent=catalog["bolo"], component=third, qty=1)
    response = apply(client, observe(client, operator), [{"sku": "BOLO", "qty": "1"}])
    assert response.status_code == 400
    assert "níveis" in response.json()["detail"]


def test_composition_records_projection_before_commit(
    client, operator, catalog, monkeypatch, django_capture_on_commit_callbacks
):
    from unittest.mock import Mock

    from shopman.offerman.signals import product_updated

    from shopman.shop.handlers import _sse_emitters

    observed = observe(client, operator)
    updated, sse = Mock(), Mock()
    monkeypatch.setattr(product_updated, "send", updated)
    monkeypatch.setattr(_sse_emitters, "emit_catalog_changed", sse)
    with django_capture_on_commit_callbacks(execute=True):
        response = apply(client, observed, [{"sku": "BOLO", "qty": "1"}])
        assert response.status_code == 200
        updated.assert_called_once()
    updated.assert_called_once()
    sse.assert_called_once()


def test_product_search_is_light_bounded_and_filters_archived(client, operator, catalog):
    client.force_login(operator)
    options = "/api/v1/backstage/catalog/products/options/"
    Product.objects.create(sku="ARQUIVADO", name="Pão arquivado", base_price_q=100, is_active=False)
    response = client.get(options, {"q": "PAO"})
    assert response.status_code == 200
    assert [row["sku"] for row in response.json()["products"]] == ["PAO"]
    assert "projection;dur=" in response["Server-Timing"]
    Product.objects.bulk_create([Product(sku=f"OPT{i}", name=f"Opção {i}", base_price_q=100) for i in range(30)])
    response = client.get(options, {"q": "OPT"})
    assert len(response.json()["products"]) == 20
    assert response.json()["has_next"] is True
    assert client.get(options, {"q": "não existe"}).json()["products"] == []


def test_outbox_failure_rolls_back_components_and_receipt(client, operator, catalog, monkeypatch):
    from shopman.offerman.signals import product_updated
    from shopman.orderman.models import IdempotencyKey

    observed = observe(client, operator)
    key = str(uuid4())

    def fail(*args, **kwargs):
        raise RuntimeError("outbox unavailable")

    monkeypatch.setattr(product_updated, "send", fail)
    with pytest.raises(RuntimeError, match="outbox unavailable"):
        apply(client, observed, [{"sku": "BOLO", "qty": "1"}], key)
    assert not ProductComponent.objects.filter(parent=catalog["pao"]).exists()
    assert not IdempotencyKey.objects.filter(key=key).exists()


def test_renaming_a_component_does_not_invalidate_composition_revision(client, operator, catalog):
    ProductComponent.objects.create(parent=catalog["pao"], component=catalog["bolo"], qty=1)
    observed = observe(client, operator)
    Product.objects.filter(pk=catalog["bolo"].pk).update(name="Bolo novo")
    response = apply(client, observed, [{"sku": "BOLO", "qty": "2"}])
    assert response.status_code == 200
    assert response.json()["product"]["components"][0]["name"] == "Bolo novo"


def test_component_unit_change_conflicts_with_observed_quantity(client, operator, catalog):
    ProductComponent.objects.create(parent=catalog["pao"], component=catalog["bolo"], qty=1)
    observed = observe(client, operator)
    Product.objects.filter(pk=catalog["bolo"].pk).update(unit="kg")
    response = apply(client, observed, [{"sku": "BOLO", "qty": "2"}])
    assert response.status_code == 409
    assert response.json()["conflicting_fields"] == ["components"]
    assert ProductComponent.objects.get(parent=catalog["pao"]).qty == 1


def test_combo_unit_change_conflicts_with_observed_composition(client, operator, catalog):
    ProductComponent.objects.create(parent=catalog["pao"], component=catalog["bolo"], qty=1)
    observed = observe(client, operator)
    Product.objects.filter(pk=catalog["pao"].pk).update(unit="kg")
    response = apply(client, observed, [{"sku": "BOLO", "qty": "2"}])
    assert response.status_code == 409
    assert response.json()["conflicting_fields"] == ["components"]
    assert ProductComponent.objects.get(parent=catalog["pao"]).qty == 1
