"""Catalog invalidations reuse the authenticated SSE transport after commit."""
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import Permission
from django.db import transaction
from shopman.offerman.models import Product

from shopman.shop.eventstream import ShopmanChannelManager
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


def test_catalog_channel_requires_catalog_permission(django_user_model):
    user = django_user_model.objects.create_user(username="catalog-stream", is_staff=True)
    manager = ShopmanChannelManager()
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    assert not manager.can_read_channel(user, "backstage-catalog-main")
    user.user_permissions.add(Permission.objects.get(codename="manage_catalog", content_type__app_label="shop"))
    user = django_user_model.objects.get(pk=user.pk)
    assert manager.can_read_channel(user, "backstage-catalog-main")
    assert not manager.can_read_channel(None, "backstage-catalog-main")


def test_product_metadata_invalidates_only_after_commit(monkeypatch, django_capture_on_commit_callbacks):
    Shop.objects.create(name="Synthetic catalog stream")
    product = Product.objects.create(sku="STREAM-LAB", name="Before")
    publish = Mock()
    monkeypatch.setattr("shopman.shop.handlers._sse_emitters._publish_backstage", publish)
    with django_capture_on_commit_callbacks(execute=True):
        product.name = "After"
        product.save(update_fields=["name"])
        publish.assert_not_called()
    assert any(call.args[:2] == ("catalog", "backstage-catalog-update") for call in publish.call_args_list)


def test_rollback_does_not_invalidate_catalog(monkeypatch, django_capture_on_commit_callbacks):
    Shop.objects.create(name="Synthetic rollback stream")
    product = Product.objects.create(sku="STREAM-ROLLBACK", name="Before")
    publish = Mock()
    monkeypatch.setattr("shopman.shop.handlers._sse_emitters._publish_backstage", publish)
    with django_capture_on_commit_callbacks(execute=True):
        with pytest.raises(RuntimeError), transaction.atomic():
            product.name = "Rolled back"
            product.save(update_fields=["name"])
            raise RuntimeError("rollback")
    publish.assert_not_called()


@pytest.mark.parametrize("resource", ["channel", "collection", "membership", "sync", "listing", "cell"])
def test_canonical_catalog_writers_invalidate_private_read(resource, monkeypatch, django_capture_on_commit_callbacks):
    from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem

    from shopman.shop.models import CatalogSyncState, Channel

    Shop.objects.create(name="Synthetic resources")
    product = Product.objects.create(sku="RESOURCE-LAB", name="Resource")
    group = Collection.objects.create(ref="stream-group", name="Group")
    listing = Listing.objects.create(ref="stream-list", name="List")
    records = {
        "channel": Channel(ref="stream-channel", name="Channel"),
        "collection": Collection(ref="stream-group-new", name="New group"),
        "membership": CollectionItem(collection=group, product=product),
        "sync": CatalogSyncState(sku=product.sku, channel_ref="stream-channel", status="pending"),
        "listing": Listing(ref="stream-list-new", name="New list"),
        "cell": ListingItem(listing=listing, product=product, price_q=1000),
    }
    publish = Mock()
    monkeypatch.setattr("shopman.shop.handlers._sse_emitters._publish_backstage", publish)
    with django_capture_on_commit_callbacks(execute=True):
        records[resource].save()
        publish.assert_not_called()
    assert any(call.args[:2] == ("catalog", "backstage-catalog-update") for call in publish.call_args_list)


def test_bulk_order_invalidates_without_model_save_signals(monkeypatch, django_capture_on_commit_callbacks):
    from shopman.offerman.models import Collection

    from shopman.backstage.services.catalog import reorder_collections

    Shop.objects.create(name="Synthetic bulk order stream")
    first = Collection.objects.create(ref="order-first", name="First", sort_order=0)
    second = Collection.objects.create(ref="order-second", name="Second", sort_order=1)
    publish = Mock()
    monkeypatch.setattr("shopman.shop.handlers._sse_emitters._publish_backstage", publish)
    with django_capture_on_commit_callbacks(execute=True):
        assert reorder_collections([second.ref, first.ref]) == 2
        publish.assert_not_called()
    assert any(call.args[:2] == ("catalog", "backstage-catalog-update") for call in publish.call_args_list)
