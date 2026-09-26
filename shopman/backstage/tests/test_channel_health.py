"""O checklist vivo de cada canal: o que falta, lido do que a casa já registra."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.utils import timezone
from shopman.doorman.models import TrustedDevice
from shopman.offerman.models import Collection, CollectionItem, Product

from shopman.backstage.projections.channel_health import build_channel_health
from shopman.backstage.services import catalog_bindings as binding_service
from shopman.shop.models import CatalogBinding, Channel, IFoodStoreStatus, Shop
from shopman.shop.models.catalog_sync import CatalogSyncState
from shopman.shop.tests._display import display_channel

pytestmark = pytest.mark.django_db

IFOOD_ON = {"client_id": "cid", "client_secret": "secret", "merchant_id": "m-1", "merchant_sync_enabled": True}


def _health(ref, **kwargs):
    return next(c for c in build_channel_health(**kwargs).channels if c.ref == ref)


def _item(health, key):
    return next((i for i in health.items if i.key == key), None)


@pytest.fixture
def operator():
    user = User.objects.create_user("canais", is_staff=True)
    user.user_permissions.add(Permission.objects.get(content_type__app_label="shop", codename="manage_catalog"))
    return user


@pytest.fixture
def ifood():
    Shop.objects.create(name="Loja")
    return Channel.objects.create(ref="ifood", name="iFood", commerce_policy="order")


@pytest.fixture
def hours(monkeypatch):
    monkeypatch.setattr("shopman.shop.services.business_calendar.has_regular_hours", lambda **_: True)


def _raw(items):
    return json.dumps({
        "schema_version": 1, "merchant_id": "m-1", "catalog_id": "cat-1", "context": "DEFAULT",
        "captured_at": "2026-09-15T12:00:00Z", "source": "imported_file",
        "categories": [{"id": "c-1", "items": [{"id": f"i-{n}", "productId": f"p-{n}"} for n in range(items)]}],
        "category_items": [{"categoryId": "c-1", "items": [
            {"id": f"i-{n}", "productId": f"p-{n}", "externalCode": f"SKU-{n}", "status": "AVAILABLE"} for n in range(items)],
            "products": [{"id": f"p-{n}", "name": f"Remoto {n}"} for n in range(items)]}],
    })


# ── iFood ─────────────────────────────────────────────────────────────────────


def test_ifood_without_merchant_sync_says_hours_live_in_the_portal(settings, ifood):
    settings.SHOPMAN_IFOOD = {"client_id": "", "client_secret": "", "merchant_id": ""}
    health = _health("ifood")
    assert not health.ready
    assert _item(health, "credentials").state == "todo"
    assert _item(health, "merchant").state == "todo"
    # Horário no Portal é escolha da casa: dito como efeito, sem pendência.
    hours = _item(health, "hours")
    assert (hours.state, hours.label) == ("ok", "O horário do iFood segue o do Portal do Parceiro")
    # Sem o módulo Merchant ninguém confere o polling: o item não é inventado.
    assert _item(health, "polling") is None


def test_ifood_ready_when_every_check_passes(settings, ifood, hours, operator):
    settings.SHOPMAN_IFOOD = IFOOD_ON
    now = timezone.now()
    IFoodStoreStatus.objects.create(merchant_id="m-1", checked_at=now - timedelta(minutes=3), synced_at=now, available=True)
    snapshot = binding_service.import_snapshot(channel_ref="ifood", raw_json=_raw(1), actor=operator)
    product = Product.objects.create(sku="SKU-0", name="Pão", unit="un", base_price_q=900)
    CatalogBinding.objects.create(
        channel=ifood, product=product, provider="ifood", account_ref="m-1", catalog_ref="cat-1", context="DEFAULT",
        resource_id="i-0", external_product_ref="p-0", category_ref="c-1", snapshot=snapshot, confirmed_by=operator,
    )
    CatalogSyncState.objects.create(sku="SKU-0", channel_ref="ifood", status="synced")
    health = _health("ifood", now=now)
    assert [i.state for i in health.items] == ["ok"] * len(health.items)
    assert {i.key for i in health.items} == {"credentials", "merchant", "hours", "polling", "bindings", "refused"}
    assert health.ready and health.summary == "Tudo certo"


def test_ifood_unbound_and_refused_products_come_with_the_fixing_action(settings, ifood, operator):
    settings.SHOPMAN_IFOOD = IFOOD_ON | {"merchant_sync_enabled": False}
    binding_service.import_snapshot(channel_ref="ifood", raw_json=_raw(3), actor=operator)
    for sku, status in (("a", "error"), ("b", "error"), ("c", "error"), ("d", "synced")):
        CatalogSyncState.objects.create(sku=sku, channel_ref="ifood", status=status)
    health = _health("ifood")
    bindings = _item(health, "bindings")
    assert (bindings.label, bindings.action_label, bindings.action_path) == (
        "3 itens do iFood sem produto vinculado", "Vincular", "/channels/ifood/catalog")
    refused = _item(health, "refused")
    assert refused.label == "3 produtos recusados pelo iFood"
    assert (refused.action_label, refused.action_target) == ("Ver e corrigir", "gestor")
    assert refused.action_path == "/catalog?surface=ifood&sync=error"


def test_ifood_without_imported_menu_asks_for_the_import(settings, ifood):
    settings.SHOPMAN_IFOOD = IFOOD_ON | {"merchant_sync_enabled": False}
    item = _item(_health("ifood"), "bindings")
    assert item.state == "todo" and item.action_label == "Importar"
    # Sem registro de envio, "nenhum recusado" seria afirmar o que ninguém viu.
    assert _item(_health("ifood"), "refused") is None


@pytest.mark.parametrize(("status", "label"), [
    ({}, "O iFood ainda não foi conferido"),
    ({"checked_at_ago": 30}, "A casa parou de conferir o iFood"),
    ({"checked_at_ago": 2, "problems": [{"code": "is-connected", "state": "ERROR"}]}, "O iFood não está ouvindo a casa"),
    ({"checked_at_ago": 2, "last_error": "HTTP 403"}, "A última conferência com o iFood falhou"),
])
def test_ifood_polling_is_read_from_the_merchant_check(settings, ifood, hours, status, label):
    settings.SHOPMAN_IFOOD = IFOOD_ON
    now = timezone.now()
    ago = status.pop("checked_at_ago", None)
    IFoodStoreStatus.objects.create(
        merchant_id="m-1", synced_at=now, checked_at=now - timedelta(minutes=ago) if ago is not None else None, **status)
    item = _item(_health("ifood", now=now), "polling")
    assert item.state == "todo" and item.label.startswith(label)


def test_ifood_without_weekly_hours_points_to_where_they_are_declared(settings, ifood):
    settings.SHOPMAN_IFOOD = IFOOD_ON
    item = _item(_health("ifood"), "hours")
    assert item.label == "A loja não tem horário semanal declarado"
    assert (item.action_target, item.action_path) == ("admin", "/admin/shop/shop/")


# ── TV e feeds ────────────────────────────────────────────────────────────────


@pytest.fixture
def paes():
    collection = Collection.objects.create(ref="paes", name="Pães", is_active=True)
    CollectionItem.objects.create(collection=collection, product=Product.objects.create(sku="PAO", name="Pão", unit="un", base_price_q=500))
    return collection


def test_tv_without_collections_or_paired_tv_lists_both_with_actions(db):
    display_channel("tv", "TV", collections=[])
    health = _health("tv")
    assert _item(health, "collections").action_target == "collections"
    paired = _item(health, "paired")
    assert (paired.state, paired.action_label, paired.action_target) == ("todo", "Parear uma TV", "pair")
    assert health.preview[0].path == "/menuboard/tv/"


def test_tv_ready_when_a_paired_tv_fetched_the_board_recently(paes):
    display_channel("tv", "TV", collections=["paes"])
    device, _ = TrustedDevice.create_for(subject_type="display", subject_id="tv")
    device.touch()
    health = _health("tv")
    assert health.ready, health.items
    assert _item(health, "seen").label.startswith("A TV buscou o quadro às")


def test_player_do_pi_aparece_separado_e_nao_conta_como_tv_pareada(paes):
    from shopman.shop.menuboard_access import PLAYER_USER_AGENT_PREFIX

    display_channel("tv", "TV", collections=["paes"])
    player, _ = TrustedDevice.create_for(
        subject_type="display", subject_id="tv", user_agent=f"{PLAYER_USER_AGENT_PREFIX}1.0",
    )
    player.touch()

    health = _health("tv")

    assert _item(health, "paired").state == "todo"
    assert _item(health, "player").state == "ok"
    assert _item(health, "player").label.startswith("Player do Raspberry Pi conectado")


def test_player_do_pi_sem_contato_vira_pendencia(paes):
    from shopman.shop.menuboard_access import PLAYER_USER_AGENT_PREFIX

    display_channel("tv", "TV", collections=["paes"])
    browser, _ = TrustedDevice.create_for(subject_type="display", subject_id="tv")
    browser.touch()
    player, _ = TrustedDevice.create_for(
        subject_type="display", subject_id="tv", user_agent=f"{PLAYER_USER_AGENT_PREFIX}1.0",
    )
    now = timezone.now()
    TrustedDevice.objects.filter(pk=player.pk).update(last_used_at=now - timedelta(minutes=20))

    item = _item(_health("tv", now=now), "player")

    assert item.state == "todo"
    assert item.label.startswith("Player do Raspberry Pi sem contato desde")


def test_tv_that_stopped_fetching_and_expiring_authorization_are_flagged(paes):
    display_channel("tv", "TV", collections=["paes"])
    now = timezone.now()
    device, _ = TrustedDevice.create_for(subject_type="display", subject_id="tv")
    TrustedDevice.objects.filter(pk=device.pk).update(
        last_used_at=now - timedelta(minutes=20), expires_at=now + timedelta(days=3, hours=1))
    health = _health("tv", now=now)
    assert _item(health, "seen").label.startswith("Nenhuma TV buscou o quadro desde")
    expiry = _item(health, "expiry")
    assert expiry.label == "A autorização da TV vence em 3 dias"
    assert expiry.action_target == "pair"


def test_revoked_or_expired_tv_is_not_counted_as_paired(paes):
    display_channel("tv", "TV", collections=["paes"])
    old, _ = TrustedDevice.create_for(subject_type="display", subject_id="tv")
    old.revoke()
    stale, _ = TrustedDevice.create_for(subject_type="display", subject_id="tv")
    TrustedDevice.objects.filter(pk=stale.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    assert _item(_health("tv"), "paired").state == "todo"


def test_public_menuboard_has_no_pairing_to_check(settings, paes):
    settings.SHOPMAN_MENUBOARD_PUBLIC = True
    display_channel("tv", "TV", collections=["paes"])
    health = _health("tv")
    assert _item(health, "paired") is None and health.ready


def test_paused_feed_and_empty_or_missing_collections(db):
    Collection.objects.create(ref="vazia", name="Vazia", is_active=True)
    feed = display_channel("google", "Google", collections=["vazia", "sumiu"], fmt="google_merchant")
    feed.is_active = False
    feed.save(update_fields=["is_active"])
    health = _health("google")
    assert _item(health, "active").label == "Pausado: o Google recebe erro ao buscar o feed"
    assert _item(health, "collections_gone").label == "1 coleção escolhida não existe mais"
    assert _item(health, "collections").label == "As coleções escolhidas estão sem produtos"
    assert _item(health, "paired") is None  # feed não tem TV
    assert health.preview[0].path == "/feed/google.xml"
    assert health.summary == "3 pendências"


# ── Loja online e o endpoint ─────────────────────────────────────────────────


def test_storefront_lists_login_pix_and_card_with_the_diagnostics_link(settings, db):
    settings.SHOPMAN_STOREFRONT_BASE_URL = "https://loja.example"
    Channel.objects.create(ref="web", name="Loja online", commerce_policy="order")
    health = _health("web")
    assert {i.key for i in health.items} >= {"login", "pix", "card"}
    for item in health.items:
        if item.state == "todo":
            assert item.action_path == "/admin/diagnostics/"
    assert health.preview[0].path == "https://loja.example"


def test_channels_without_a_known_checklist_are_left_out(db):
    Channel.objects.create(ref="pdv", name="PDV", commerce_policy="order")
    assert build_channel_health().channels == ()


def test_endpoint_requires_catalog_permission_and_returns_the_board(client, operator, ifood):
    url = "/api/v1/backstage/channels/health/"
    plain = User.objects.create_user("sem-permissao", is_staff=True)
    client.force_login(plain)
    assert client.get(url).status_code == 403
    client.force_login(operator)
    response = client.get(url)
    assert response.status_code == 200
    channel, = response.json()["health"]["channels"]
    assert channel["ref"] == "ifood" and channel["items"][0]["key"] == "credentials"


# ── Linguagem de operador ────────────────────────────────────────────────────

_ENGINEER_WORDS = re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b|deploy|worker|polling|\bHTTP\b", re.IGNORECASE)


def _every_item_text(board):
    for channel in board.channels:
        for item in channel.items:
            yield channel.ref, item.key, item.label, item.hint


def test_no_item_speaks_env_vars_workers_or_deploy_to_the_operator(settings, operator, monkeypatch):
    """D6 (omotenashi-copy): o Gestor não pede o que o operador não alcança."""
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="ifood", name="iFood", commerce_policy="order")
    Channel.objects.create(ref="web", name="Loja online", commerce_policy="order")
    now = timezone.now()
    texts = []
    # Todos os caminhos do iFood que acendem pendência, um de cada vez.
    for ifood_cfg, hours, status in (
        ({"client_id": "", "client_secret": "", "merchant_id": ""}, False, None),
        (IFOOD_ON | {"merchant_sync_enabled": False}, False, None),
        (IFOOD_ON, False, None),
        (IFOOD_ON, True, {}),
        (IFOOD_ON, True, {"checked_at": now - timedelta(minutes=30), "synced_at": now}),
        (IFOOD_ON, True, {"checked_at": now, "synced_at": now, "problems": [{"code": "is-connected"}]}),
        (IFOOD_ON, True, {"checked_at": now, "synced_at": now, "last_error": "iFood merchant merchant_status: HTTP 403"}),
    ):
        settings.SHOPMAN_IFOOD = ifood_cfg
        monkeypatch.setattr("shopman.shop.services.business_calendar.has_regular_hours", lambda hours=hours, **_: hours)
        IFoodStoreStatus.objects.all().delete()
        if status is not None:
            IFoodStoreStatus.objects.create(merchant_id="m-1", **status)
        texts += list(_every_item_text(build_channel_health(now=now)))
    offenders = [t for t in texts if _ENGINEER_WORDS.search(t[2]) or _ENGINEER_WORDS.search(t[3])]
    assert not offenders, offenders
