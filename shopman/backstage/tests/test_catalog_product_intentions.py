"""Product receipt shares the transaction; field disputes use real row locks."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import connection, connections
from django.test import Client
from shopman.orderman.models import IdempotencyKey

from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
shop = fixtures.shop
pytestmark = pytest.mark.django_db(transaction=True)
URL = fixtures.DETAIL_URL.format(sku="PAO")


@pytest.fixture(autouse=True)
def attribute_registry(db):
    from shopman.shop.attribute_defaults import ensure_definitions

    ensure_definitions()


@pytest.mark.parametrize("same_field", [True, False])
def test_concurrent_partial_product_intentions(operator, catalog, same_field):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL locks and independent connections")
    clients = [Client(), Client()]
    for client in clients:
        client.force_login(operator)
    observed = clients[0].get(URL).json()["action"]["payload_schema"]
    patches = [{"name": "First"}, {"name": "Second"} if same_field else {"storage_tip": "Fresh"}]
    barrier = Barrier(2)

    def worker(index):
        try:
            barrier.wait(timeout=5)
            return clients[index].patch(URL, {**observed, "patch": patches[index]},
                content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(worker, range(2)))
    assert sorted(codes) == ([200, 409] if same_field else [200, 200])
    catalog["pao"].refresh_from_db()
    if not same_field:
        assert catalog["pao"].name == "First"
        assert catalog["pao"].storage_tip == "Fresh"


def test_product_receipt_storage_failure_rolls_back_product(client, operator, catalog, monkeypatch):
    client.force_login(operator)
    body = {**client.get(URL).json()["action"]["payload_schema"], "patch": {"name": "After"}}
    original = IdempotencyKey.save

    def fail_receipt(self, *args, **kwargs):
        if self.response_body:
            raise RuntimeError("synthetic receipt failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(IdempotencyKey, "save", fail_receipt)
    with pytest.raises(RuntimeError, match="synthetic receipt failure"):
        client.patch(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    catalog["pao"].refresh_from_db()
    assert catalog["pao"].name == "Pão"


def test_product_receipt_remains_readable_when_projection_fails(client, operator, catalog, monkeypatch):
    from shopman.backstage.api.catalog import CatalogProductDetailView

    client.force_login(operator)
    body = {**client.get(URL).json()["action"]["payload_schema"], "patch": {"name": "Committed before read outage"}}
    key = str(uuid4())

    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic product projection outage")

    monkeypatch.setattr(CatalogProductDetailView, "_read", unavailable)
    client.raise_request_exception = False
    response = client.patch(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 500
    catalog["pao"].refresh_from_db()
    assert catalog["pao"].name == "Committed before read outage"
    receipt = client.get(URL, {"idempotency_key": key})
    assert receipt.status_code == 200
    assert receipt.json()["outcome"] == "applied"
    assert IdempotencyKey.objects.filter(key=key, status="done").count() == 1


@pytest.mark.parametrize("field", ["nutrition_facts", "allergens"])
def test_source_change_conflicts_even_when_observed_value_is_equal(client, operator, catalog, field):
    from shopman.offerman.models import Product

    from shopman.shop.services import attributes

    product = catalog["pao"]
    if field == "nutrition_facts":
        facts = {"serving_size_g": 50, "energy_kcal": 120, "auto_filled": True}
        Product.objects.filter(pk=product.pk).update(nutrition_facts=facts)
        patch = {"nutrition_facts": {"sodium_mg": 25}}
    else:
        attributes.set(product, "alergenos", ["leite"], source="recipe")
        attributes.set(product, "dieta", ["100% vegetal"], source="recipe")
        patch = {"allergens": ["glúten"]}
    client.force_login(operator)
    before = client.get(URL).json()
    if field == "nutrition_facts":
        Product.objects.filter(pk=product.pk).update(nutrition_facts={**facts, "auto_filled": False})
    else:
        product.refresh_from_db()
        attributes.set(product, "alergenos", ["leite"], source="manual")
        assert client.get(URL).json()["product"]["dietary_from_recipe"] is True  # the other label still derives
    response = client.patch(URL, {**before["action"]["payload_schema"], "patch": patch},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 409
    product.refresh_from_db()
    if field == "nutrition_facts":
        assert product.nutrition_facts == {**facts, "auto_filled": False}
    else:
        assert attributes.get(product, "alergenos") == ["leite"]
