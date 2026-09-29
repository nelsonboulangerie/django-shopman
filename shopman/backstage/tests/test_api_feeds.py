"""Backstage: API da aba Canais — board, toggle "Ativo" (com gerente) e coleções dos feeds."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from shopman.offerman.models import Collection

from shopman.backstage.services import feeds as feed_service
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
SWITCH_URL = "/api/v1/backstage/feeds/switch/"
COLLS_URL = "/api/v1/backstage/feeds/collections/"
ROTATION_URL = "/api/v1/backstage/feeds/rotation/"
AUTOMATIC_URL = "/api/v1/backstage/feeds/automatic/"


def _post(client, url, *, data, content_type):
    field = url.strip("/").split("/")[-1]
    channel = Channel.objects.filter(ref=data.get("ref")).first()
    payload = {"expected_actor_id": int(client.session["_auth_user_id"]),
        "base_revision": feed_service.revision(channel, field) if channel else "missing",
        "idempotency_key": str(uuid.uuid4()), **data}
    return client.post(url, payload, content_type=content_type)


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
    assert by_ref["tv"]["automatic"]["enabled"] is False
    assert by_ref["tv"]["automatic"]["lead_minutes"] == 15
    assert by_ref["google"]["automatic"] is None
    assert next(a for a in by_ref["tv"]["actions"] if a["ref"] == "automatic")["enabled"] is True
    assert {c["ref"] for c in data["all_collections"]} == {"paes", "doces"}


def test_board_requires_manage_catalog(client, plain_staff, board):
    client.force_login(plain_staff)
    assert client.get(BOARD_URL).status_code == 403


def _switch(client, *, ref, is_active, period="open", reason="Férias", **extra):
    from shopman.shop.services import channel_switch

    channel = Channel.objects.get(ref=ref)
    body = {"ref": ref, "is_active": is_active, "period": period, "reason": reason,
            "expected_actor_id": int(client.session["_auth_user_id"]),
            "base_revision": channel_switch.revision(channel), "idempotency_key": str(uuid.uuid4()), **extra}
    return client.post(SWITCH_URL, body, content_type="application/json")


def _adjust_shift() -> Permission:
    return Permission.objects.get(content_type__app_label="cashman", codename="adjust_shift")


@pytest.fixture
def manager(db, shop):
    """Gerente logado: tem o catálogo E a régua de exceção do PDV — só confirma."""
    u = User.objects.create_user("gerente", password="pw", is_staff=True, first_name="Joyce")
    u.user_permissions.add(_perm(), _adjust_shift())
    return User.objects.get(pk=u.pk)


@pytest.fixture
def other_manager(db, shop):
    from shopman.doorman.models import PinCredential

    u = User.objects.create_user("ana", password="pw", is_staff=True, first_name="Ana")
    u.user_permissions.add(_adjust_shift())
    PinCredential.set_for(u, "4321")
    return User.objects.get(pk=u.pk)


def test_gerente_logado_so_confirma(client, manager, board):
    client.force_login(manager)
    resp = _switch(client, ref="google", is_active=True)
    assert resp.status_code == 200, resp.content
    google = Channel.objects.get(ref="google")
    assert google.is_active is True
    assert google.config["activation"]["approved_by"] == "Joyce"


def test_quem_nao_e_gerente_precisa_da_assinatura_de_um(client, operator, other_manager, board):
    client.force_login(operator)
    refused = _switch(client, ref="tv", is_active=False)
    assert refused.status_code in (400, 403, 422)
    assert refused.json()["error"]["code"] == "manager_approval_required"
    assert Channel.objects.get(ref="tv").is_active is True

    wrong = _switch(client, ref="tv", is_active=False, manager_approval={"username": "ana", "pin": "0000"})
    assert wrong.json()["error"]["code"] == "manager_approval_invalid"

    ok = _switch(client, ref="tv", is_active=False, manager_approval={"username": "ana", "pin": "4321"})
    assert ok.status_code == 200, ok.content
    tv = Channel.objects.get(ref="tv")
    assert tv.is_active is False
    assert (tv.config["activation"]["by"], tv.config["activation"]["approved_by"]) == ("sc-api", "Ana")


def test_canal_de_venda_tem_o_mesmo_toggle(client, manager, board):
    Channel.objects.create(ref="web", name="Loja online")
    client.force_login(manager)
    board_before = client.get(BOARD_URL).json()["board"]
    web = next(c for c in board_before["catalog_channels"] if c["ref"] == "web")
    assert web["switch"]["is_active"] is True
    assert web["switch"]["title"] == "Desligar Loja online"
    assert web["switch"]["requires_manager_approval"] is False
    assert "Sem entregador" in web["switch"]["reasons"]
    assert [p["key"] for p in web["switch"]["periods"]] == ["30m", "1h", "today", "open", "custom"]

    resp = _switch(client, ref="web", is_active=False, period="1h", reason="Loja cheia")
    assert resp.status_code == 200, resp.content
    web = next(c for c in client.get(BOARD_URL).json()["board"]["catalog_channels"] if c["ref"] == "web")
    assert web["is_active"] is False
    assert web["switch"]["title"] == "Ligar Loja online"
    assert web["switch"]["reasons"] == []
    assert "Loja cheia" in web["switch"]["state_line"]


def test_quem_nao_e_gerente_recebe_a_lista_de_quem_assina(client, operator, other_manager, board):
    client.force_login(operator)
    data = client.get(BOARD_URL).json()["board"]
    assert data["managers"] == [{"username": "ana", "name": "Ana"}]
    assert all(feed["switch"]["requires_manager_approval"] for feed in data["feeds"])


def test_switch_unknown_channel(client, manager, board):
    client.force_login(manager)
    resp = client.post(SWITCH_URL, {"ref": "ghost", "is_active": True, "period": "open",
        "expected_actor_id": manager.pk, "base_revision": "x", "idempotency_key": str(uuid.uuid4())},
        content_type="application/json")
    assert resp.status_code == 400


def test_set_collections(client, operator, board):
    client.force_login(operator)
    resp = _post(client,
        COLLS_URL,
        data={"ref": "tv", "collections": ["doces", "paes"]},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert Channel.objects.get(ref="tv").config["display"]["collections"] == ["doces", "paes"]


def test_set_collections_unknown_rejected(client, operator, board):
    client.force_login(operator)
    resp = _post(client,
        COLLS_URL,
        data={"ref": "tv", "collections": ["nope"]},
        content_type="application/json",
    )
    assert resp.status_code == 400


# ── Rotação de páginas do quadro ────────────────────────────────────────────────


def _rotate(client, body):
    return _post(client, ROTATION_URL, data=body, content_type="application/json")


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


# ── Janela automática e descanso da TV ─────────────────────────────────────────


def _automatic(client, body):
    return _post(client, AUTOMATIC_URL, data=body, content_type="application/json")


def test_set_automatic_writes_mode_and_normalized_messages(client, operator, board):
    client.force_login(operator)
    resp = _automatic(client, {
        "ref": "tv", "enabled": True,
        "idle_messages": [
            "  Atendimento de seg. a sáb., das 9h às 18h  ",
            "  Nelson Boulangerie:   minha padaria favorita  ",
        ],
    })
    assert resp.status_code == 200, resp.content
    assert Channel.objects.get(ref="tv").config["display"]["automatic"] == {
        "enabled": True,
        "idle_messages": [
            "Atendimento de seg. a sáb., das 9h às 18h",
            "Nelson Boulangerie: minha padaria favorita",
        ],
    }


def test_set_automatic_is_projected_back_to_the_manager(client, operator, board):
    client.force_login(operator)
    _automatic(client, {"ref": "tv", "enabled": True, "idle_messages": ["Voltamos às 9h", "Até logo"]})
    tv = next(feed for feed in client.get(BOARD_URL).json()["board"]["feeds"] if feed["ref"] == "tv")
    assert tv["automatic"]["enabled"] is True
    assert tv["automatic"]["idle_messages"] == ["Voltamos às 9h", "Até logo"]


def test_set_automatic_rejects_platform_feed(client, operator, board):
    client.force_login(operator)
    resp = _automatic(client, {"ref": "google", "enabled": True, "idle_messages": ["Olá"]})
    assert resp.status_code == 400
    assert "apenas no menuboard" in resp.json()["detail"]


def test_set_automatic_rejects_long_message(client, operator, board):
    client.force_login(operator)
    resp = _automatic(client, {"ref": "tv", "enabled": True, "idle_messages": ["x" * 241]})
    assert resp.status_code == 400
    assert "240" in resp.json()["detail"]


def test_set_rotation_requires_manage_catalog(client, plain_staff, board):
    client.force_login(plain_staff)
    resp = _rotate(client, {"ref": "tv", "rotate_seconds": 10, "items_per_page": 12})
    assert resp.status_code == 403
