"""Publication decisions retain their exact preview and cannot replay over a later edit."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import connection, connections
from django.test import Client
from shopman.offerman.models import CollectionItem, ListingItem
from shopman.orderman.models import Directive, IdempotencyKey

from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
shop = fixtures.shop
pytestmark = pytest.mark.django_db(transaction=True)
URL = fixtures.BULK_URL


def preview(client, operator, **override):
    client.force_login(operator)
    data = {"surface_ref": "*", "skus": ["PAO"], "is_sellable": False, **override}
    response = client.post(URL, {**data, "preview": True}, content_type="application/json")
    assert response.status_code == 200
    return data, response.json()["preview"]


def intent(data, seen):
    return {**data, "base_revision": seen["base_revision"], "expected_actor_id": seen["expected_actor_id"]}


def flags():
    return list(ListingItem.objects.order_by("pk").values_list("pk", "is_published", "is_sellable"))


def test_preview_lists_every_tier_without_writing(client, operator, catalog):
    first = ListingItem.objects.get(product__sku="PAO", listing__ref="web")
    ListingItem.objects.create(product=first.product, listing=first.listing, min_qty=10, price_q=400)
    before = flags()
    data, seen = preview(client, operator)
    assert flags() == before
    assert len(seen["cells"]) == 3
    assert {cell["tier"] for cell in seen["cells"]} == {"1.000", "10.000"}
    assert all(cell["before"]["is_sellable"] is True and cell["after"]["is_sellable"] is False for cell in seen["cells"])


def test_receipt_replay_does_not_pause_later_activation(client, operator, catalog):
    data, seen = preview(client, operator)
    body, key = intent(data, seen), str(uuid4())
    first = client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 200
    ListingItem.objects.filter(product__sku="PAO").update(is_sellable=True)
    before = flags()
    assert client.post(URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).json() == first.json()
    assert client.get(URL, {"idempotency_key": key}).json() == first.json()
    assert flags() == before
    assert client.post(URL, {**body, "is_sellable": True}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code == 409


def test_changed_membership_refuses_entire_selection(client, operator, catalog):
    data, seen = preview(client, operator, skus=None, collection_ref="doces")
    CollectionItem.objects.create(collection=catalog["coll"], product=catalog["pao"])
    before = flags()
    response = client.post(URL, intent(data, seen), content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 409
    assert flags() == before


def test_old_client_cannot_write(client, operator, catalog):
    client.force_login(operator)
    before = flags()
    assert client.post(URL, {"surface_ref": "*", "skus": ["PAO"], "is_sellable": False}, content_type="application/json").status_code == 400
    assert flags() == before


def test_distinct_intentions_compete_on_observed_publication(operator, catalog):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL locks and independent connections")
    clients = [Client(), Client()]
    data, seen = preview(clients[0], operator)
    clients[1].force_login(operator)
    barrier = Barrier(2)

    def worker(client):
        try:
            barrier.wait(timeout=5)
            return client.post(URL, intent(data, seen), content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(worker, clients)) == [200, 409]


def test_second_enqueue_failure_rolls_back_flags_and_receipt(client, operator, catalog, monkeypatch):
    from shopman.offerman import conf

    from shopman.shop.handlers import catalog_projection

    data, seen = preview(client, operator)
    before = flags()
    monkeypatch.setattr(conf, "get_projection_backend", lambda _ref: object())
    calls = []

    def enqueue(sku, listing_ref, **kwargs):
        calls.append(listing_ref)
        if len(calls) == 2:
            raise RuntimeError("second publication enqueue failed")
        Directive.objects.create(topic="lab.publication", payload={"sku": sku, "listing_ref": listing_ref})

    monkeypatch.setattr(catalog_projection, "enqueue_project", enqueue)
    key = str(uuid4())
    with pytest.raises(RuntimeError, match="second publication enqueue failed"):
        client.post(URL, intent(data, seen), content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert flags() == before
    assert not Directive.objects.filter(topic="lab.publication").exists()
    assert not IdempotencyKey.objects.filter(key=key).exists()


def test_channel_created_after_snapshot_cannot_join_all_channel_intention(client, operator, catalog, monkeypatch):
    from shopman.offerman.models import Listing

    from shopman.backstage.services import catalog as service
    from shopman.shop.models import Channel

    data, seen = preview(client, operator)
    original = service.bulk_set
    inserted = []

    def concurrent_channel(skus, ref, **kwargs):
        if not inserted:
            Channel.objects.create(ref="new-channel", name="New", is_active=True)
            listing = Listing.objects.create(ref="new-channel", name="New")
            inserted.append(ListingItem.objects.create(listing=listing, product=catalog["pao"], price_q=500))
        return original(skus, ref, **kwargs)

    monkeypatch.setattr(service, "bulk_set", concurrent_channel)
    response = client.post(URL, intent(data, seen), content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 200
    inserted[0].refresh_from_db()
    assert inserted[0].is_sellable
    assert {cell["surface_ref"] for cell in response.json()["cells"]} == {"web", "ifood"}


def test_display_preview_skips_outside_membership_and_never_creates_price(client, operator, catalog):
    from shopman.shop.tests._display import display_channel

    display = display_channel("tv", "TV", collections=["doces"], prices_from="web")
    data, seen = preview(client, operator, surface_ref="tv", skus=["PAO", "BOLO"])
    assert [cell["sku"] for cell in seen["cells"]] == ["BOLO"]
    assert seen["skipped"][0]["sku"] == "PAO"
    before = ListingItem.objects.count()
    response = client.post(URL, intent(data, seen), content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 200
    display.refresh_from_db()
    assert display.config["display"]["paused_skus"] == ["BOLO"]
    assert ListingItem.objects.count() == before
    assert client.post(URL, {**data, "preview": True, "is_published": False}, content_type="application/json").status_code == 400


def test_other_person_cannot_apply_preview_or_read_receipt(client, operator, catalog, django_user_model):
    data, seen = preview(client, operator)
    key = str(uuid4())
    assert client.post(URL, intent(data, seen), content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code == 200
    other = django_user_model.objects.create_user("publication-other", is_staff=True)
    other.user_permissions.set(operator.user_permissions.all())
    client.force_login(other)
    assert client.get(URL, {"idempotency_key": key}).status_code == 202
    assert client.post(URL, intent(data, seen), content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code == 409
