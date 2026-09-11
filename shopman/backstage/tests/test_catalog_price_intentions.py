"""Canonical prices and local receipts under replay, conflict and enqueue failure."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import connection, connections
from django.test import Client
from shopman.offerman.models import ListingItem
from shopman.orderman.models import Directive, IdempotencyKey

from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
shop = fixtures.shop

pytestmark = pytest.mark.django_db(transaction=True)
URL = "/api/v1/backstage/catalog/bulk-price/"


def intent(client, operator, **overrides):
    client.force_login(operator)
    data = {"surface_ref": "*", "skus": ["PAO"], "op": "pct", "value": 10, **overrides}
    response = client.post(URL, {**data, "preview": True}, content_type="application/json")
    assert response.status_code == 200
    preview = response.json()["preview"]
    return {**data, "base_revision": preview["base_revision"], "expected_actor_id": preview["expected_actor_id"]}


def prices():
    return dict(ListingItem.objects.filter(product__sku="PAO").values_list("listing__ref", "price_q"))


def test_replay_and_lookup_never_reapply_percentage(client, operator, catalog):
    body = intent(client, operator)
    key = str(uuid4())
    first = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 200
    applied = prices()
    receipt = client.get(URL, {"idempotency_key": key})
    replay = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert receipt.json() == replay.json() == first.json()
    assert prices() == applied
    divergent = client.post(URL, {**body, "value": 20}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert divergent.status_code == 409
    assert prices() == applied


def test_changed_price_refuses_every_destination(client, operator, catalog):
    body = intent(client, operator)
    ListingItem.objects.filter(listing__ref="ifood", product__sku="PAO").update(price_q=999)
    before = prices()
    response = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 409
    assert prices() == before


def test_failed_second_enqueue_rolls_back_all_prices_and_receipt(client, operator, catalog, monkeypatch):
    from shopman.offerman import conf

    from shopman.shop.handlers import catalog_projection

    body = intent(client, operator)
    before = prices()
    monkeypatch.setattr(conf, "get_projection_backend", lambda _ref: object())
    calls = []

    def enqueue(sku, listing_ref, **kwargs):
        calls.append(listing_ref)
        if len(calls) == 2:
            raise RuntimeError("second enqueue failed")
        Directive.objects.create(topic="lab.sync", payload={"sku": sku, "listing_ref": listing_ref})

    monkeypatch.setattr(catalog_projection, "enqueue_project", enqueue)
    key = str(uuid4())
    with pytest.raises(RuntimeError, match="second enqueue failed"):
        client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert prices() == before
    assert not Directive.objects.filter(topic="lab.sync").exists()
    assert not IdempotencyKey.objects.filter(key=key).exists()


def test_two_distinct_intentions_on_same_preview_apply_once(operator, catalog):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL locks and independent connections")
    clients = [Client(), Client()]
    body = intent(clients[0], operator)
    clients[1].force_login(operator)
    barrier = Barrier(2)

    def worker(client):
        try:
            barrier.wait(timeout=5)
            return client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(worker, clients))
    assert sorted(codes) == [200, 409]
    assert prices()["web"] == 660


def test_legacy_client_and_other_person_cannot_apply_or_replay(client, operator, catalog, django_user_model):
    body = intent(client, operator)
    before = prices()
    assert client.post(URL, body, content_type="application/json").status_code == 400
    key = str(uuid4())
    assert client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code == 200
    other = django_user_model.objects.create_user(username="other", is_staff=True)
    client.force_login(other)
    assert client.get(URL, {"idempotency_key": key}).status_code == 403
    other.user_permissions.set(operator.user_permissions.all())
    assert client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code == 409
    assert client.get(URL, {"idempotency_key": key}).json()["outcome"] == "unknown"
    assert prices()["web"] == int(before["web"] * 1.1)


def test_limit_counts_destination_cells_and_keeps_tiers_explicit(client, operator, catalog):
    from shopman.offerman.models import Listing, Product

    from shopman.backstage.services.catalog import MAX_BULK_PRICE_CELLS

    client.force_login(operator)
    products = Product.objects.bulk_create([Product(sku=f"LIMIT-{i}", name=f"Limit {i}", unit="un") for i in range(MAX_BULK_PRICE_CELLS // 2 + 1)])
    listings = list(Listing.objects.filter(ref__in=["web", "ifood"]))
    ListingItem.objects.bulk_create([ListingItem(product=product, listing=listing, price_q=100) for product in products for listing in listings])
    response = client.post(URL, {"surface_ref": "*", "skus": [product.sku for product in products], "op": "pct", "value": 10, "preview": True}, content_type="application/json")
    assert response.status_code == 400
    assert str(MAX_BULK_PRICE_CELLS) in response.json()["detail"]
    assert set(ListingItem.objects.filter(product__in=products).values_list("price_q", flat=True)) == {100}


def test_receipt_storage_failure_rolls_back_prices(client, operator, catalog, monkeypatch):
    body = intent(client, operator)
    before = prices()
    original = IdempotencyKey.save

    def fail_receipt(instance, *args, **kwargs):
        if instance.status == "done" and (instance.response_body or {}).get("contract") == "local-mutation-v1":
            raise RuntimeError("receipt storage failed")
        return original(instance, *args, **kwargs)

    monkeypatch.setattr(IdempotencyKey, "save", fail_receipt)
    with pytest.raises(RuntimeError, match="receipt storage failed"):
        client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert prices() == before


def test_collection_membership_change_requires_new_preview(client, operator, catalog):
    from shopman.offerman.models import Collection, CollectionItem, Product
    body = intent(client, operator, collection_ref="doces")
    CollectionItem.objects.create(collection=Collection.objects.get(ref="doces"), product=Product.objects.get(sku="PAO"))
    before = prices()
    response = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 409
    assert prices() == before
