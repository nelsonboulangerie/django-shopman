"""Vínculos usam a intenção canônica do produto e da célula."""
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from shopman.offerman.models import Collection, CollectionItem, ListingItem

from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
operator = fixtures.operator
shop = fixtures.shop
pytestmark = pytest.mark.django_db
URL = "/api/v1/backstage/catalog/product/PAO/"


def read(client, operator):
    client.force_login(operator)
    return client.get(URL).json()


def write(client, observed, patch, key=None):
    return client.patch(URL, {**observed["action"]["payload_schema"], "patch": patch},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or str(uuid4()))


def test_collections_revision_receipt_and_no_publication(client, operator, catalog):
    observed = read(client, operator)
    item = ListingItem.objects.get(product=catalog["pao"], listing__ref="web")
    before = (item.price_q, item.is_published, item.is_sellable)
    rows = [{"ref": "doces", "is_primary": True, "sort_order": 4}]
    key = str(uuid4())
    applied = write(client, observed, {"collections": rows}, key)
    assert applied.status_code == 200, applied.content
    assert applied.json()["product"]["collections"] == rows
    replay = write(client, observed, {"collections": rows}, key)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    stale = write(client, observed, {"collections": []})
    assert stale.status_code == 409
    assert stale.json()["conflicting_fields"] == ["collections"]
    # Campo independente continua podendo ser salvo com sua revisão observada.
    assert write(client, observed, {"storage_tip": "Guardar fechado"}).status_code == 200
    item.refresh_from_db()
    assert (item.price_q, item.is_published, item.is_sellable) == before
    assert client.patch(URL, {"patch": {"collections": []}}, content_type="application/json").status_code == 400


def test_invalid_collection_set_is_atomic(client, operator, catalog):
    Collection.objects.create(ref="outra", name="Outra")
    observed = read(client, operator)
    result = write(client, observed, {"collections": [
        {"ref": "doces", "is_primary": True, "sort_order": 0},
        {"ref": "outra", "is_primary": True, "sort_order": 1}]})
    assert result.status_code == 400
    assert not CollectionItem.objects.filter(product=catalog["pao"]).exists()
    assert write(client, observed, {"collections": [{"ref": "sumiu"}]}).status_code == 400
    assert not CollectionItem.objects.filter(product=catalog["pao"]).exists()


def test_collections_can_switch_primary_remove_and_reorder(client, operator, catalog):
    Collection.objects.create(ref="outra", name="Outra")
    for primary in ("doces", "outra"):
        observed = read(client, operator)
        rows = [{"ref": ref, "is_primary": ref == primary, "sort_order": index + 3}
            for index, ref in enumerate(["doces", "outra"])]
        assert write(client, observed, {"collections": rows}).status_code == 200
        assert CollectionItem.objects.get(product=catalog["pao"], is_primary=True).collection.ref == primary
    assert write(client, read(client, operator), {"collections": []}).status_code == 200
    assert not CollectionItem.objects.filter(product=catalog["pao"]).exists()


