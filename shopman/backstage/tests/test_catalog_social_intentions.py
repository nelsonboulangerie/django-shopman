"""The social route shares product field revisions, merge and receipt."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import connection, connections
from django.test import Client

from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
shop = fixtures.shop
pytestmark = pytest.mark.django_db(transaction=True)
URL = fixtures.SOCIAL_URL


@pytest.fixture(autouse=True)
def attribute_registry(db):
    from shopman.shop.attribute_defaults import ensure_definitions

    ensure_definitions()


def test_old_social_payload_cannot_bypass_revision(client, operator, catalog):
    client.force_login(operator)
    before = dict(catalog["pao"].metadata)
    response = client.post(URL, {"sku": "PAO", "brand": "Stale social writer"}, content_type="application/json")
    catalog["pao"].refresh_from_db()
    assert catalog["pao"].metadata == before
    assert response.status_code == 400


def test_social_replay_uses_product_receipt_and_cannot_restore_old_brand(client, operator, catalog):
    client.force_login(operator)
    before = client.get(URL, {"sku": "PAO"}).json()
    body = {**before["action"]["payload_schema"], "sku": "PAO", "patch": {"social": {"brand": "First"}}}
    key = str(uuid4())
    response = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 200
    assert response.json()["social"]["brand"] == "First"
    detail_url = fixtures.DETAIL_URL.format(sku="PAO")
    current = client.get(detail_url).json()
    assert client.patch(detail_url, {**current["action"]["payload_schema"], "patch": {"social": {"brand": "Later"}}},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code == 200
    assert client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code == 200
    assert client.get(detail_url, {"idempotency_key": key}).json()["outcome"] == "applied"
    assert client.get(URL, {"sku": "PAO"}).json()["social"]["brand"] == "Later"


def test_social_and_detail_writers_merge_independent_fields(operator, catalog):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL locks and independent connections")
    clients = [Client(), Client()]
    for client in clients:
        client.force_login(operator)
    seen = clients[0].get(URL, {"sku": "PAO"}).json()["action"]["payload_schema"]
    barrier = Barrier(2)

    def worker(index):
        try:
            barrier.wait(timeout=5)
            if index == 0:
                return clients[index].post(URL, {**seen, "sku": "PAO", "patch": {"social": {"brand": "Brand"}}},
                    content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code
            return clients[index].patch(fixtures.DETAIL_URL.format(sku="PAO"), {**seen, "patch": {"social": {"hashtags": ["pao"]}}},
                content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(worker, range(2))) == [200, 200]
    actual = clients[0].get(URL, {"sku": "PAO"}).json()["social"]
    assert actual["brand"] == "Brand"
    assert actual["hashtags"] == ["pao"]


def test_social_only_edit_preserves_legacy_label_validation_scope(client, operator, catalog):
    from shopman.offerman.models import Product

    Product.objects.filter(pk=catalog["pao"].pk).update(nutrition_facts={"serving_size_g": 0, "proteins_g": 4})
    client.force_login(operator)
    read = client.get(URL, {"sku": "PAO"}).json()
    response = client.post(URL, {**read["action"]["payload_schema"], "sku": "PAO", "patch": {"social": {"brand": "Catalog brand"}}},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 200
    catalog["pao"].refresh_from_db()
    assert catalog["pao"].nutrition_facts == {"serving_size_g": 0, "proteins_g": 4}
    assert catalog["pao"].metadata["social"]["brand"] == "Catalog brand"
