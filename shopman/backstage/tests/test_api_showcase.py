"""Backstage: API dos canais de EXIBIÇÃO — board + ligar/pausar + coleções."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.offerman.models import Collection

from shopman.shop.models import Channel, Shop
from shopman.shop.tests._display import display_channel


def _perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_catalog",
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(db, shop):
    u = User.objects.create_user("sc-api", password="pw", is_staff=True)
    u.user_permissions.add(_perm())
    return u


@pytest.fixture
def plain_staff(db, shop):
    return User.objects.create_user("plain", password="pw", is_staff=True)


@pytest.fixture
def board(db):
    Collection.objects.create(ref="paes", name="Pães", is_active=True, sort_order=1)
    Collection.objects.create(ref="doces", name="Doces", is_active=True, sort_order=2)
    display_channel("tv", "TV Café", collections=["paes"], prices_from="pdv")
    google = display_channel("google", "Google", collections=[], fmt="google_merchant", prices_from="web")
    google.is_active = False
    google.save(update_fields=["is_active"])


BOARD_URL = "/api/v1/backstage/showcases/"
ACTIVE_URL = "/api/v1/backstage/showcases/active/"
COLLS_URL = "/api/v1/backstage/showcases/collections/"


def test_board_shape(client, operator, board):
    client.force_login(operator)
    resp = client.get(BOARD_URL)
    assert resp.status_code == 200
    data = resp.json()["board"]
    by_ref = {s["ref"]: s for s in data["showcases"]}
    assert by_ref["tv"]["kind"] == "menuboard"
    assert by_ref["tv"]["output_path"] == "/menuboard/tv/"
    assert [c["ref"] for c in by_ref["tv"]["collections"]] == ["paes"]
    assert by_ref["google"]["output_path"] == "/feed/google.xml"
    assert by_ref["google"]["is_active"] is False
    assert {c["ref"] for c in data["all_collections"]} == {"paes", "doces"}


def test_board_requires_manage_catalog(client, plain_staff, board):
    client.force_login(plain_staff)
    assert client.get(BOARD_URL).status_code == 403


def test_toggle_active(client, operator, board):
    client.force_login(operator)
    resp = client.post(
        ACTIVE_URL, data={"ref": "google", "is_active": True}, content_type="application/json"
    )
    assert resp.status_code == 200
    assert Channel.objects.get(ref="google").is_active is True


def test_set_collections(client, operator, board):
    client.force_login(operator)
    resp = client.post(
        COLLS_URL,
        data={"ref": "tv", "collections": ["doces", "paes"]},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert Channel.objects.get(ref="tv").config["display"]["collections"] == ["doces", "paes"]


def test_set_collections_unknown_rejected(client, operator, board):
    client.force_login(operator)
    resp = client.post(
        COLLS_URL,
        data={"ref": "tv", "collections": ["nope"]},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_toggle_unknown_showcase(client, operator, board):
    client.force_login(operator)
    resp = client.post(
        ACTIVE_URL, data={"ref": "ghost", "is_active": True}, content_type="application/json"
    )
    assert resp.status_code == 400