def test_listing_minimum_uses_cell_intention_and_conflicts(client, operator, catalog):
    observed = read(client, operator)
    link = next(row for row in observed["product"]["listing_links"] if row["surface_ref"] == "web")
    payload = link["action"]["payload_schema"]
    key = str(uuid4())
    body = {**payload, "min_qty": "2.500", "price_q": 777, "is_sellable": False}
    applied = client.post(fixtures.CELL_URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert applied.status_code == 200, applied.content
    item = ListingItem.objects.get(product=catalog["pao"], listing__ref="web")
    assert str(item.min_qty) == "2.500"
    assert item.price_q == 777 and not item.is_sellable
    replay = client.post(fixtures.CELL_URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert replay.status_code == 200
    conflict = client.post(fixtures.CELL_URL, {**payload, "min_qty": "3"}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert conflict.status_code == 409
    current = read(client, operator)["product"]["listing_links"][0]["action"]["payload_schema"]
    for value in ["0", "-1", "NaN", "1.0001"]:
        result = client.post(fixtures.CELL_URL, {**current, "min_qty": value}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        assert result.status_code == 400


def test_detail_queries_do_not_grow_with_links(client, operator, catalog):
    client.force_login(operator)
    # Aquecimento de caches e permissões fora da medição.
    client.get(URL)
    with CaptureQueriesContext(connection) as before:
        first = client.get(URL)
    for index in range(30):
        collection = Collection.objects.create(ref=f"c{index}", name=f"Coleção {index}")
        CollectionItem.objects.create(collection=collection, product=catalog["pao"])
    with CaptureQueriesContext(connection) as after:
        second = client.get(URL)
    assert len(second.json()["product"]["collections"]) == 30
    assert len(after) == len(before), f"Vínculos: {len(before)} -> {len(after)} consultas"
    print(f"LINKS QUERIES before={len(before)} after={len(after)} timing_before={first.headers.get('Server-Timing')} timing_after={second.headers.get('Server-Timing')}")


def test_missing_channel_link_created_once_with_observed_intention(client, operator, catalog):
    from shopman.shop.models import Channel

    Channel.objects.create(ref="counter", name="Balcão")
    observed = read(client, operator)
    link = next(row for row in observed["product"]["listing_links"] if row["surface_ref"] == "counter")
    assert link["is_published"] is False and link["is_sellable"] is False
    body = {**link["action"]["payload_schema"], "price_q": 650, "min_qty": "1"}
    key = str(uuid4())
    response = client.post(fixtures.CELL_URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 200, response.content
    response = client.post(fixtures.CELL_URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert response.status_code == 200
    assert ListingItem.objects.filter(product=catalog["pao"], listing__ref="counter").count() == 1
    # Outra intenção sobre o recorte ausente observado tem de conflitar.
    stale = client.post(fixtures.CELL_URL, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert stale.status_code == 409
    created = ListingItem.objects.get(product=catalog["pao"], listing__ref="counter")
    assert created.price_q == 650 and not created.is_published and not created.is_sellable


def test_collection_receipt_failure_rolls_back_membership(client, operator, catalog, monkeypatch):
    from shopman.orderman.models import IdempotencyKey

    observed = read(client, operator)
    original = IdempotencyKey.save
    def fail_receipt(self, *args, **kwargs):
        if self.response_body:
            raise RuntimeError("recibo indisponível")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(IdempotencyKey, "save", fail_receipt)
    with pytest.raises(RuntimeError, match="recibo indisponível"):
        write(client, observed, {"collections": [{"ref": "doces", "sort_order": 0, "is_primary": True}]})
    assert not CollectionItem.objects.filter(product=catalog["pao"]).exists()


def test_minimum_cannot_replace_another_tier(client, operator, catalog):
    item = ListingItem.objects.get(product=catalog["pao"], listing__ref="web")
    ListingItem.objects.create(product=item.product, listing=item.listing, price_q=400, min_qty=10)
    observed = read(client, operator)
    link = next(row for row in observed["product"]["listing_links"] if row["surface_ref"] == "web")
    response = client.post(fixtures.CELL_URL, {**link["action"]["payload_schema"], "min_qty": "10"},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert response.status_code == 400
    item.refresh_from_db()
    assert item.min_qty == 1



def test_collection_revision_is_checked_again_after_curation_locks(client, operator, catalog, monkeypatch):
    from shopman.backstage.services import catalog as service

    CollectionItem.objects.create(collection=catalog["coll"], product=catalog["pao"], sort_order=0)
    observed = read(client, operator)
    original = service._apply_product_collections
    def interleaved(product, rows, **kwargs):
        # Simula a ordenação canônica concluída entre a checagem inicial do
        # produto e a aquisição dos locks da curadoria.
        CollectionItem.objects.filter(product=product).update(sort_order=9)
        return original(product, rows, **kwargs)
    monkeypatch.setattr(service, "_apply_product_collections", interleaved)
    result = write(client, observed, {"collections": [{"ref": "doces", "sort_order": 3, "is_primary": True}]})
    assert result.status_code == 409
    assert result.json()["conflicting_fields"] == ["collections"]
