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
