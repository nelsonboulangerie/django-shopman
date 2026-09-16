from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from shopman.shop.models import PushSubscription

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/notifications/push/"
User = get_user_model()


@pytest.fixture
def operator():
    return User.objects.create_user(username="push-owner", password="x", is_staff=True)


@pytest.fixture
def colleague():
    return User.objects.create_user(username="push-other", password="x", is_staff=True)


def _payload(**changes):
    payload = {
        "subscription": {
            "endpoint": "https://fcm.googleapis.com/fcm/send/device-1",
            "keys": {"p256dh": "public-device-key", "auth": "device-auth"},
        },
        "surface_ref": "orders",
        "device_label": "iPhone da cozinha",
        "categories": ["order"],
    }
    payload.update(changes)
    return payload


def test_anonymous_cannot_manage_push_devices(client):
    assert client.get(URL).status_code in (401, 403)


def test_register_list_update_and_remove_owned_device(client, operator):
    client.force_login(operator)

    created = client.post(URL, _payload(), content_type="application/json")
    assert created.status_code == 201
    device_id = created.json()["device"]["id"]

    listing = client.get(URL).json()
    assert [device["id"] for device in listing["devices"]] == [device_id]
    assert listing["surface_categories"]["orders"] == ["order"]
    assert {item["value"] for item in listing["categories"]} >= {"campaign", "order"}

    updated = client.patch(
        URL,
        {"id": device_id, "categories": []},
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["device"]["categories"] == []

    removed = client.delete(URL, {"id": device_id}, content_type="application/json")
    assert removed.status_code == 204
    record = PushSubscription.objects.get(pk=device_id)
    assert record.disabled_at is not None
    assert client.get(URL).json()["devices"] == []


def test_registration_is_idempotent_and_reactivates_endpoint(client, operator):
    old = PushSubscription.objects.create(
        user=operator,
        endpoint="https://fcm.googleapis.com/fcm/send/device-1",
        p256dh="old-key",
        auth="old-auth",
        surface_ref="orders",
        device_label="Antigo",
        categories=["order"],
        failures=4,
        disabled_at=timezone.now(),
    )
    client.force_login(operator)

    response = client.post(URL, _payload(), content_type="application/json")

    assert response.status_code == 200
    old.refresh_from_db()
    assert old.disabled_at is None
    assert old.failures == 0
    assert old.p256dh == "public-device-key"
    assert PushSubscription.objects.count() == 1


def test_reregistering_browser_endpoint_transfers_it_to_current_account(
    client, operator, colleague
):
    record = PushSubscription.objects.create(
        user=colleague,
        endpoint="https://fcm.googleapis.com/fcm/send/device-1",
        p256dh="old-key",
        auth="old-auth",
        surface_ref="orders",
        device_label="Antigo",
        categories=["order"],
    )
    client.force_login(operator)

    assert client.post(URL, _payload(), content_type="application/json").status_code == 200
    record.refresh_from_db()
    assert record.user == operator


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"subscription": {"endpoint": "http://push.test", "keys": {"p256dh": "x", "auth": "y"}}}, "endpoint"),
        ({"subscription": {"endpoint": "https://127.0.0.1/push", "keys": {"p256dh": "x", "auth": "y"}}}, "endpoint"),
        ({"subscription": {"endpoint": "https://push.localhost/device", "keys": {"p256dh": "x", "auth": "y"}}}, "endpoint"),
        ({"subscription": {"endpoint": "https://fcm.googleapis.com.evil.test/device", "keys": {"p256dh": "x", "auth": "y"}}}, "endpoint"),
        ({"subscription": {"endpoint": "https://user@fcm.googleapis.com/device", "keys": {"p256dh": "x", "auth": "y"}}}, "endpoint"),
        ({"subscription": {"endpoint": "https://fcm.googleapis.com:444/device", "keys": {"p256dh": "x", "auth": "y"}}}, "endpoint"),
        ({"subscription": {"endpoint": "https://fcm.googleapis.com/fcm/send/device", "keys": {"p256dh": "", "auth": "y"}}}, "keys"),
        ({"surface_ref": "storefront"}, "surface_ref"),
        ({"categories": ["campaign"]}, "categories"),
        ({"categories": ["order", "order"]}, "categories"),
    ],
)
def test_invalid_registration_is_rejected(client, operator, changes, field):
    client.force_login(operator)
    response = client.post(URL, _payload(**changes), content_type="application/json")
    assert response.status_code == 400
    assert response.json()["field"] == field
    assert PushSubscription.objects.count() == 0


def test_other_users_device_is_neither_visible_nor_mutable(client, operator, colleague):
    record = PushSubscription.objects.create(
        user=colleague,
        endpoint="https://updates.push.services.mozilla.com/wpush/v2/other",
        p256dh="key",
        auth="auth",
        surface_ref="hub",
        device_label="Outro",
        categories=["system"],
    )
    client.force_login(operator)

    assert client.get(URL).json()["devices"] == []
    assert client.patch(
        URL, {"id": record.pk, "categories": []}, content_type="application/json"
    ).status_code == 404
    assert client.delete(
        URL, {"endpoint": record.endpoint}, content_type="application/json"
    ).status_code == 404
    record.refresh_from_db()
    assert record.disabled_at is None
