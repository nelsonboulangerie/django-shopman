"""Central de Apps — contrato do launcher (GET /api/v1/backstage/hub/).

O endpoint é staff-gated (IsBackstageOperator); os tiles são filtrados por permissão
DENTRO da projection — operador sem apps recebe grade vazia (não 403). Ícone forte por
superfície conforme o design system canônico. Superfície sem URL configurada em
``SHOPMAN_SURFACE_URLS`` não vira tile (nunca link morto); os defaults de dev
(127.0.0.1:PORT) só valem com DEBUG ligado.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from django.urls import reverse

from shopman.shop.models import Shop

SURFACE_URLS = {
    "pos": "https://pdv.example.test/",
    "kds": "https://kds.example.test/",
    "gestor": "https://gestor.example.test/",
    "production": "https://prod.example.test/",
    "purchase": "https://compras.example.test/",
    "marketing": "https://mkt.example.test/",
    "bi": "https://bi.example.test/",
    "loja": "https://loja.example.test/",
}


def _manage_orders_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get_for_model(Shop),
        codename="manage_orders",
    )


@pytest.mark.django_db
def test_hub_requires_staff(client, db):
    customer = User.objects.create_user("hub-cust", password="pw", is_staff=False)
    client.force_login(customer)
    assert client.get(reverse("api-backstage-hub")).status_code == 403

    staff = User.objects.create_user("hub-staff", password="pw", is_staff=True)
    client.force_login(staff)
    assert client.get(reverse("api-backstage-hub")).status_code == 200


@pytest.mark.django_db
def test_hub_empty_for_staff_without_apps(client, db):
    """Staff sem nenhuma permissão de operação → launcher sem tiles (não 403)."""
    staff = User.objects.create_user("hub-plain", password="pw", is_staff=True)
    client.force_login(staff)
    hub = client.get(reverse("api-backstage-hub")).json()["hub"]
    assert hub["tiles"] == []
    assert hub["operator_name"] == "hub-plain"


@pytest.mark.django_db
@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_hub_superuser_sees_all_tiles(client, db):
    admin = User.objects.create_superuser("hub-admin", "a@b.c", "pw")
    client.force_login(admin)
    hub = client.get(reverse("api-backstage-hub")).json()["hub"]

    refs = [tile["ref"] for tile in hub["tiles"]]
    assert refs == ["pos", "kds", "gestor", "production", "purchase", "marketing", "bi", "loja"]

    by_ref = {tile["ref"]: tile for tile in hub["tiles"]}
    # Ícone forte por app (DS §6).
    assert by_ref["pos"]["icon"] == "banknote"
    assert by_ref["kds"]["icon"] == "chef-hat"
    assert by_ref["gestor"]["icon"] == "clipboard-list"
    assert by_ref["production"]["icon"] == "croissant"
    assert by_ref["purchase"]["icon"] == "package-check"
    assert by_ref["marketing"]["icon"] == "megaphone"
    assert by_ref["bi"]["icon"] == "chart-line"
    assert by_ref["bi"]["label"] == "B.I."
    # Nome público sem jargão interno: a superfície "production" é Produção e a
    # A ref da superfície é "marketing" (a seção), não "campaign" (a entidade dentro dela).
    assert by_ref["production"]["label"] == "Produção"
    assert by_ref["purchase"]["label"] == "Compras"
    assert by_ref["marketing"]["label"] == "Marketing"
    assert by_ref["loja"]["icon"] == "store"
    # Loja abre a loja do cliente (storefront) em nova aba — fora da zona de operador.
    assert by_ref["loja"]["kind"] == "external"
    assert by_ref["loja"]["url"] == "https://loja.example.test/"
    assert by_ref["pos"]["kind"] == "launch"
    # Contrato do tile.
    for tile in hub["tiles"]:
        assert set(tile) == {"ref", "label", "description", "icon", "url", "kind"}
        assert tile["label"] and tile["url"]


@pytest.mark.django_db
@override_settings(SHOPMAN_SURFACE_URLS=SURFACE_URLS)
def test_hub_filters_by_permission(client, db):
    """Operador só de pedidos vê o Gestor, não o PDV/KDS/Loja."""
    operator = User.objects.create_user("hub-gestor", password="pw", is_staff=True)
    operator.user_permissions.add(_manage_orders_perm())
    client.force_login(operator)
    refs = [tile["ref"] for tile in client.get(reverse("api-backstage-hub")).json()["hub"]["tiles"]]

    assert "gestor" in refs
    assert "pos" not in refs
    assert "kds" not in refs
    assert "loja" not in refs  # loja só p/ superuser


@pytest.mark.django_db
@override_settings(
    SHOPMAN_SURFACE_URLS={k: v for k, v in SURFACE_URLS.items() if k != "marketing"}
)
def test_hub_hides_surface_without_url(client, db):
    """Superfície sem URL configurada some do launcher — nunca link morto nem
    fallback 127.0.0.1 fora de DEBUG (foi o bug do tile Marketing no staging)."""
    admin = User.objects.create_superuser("hub-nourl", "a@b.c", "pw")
    client.force_login(admin)
    tiles = client.get(reverse("api-backstage-hub")).json()["hub"]["tiles"]

    refs = [tile["ref"] for tile in tiles]
    assert "marketing" not in refs
    assert refs == ["pos", "kds", "gestor", "production", "purchase", "bi", "loja"]
    assert all("127.0.0.1" not in tile["url"] for tile in tiles)


@pytest.mark.django_db
@override_settings(DEBUG=True, SHOPMAN_SURFACE_URLS={})
def test_hub_debug_falls_back_to_dev_urls(client, db):
    """Em DEBUG (dev local sem env), o launcher usa os defaults 127.0.0.1:PORT."""
    admin = User.objects.create_superuser("hub-debug", "a@b.c", "pw")
    client.force_login(admin)
    by_ref = {
        tile["ref"]: tile
        for tile in client.get(reverse("api-backstage-hub")).json()["hub"]["tiles"]
    }
    assert by_ref["marketing"]["url"] == "http://127.0.0.1:3006/"
    assert by_ref["bi"]["url"] == "http://127.0.0.1:3007/"
    assert by_ref["purchase"]["url"] == "http://127.0.0.1:3008/"
    assert by_ref["loja"]["url"] == "http://127.0.0.1:3000/"
