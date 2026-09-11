"""Curated order belongs to an exact observed set, never a partial drag payload."""
import pytest
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.backstage.services import catalog
from shopman.backstage.services.exceptions import CatalogError

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("ordered", [["A"], ["B", "B"], ["B", "A", "UNKNOWN"]])
def test_manual_order_requires_exact_unique_members(ordered):
    group = Collection.objects.create(ref="manual", name="Manual")
    for index, sku in enumerate(["A", "B"]):
        product = Product.objects.create(sku=sku, name=sku, base_price_q=1000)
        CollectionItem.objects.create(collection=group, product=product, sort_order=index)
    with pytest.raises(CatalogError):
        catalog.reorder_collection_items("manual", ordered)
    assert list(CollectionItem.objects.filter(collection=group).order_by("sort_order").values_list("product__sku", flat=True)) == ["A", "B"]


@pytest.mark.parametrize("ordered", [["A"], ["B", "B"], ["B", "A", "UNKNOWN"]])
def test_collection_order_requires_exact_unique_active_set(ordered):
    for index, ref in enumerate(["A", "B"]):
        Collection.objects.create(ref=ref, name=ref, is_active=True, sort_order=index)
    with pytest.raises(CatalogError):
        catalog.reorder_collections(ordered)
    assert list(Collection.objects.filter(is_active=True).order_by("sort_order").values_list("ref", flat=True)) == ["A", "B"]


def test_order_receipt_replay_does_not_undo_later_order(client, django_user_model):
    from uuid import uuid4

    user = django_user_model.objects.create_user("curator", is_staff=True, is_superuser=True)
    client.force_login(user)
    for index, ref in enumerate(["A", "B"]):
        Collection.objects.create(ref=ref, name=ref, is_active=True, sort_order=index)
    url = "/api/v1/backstage/catalog/reorder-collections/"
    base = {"ref": "", "expected_actor_id": user.pk, "base_revision": catalog.curation_revision()}
    key = str(uuid4())
    body = {**base, "ordered_refs": ["B", "A"]}
    assert client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code == 200
    catalog.reorder_collections(["A", "B"])
    assert client.get(url, {"idempotency_key": key}).json()["outcome"] == "applied"
    assert client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code == 200
    assert list(Collection.objects.order_by("sort_order").values_list("ref", flat=True)) == ["A", "B"]
    assert client.post(url, {**body, "ordered_refs": ["A", "B"]}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code == 409


def test_membership_changed_after_observation_is_conflict_without_mutation():
    from shopman.backstage.services.exceptions import CatalogConflict

    Collection.objects.create(ref="A", name="A", is_active=True, sort_order=0)
    base = catalog.curation_revision()
    Collection.objects.create(ref="B", name="B", is_active=True, sort_order=1)
    with pytest.raises(CatalogConflict):
        catalog.reorder_collections(["A"], expected_revision=base)
    assert list(Collection.objects.order_by("sort_order").values_list("ref", flat=True)) == ["A", "B"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_orders_are_serialized():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import connection, connections

    from shopman.backstage.services.exceptions import CatalogConflict

    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks and independent connections")
    for index, ref in enumerate(["A", "B", "C"]):
        Collection.objects.create(ref=ref, name=ref, is_active=True, sort_order=index)
    base = catalog.curation_revision()
    barrier = Barrier(2)

    def worker(ordered):
        try:
            barrier.wait(timeout=5)
            try:
                catalog.reorder_collections(ordered, expected_revision=base)
                return "applied"
            except CatalogConflict:
                return "conflict"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(worker, [["B", "A", "C"], ["C", "B", "A"]]))
    assert sorted(outcomes) == ["applied", "conflict"]
