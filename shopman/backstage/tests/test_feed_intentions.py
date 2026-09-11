"""Feed receipts, independent field revisions, and concurrent Channel writes."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from django.contrib.auth.models import Permission
from django.db import connection, connections
from shopman.offerman.models import Collection

from shopman.backstage.services import feeds
from shopman.shop.models import Channel, Shop
from shopman.shop.tests._display import display_channel

pytestmark = pytest.mark.django_db


@pytest.fixture
def context(client, django_user_model):
    Shop.objects.create(name="Synthetic feed lab")
    user = django_user_model.objects.create_user(username="feed-intention", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_catalog", content_type__app_label="shop"))
    client.force_login(user)
    Collection.objects.create(ref="bread", name="Bread")
    channel = display_channel("lab-tv", "Lab TV", collections=[], prices_from="web")
    return user, channel


@pytest.mark.parametrize("field,inputs", [("active", {"is_active": False}), ("collections", {"collections": ["bread"]}), ("rotation", {"rotate_seconds": 10, "items_per_page": 8})])
def test_feed_receipt_replays_same_intention(client, context, field, inputs):
    user, channel = context
    url = f"/api/v1/backstage/feeds/{field}/"
    body = {"ref": channel.ref, "expected_actor_id": user.pk, "base_revision": feeds.revision(channel, field), **inputs}
    first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="feed-intention")
    assert first.status_code == 200, first.content
    second = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="feed-intention")
    assert second.status_code == 200
    assert second.json()["replayed"]
    receipt = client.get(url, {"ref": channel.ref, "idempotency_key": "feed-intention"})
    assert receipt.json()["outcome"] == "applied"
    conflict = client.post(url, {**body, "base_revision": "different"}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="feed-intention")
    assert conflict.status_code == 409


def test_other_field_does_not_invalidate_draft_but_same_field_does(context):
    _user, channel = context
    collections = feeds.revision(channel, "collections")
    rotation = feeds.revision(channel, "rotation")
    feeds.set_rotation(channel.ref, rotate_seconds=10, items_per_page=8, expected_revision=rotation)
    feeds.set_collections(channel.ref, ["bread"], expected_revision=collections)
    channel.refresh_from_db()
    assert channel.config["display"]["rotate_seconds"] == 10
    assert channel.config["display"]["collections"] == ["bread"]
    feeds.set_item_paused(channel.ref, "SKU-A", paused=True)
    feeds.set_items_paused(channel.ref, ["SKU-B"], paused=True)
    channel.refresh_from_db()
    assert channel.config["display"]["paused_skus"] == ["SKU-A", "SKU-B"]
    assert channel.config["display"]["rotate_seconds"] == 10
    with pytest.raises(feeds.FeedConflict):
        feeds.set_collections(channel.ref, [], expected_revision=collections)
    channel.refresh_from_db()
    assert channel.config["display"]["collections"] == ["bread"]


def test_feed_legacy_writer_cannot_bypass_receipt(client, context):
    _user, channel = context
    response = client.post("/api/v1/backstage/feeds/active/", {"ref": channel.ref, "is_active": False}, content_type="application/json")
    assert response.status_code == 400
    channel.refresh_from_db()
    assert channel.is_active


@pytest.mark.django_db(transaction=True)
def test_rotation_and_collections_in_two_connections_preserve_each_other(context, monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Row locking requires independent PostgreSQL connections")
    _user, channel = context
    paused, resume, second_started = Event(), Event(), Event()
    original = feeds._save_display

    def pause_first_save(channel, display):
        if not paused.is_set():
            paused.set()
            assert resume.wait(10)
        original(channel, display)

    monkeypatch.setattr(feeds, "_save_display", pause_first_save)

    def rotation():
        try:
            feeds.set_rotation(channel.ref, rotate_seconds=10, items_per_page=8)
        finally:
            connections.close_all()

    def collections():
        try:
            second_started.set()
            feeds.set_collections(channel.ref, ["bread"])
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(rotation)
        try:
            assert paused.wait(10)
            second = pool.submit(collections)
            assert second_started.wait(10)
            try:
                second.result(timeout=1)
            except TimeoutError:
                pass  # Expected when the Channel row is held by the first writer.
        finally:
            resume.set()
        first.result(timeout=10)
        second.result(timeout=10)
    current = Channel.objects.get(pk=channel.pk).config["display"]
    assert current["rotate_seconds"] == 10
    assert current["collections"] == ["bread"]


def test_failed_local_publication_rolls_back_feed_and_receipt(client, context, monkeypatch):
    from shopman.orderman.models import IdempotencyKey

    user, channel = context

    def fail_after_save(_ref):
        raise RuntimeError("Synthetic failure before commit")

    monkeypatch.setattr(feeds, "_notify", fail_after_save)
    with pytest.raises(RuntimeError, match="Synthetic failure"):
        client.post("/api/v1/backstage/feeds/active/", {"ref": channel.ref, "is_active": False,
            "expected_actor_id": user.pk, "base_revision": feeds.revision(channel, "active")},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="failed-feed")
    channel.refresh_from_db()
    assert channel.is_active
    assert not IdempotencyKey.objects.filter(key="failed-feed").exists()
