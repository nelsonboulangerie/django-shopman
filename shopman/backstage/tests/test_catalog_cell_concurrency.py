"""Different cell fields must survive overlapping canonical facade writers."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.db import connection, connections
from shopman.offerman.models import ListingItem

from shopman.backstage.services import catalog as service
from shopman.backstage.tests import test_api_catalog_surface as fixtures

catalog = fixtures.catalog
pytestmark = pytest.mark.django_db(transaction=True)


def test_price_and_pause_do_not_overwrite_each_other(catalog, monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL locks and independent connections")
    price_loaded, pause_attempted = Event(), Event()
    original = ListingItem.save

    def controlled_save(self, *args, **kwargs):
        if self.price_q == 777 and self.is_sellable:
            price_loaded.set()
            pause_attempted.wait(1)
        elif not self.is_sellable:
            pause_attempted.set()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ListingItem, "save", controlled_save)

    def price():
        try:
            service.set_cell("PAO", "web", price_q=777)
        finally:
            connections.close_all()

    def pause():
        try:
            assert price_loaded.wait(5)
            service.set_cell("PAO", "web", is_sellable=False)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(price), pool.submit(pause)]
        for job in jobs:
            job.result(timeout=10)
    item = ListingItem.objects.get(product__sku="PAO", listing__ref="web")
    assert item.price_q == 777
    assert item.is_sellable is False


operator = fixtures.operator
shop = fixtures.shop


def observed_cell(client, operator):
    client.force_login(operator)
    matrix = client.get(fixtures.MATRIX_URL).json()["matrix"]
    cell = next(cell for row in matrix["rows"] if row["sku"] == "PAO" for cell in row["cells"] if cell["surface_ref"] == "web")
    return cell["action"]["payload_schema"]


def test_cell_receipt_replay_and_independent_field_revision(client, operator, catalog):
    from uuid import uuid4

    body = observed_cell(client, operator)
    key = str(uuid4())
    first = client.post(fixtures.CELL_URL, {**body, "price_q": 777}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 200
    pause = client.post(fixtures.CELL_URL, {**body, "is_sellable": False}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert pause.status_code == 200
    stale_price = client.post(fixtures.CELL_URL, {**body, "price_q": 888}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert stale_price.status_code == 409
    assert stale_price.json()["current"]["price_q"] == 777
    assert stale_price.json()["conflicting_fields"] == ["price_q"]
    receipt = client.get(fixtures.CELL_URL, {"ref": body["ref"], "idempotency_key": key})
    assert receipt.json()["outcome"] == "applied"
    service.set_cell("PAO", "web", price_q=999)
    replay = client.post(fixtures.CELL_URL, {**body, "price_q": 777}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert replay.json() == first.json()
    item = ListingItem.objects.get(product__sku="PAO", listing__ref="web")
    assert item.price_q == 999
    assert not item.is_sellable


def test_cell_receipt_failure_rolls_back_price(client, operator, catalog, monkeypatch):
    from uuid import uuid4

    from shopman.orderman.models import IdempotencyKey

    body = observed_cell(client, operator)
    original = IdempotencyKey.save

    def fail_receipt(self, *args, **kwargs):
        if self.response_body:
            raise RuntimeError("synthetic receipt unavailable")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(IdempotencyKey, "save", fail_receipt)
    with pytest.raises(RuntimeError, match="synthetic receipt unavailable"):
        client.post(fixtures.CELL_URL, {**body, "price_q": 777}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert ListingItem.objects.get(product__sku="PAO", listing__ref="web").price_q == 600
