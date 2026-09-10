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


BOARD_URL = "/api/v1/backstage/feeds/"
ACTIVE_URL = "/api/v1/backstage/feeds/active/"
COLLS_URL = "/api/v1/backstage/feeds/collections/"
ROTATION_URL = "/api/v1/backstage/feeds/rotation/"


def test_board_shape(client, operator, board):
    client.force_login(operator)
    resp = client.get(BOARD_URL)
    assert resp.status_code == 200
    data = resp.json()["board"]
    by_ref = {s["ref"]: s for s in data["feeds"]}
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


def test_toggle_unknown_feed(client, operator, board):
    client.force_login(operator)
    resp = client.post(
        ACTIVE_URL, data={"ref": "ghost", "is_active": True}, content_type="application/json"
    )
    assert resp.status_code == 400


# ── Rotação de páginas do quadro ────────────────────────────────────────────────


def _rotate(client, body):
    return client.post(ROTATION_URL, data=body, content_type="application/json")


def test_set_rotation_writes_display_config(client, operator, board):
    client.force_login(operator)
    resp = _rotate(client, {"ref": "tv", "rotate_seconds": 15, "items_per_page": 12})
    assert resp.status_code == 200
    display = Channel.objects.get(ref="tv").config["display"]
    assert display["rotate_seconds"] == 15
    assert display["items_per_page"] == 12


def test_set_rotation_off_zeroes_both(client, operator, board):
    client.force_login(operator)
    _rotate(client, {"ref": "tv", "rotate_seconds": 15, "items_per_page": 12})
    resp = _rotate(client, {"ref": "tv", "rotate_seconds": 0, "items_per_page": 0})
    assert resp.status_code == 200
    display = Channel.objects.get(ref="tv").config["display"]
    assert display["rotate_seconds"] == 0
    assert display["items_per_page"] == 0


def test_set_rotation_shows_on_the_board(client, operator, board):
    client.force_login(operator)
    _rotate(client, {"ref": "tv", "rotate_seconds": 15, "items_per_page": 12})
    data = client.get(BOARD_URL).json()["board"]
    tv = next(s for s in data["feeds"] if s["ref"] == "tv")
    assert tv["rotate_seconds"] == 15
    assert tv["items_per_page"] == 12


def test_set_rotation_rejects_strobe(client, operator, board):
    """Abaixo de 5s por página ninguém lê: recusa em vez de aceitar calada."""
    client.force_login(operator)
    resp = _rotate(client, {"ref": "tv", "rotate_seconds": 3, "items_per_page": 12})
    assert resp.status_code == 400
    assert "5 segundos" in resp.json()["detail"]


def test_set_rotation_rejects_one_without_the_other(client, operator, board):
    """Rotação sem teto não tem página; teto sem rotação esconderia o resto."""
    client.force_login(operator)
    assert _rotate(client, {"ref": "tv", "rotate_seconds": 10, "items_per_page": 0}).status_code == 400
    assert _rotate(client, {"ref": "tv", "rotate_seconds": 0, "items_per_page": 12}).status_code == 400


def test_set_rotation_rejects_garbage(client, operator, board):
    client.force_login(operator)
    assert _rotate(client, {"ref": "tv", "rotate_seconds": "dez", "items_per_page": 12}).status_code == 400
    assert _rotate(client, {"ref": "tv", "rotate_seconds": -5, "items_per_page": 12}).status_code == 400
    assert _rotate(client, {"ref": "tv", "items_per_page": 12}).status_code == 400


def test_set_rotation_rejects_platform_feed(client, operator, board):
    """Feed XML (Google/Meta) não tem tela: não há páginas para rotacionar."""
    client.force_login(operator)
    resp = _rotate(client, {"ref": "google", "rotate_seconds": 10, "items_per_page": 12})
    assert resp.status_code == 400


def test_set_rotation_requires_manage_catalog(client, plain_staff, board):
    client.force_login(plain_staff)
    resp = _rotate(client, {"ref": "tv", "rotate_seconds": 10, "items_per_page": 12})
    assert resp.status_code == 403
