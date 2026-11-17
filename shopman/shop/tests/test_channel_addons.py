"""Complementos do iFood: payload do PUT, PATCH de opção e o serviço tudo-ou-nada.

A forma do payload e as duas descobertas (``optionIds`` só aceita UUID versão 4;
o PUT deixa o contexto DEFAULT AVAILABLE) foram lidas na loja de teste em
17/11/2026, e cada uma tem um teste aqui.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult

from shopman.shop.adapters import catalog_projection_ifood as adapter
from shopman.shop.models import Channel, ChannelAddon, ChannelAddonGroup
from shopman.shop.services import channel_addons as service

pytestmark = pytest.mark.django_db

MERCHANT = "00000000-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def ifood_config(settings):
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = {"environment": "test", "merchant_allowlist": [MERCHANT]}
    settings.SHOPMAN_IFOOD = {
        "merchant_id": MERCHANT,
        "api_base": "https://mock-ifood.test",
        "catalog_default_category": "cat-default",
    }


@pytest.fixture
def channel():
    return Channel.objects.create(ref="ifood", name="iFood", is_active=True)


@pytest.fixture
def group(channel):
    group = ChannelAddonGroup.objects.create(
        channel=channel, sku="PAO", ref="molhos", name="Molhos", min_choices=0, max_choices=2
    )
    ChannelAddon.objects.create(group=group, ref="mel", name="Mel", price_q=150, index=0)
    ChannelAddon.objects.create(group=group, ref="geleia", name="Geleia", price_q=250, index=1, is_active=False)
    return group


def _item(**overrides):
    values = {
        "sku": "PAO", "name": "Pão", "description": "", "unit": "un", "price_q": 1000,
        "is_published": True, "is_sellable": True, "image_url": "", "category": "",
    }
    values.update(overrides)
    return ProjectedItem(**values)


def _ok(json_data=None):
    response = MagicMock(status_code=200, headers={})
    response.json.return_value = json_data or {}
    response.raise_for_status = MagicMock()
    return response


def test_option_ids_are_stable_and_shaped_as_uuid_version_4():
    first = adapter.addon_identity(MERCHANT, "PAO", "molhos", "mel")
    again = adapter.addon_identity(MERCHANT, "PAO", "molhos", "mel")
    group = adapter.addon_identity(MERCHANT, "PAO", "molhos")

    assert first == again
    for value in (first["option_id"], first["product_id"], group["group_id"]):
        assert uuid.UUID(value).version == 4


def test_put_carries_groups_options_products_and_the_link_on_the_item(group):
    groups = adapter._addon_groups("PAO", "ifood")
    addons = adapter._addon_payload("PAO", groups, merchant_id=MERCHANT, image_paths={})
    identity = MagicMock(item_id="item-1", product_id="product-1", category_ref="")
    body = adapter._item_payload(_item(), merchant_id=MERCHANT, category_id="cat", identity=identity, addons=addons)

    group_id = adapter.addon_identity(MERCHANT, "PAO", "molhos")["group_id"]
    mel = adapter.addon_identity(MERCHANT, "PAO", "molhos", "mel")
    geleia = adapter.addon_identity(MERCHANT, "PAO", "molhos", "geleia")
    assert body["products"][0]["optionGroups"] == [{"id": group_id, "min": 0, "max": 2, "index": 0}]
    assert body["optionGroups"][0]["optionIds"] == [mel["option_id"], geleia["option_id"]]
    assert body["optionGroups"][0]["externalCode"] == "PAO-molhos"
    assert [(o["id"], o["status"], o["price"]) for o in body["options"]] == [
        (mel["option_id"], "AVAILABLE", {"value": 1.5, "originalValue": 1.5}),
        (geleia["option_id"], "UNAVAILABLE", {"value": 2.5, "originalValue": 2.5}),
    ]
    assert [p["name"] for p in body["products"][1:]] == ["Mel", "Geleia"]


def test_sku_without_addons_does_not_touch_remote_option_groups():
    identity = MagicMock(item_id="item-1", product_id="product-1", category_ref="")
    body = adapter._item_payload(_item(), merchant_id=MERCHANT, category_id="cat", identity=identity)

    # Sem as chaves, o PUT preserva o que a loja tenha criado no Portal.
    assert "optionGroups" not in body
    assert "options" not in body
    assert "optionGroups" not in body["products"][0]


def test_group_without_options_is_not_sent(channel):
    ChannelAddonGroup.objects.create(channel=channel, sku="PAO", ref="vazio", name="Vazio")
    groups = adapter._addon_groups("PAO", "ifood")
    addons = adapter._addon_payload("PAO", groups, merchant_id=MERCHANT)

    assert addons["optionGroups"] == []
    assert addons["links"] == []


def test_put_is_followed_by_status_patches_for_what_is_paused(group):
    with patch.object(adapter.requests, "put", return_value=_ok()) as put, patch.object(
        adapter.requests, "patch", return_value=_ok()
    ) as patch_call:
        adapter._upsert_item(_item(is_sellable=False), adapter._get_config("ifood"), {"Authorization": "x"}, channel="ifood")

    put.assert_called_once()
    geleia = adapter.addon_identity(MERCHANT, "PAO", "molhos", "geleia")["option_id"]
    calls = [(c.args[0].rsplit("/merchants/", 1)[1], c.kwargs["json"]) for c in patch_call.call_args_list]
    item_id = put.call_args.kwargs["json"]["item"]["id"]
    assert calls == [
        (f"{MERCHANT}/items/status", {"itemId": item_id, "status": "UNAVAILABLE"}),
        (f"{MERCHANT}/options/status", {"optionId": geleia, "status": "UNAVAILABLE"}),
    ]


def test_option_price_goes_by_patch_and_is_confirmed_by_reading_the_item(group):
    mel = group.addons.get(ref="mel")
    mel.price_q = 375
    option_id = adapter.addon_identity(MERCHANT, "PAO", "molhos", "mel")["option_id"]
    flat = {"options": [{"id": option_id, "price": {"value": 3.75}, "status": "AVAILABLE"}]}
    with patch.object(adapter.ifood_auth, "headers_with_reason", return_value=({"Authorization": "x"}, "")), patch.object(
        adapter.requests, "patch", return_value=_ok()
    ) as patch_call, patch.object(adapter.requests, "get", return_value=_ok(flat)):
        result = adapter.IFoodCatalogProjection().update_addon_price(mel, channel="ifood")

    assert result.success, result.errors
    assert patch_call.call_args.args[0].endswith("/options/price")
    assert patch_call.call_args.kwargs["json"] == {
        "optionId": option_id,
        "price": {"value": 3.75, "originalValue": 3.75},
    }


def test_option_pause_waits_for_the_eventually_consistent_read(group, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    mel = group.addons.get(ref="mel")
    mel.is_active = False
    option_id = adapter.addon_identity(MERCHANT, "PAO", "molhos", "mel")["option_id"]
    reads = [
        _ok({"options": [{"id": option_id, "status": "AVAILABLE"}]}),
        _ok({"options": [{"id": option_id, "status": "UNAVAILABLE"}]}),
    ]
    with patch.object(adapter.ifood_auth, "headers_with_reason", return_value=({"Authorization": "x"}, "")), patch.object(
        adapter.requests, "patch", return_value=_ok()
    ) as patch_call, patch.object(adapter.requests, "get", side_effect=reads):
        result = adapter.IFoodCatalogProjection().set_addon_status(mel, channel="ifood")

    assert result.success, result.errors
    assert patch_call.call_args.kwargs["json"] == {"optionId": option_id, "status": "UNAVAILABLE"}


def test_option_writes_are_blocked_outside_the_test_store(group, settings):
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = None
    with patch.object(adapter.requests, "patch") as patch_call:
        result = adapter.IFoodCatalogProjection().update_addon_price(group.addons.first(), channel="ifood")

    assert not result.success
    patch_call.assert_not_called()


def test_price_change_is_rolled_back_when_ifood_does_not_confirm(group):
    mel = group.addons.get(ref="mel")
    backend = MagicMock()
    backend.update_addon_price.return_value = ProjectionResult(success=False, errors=["HTTP 500"], channel="ifood")
    with patch.object(service, "_backend", return_value=backend):
        with pytest.raises(service.AddonRemoteError):
            service.change_addon_price(addon_id=mel.pk, price_q=999)

    mel.refresh_from_db()
    assert mel.price_q == 150


def test_new_addon_is_kept_only_after_ifood_shows_it(group, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    backend = MagicMock()
    backend.project.return_value = ProjectionResult(success=True, projected=1, channel="ifood")

    def read_item(sku, *, channel):
        addon = ChannelAddon.objects.get(group=group, ref="cebola")
        ids = adapter.addon_identity(MERCHANT, "PAO", "molhos", addon.ref)
        return {
            "item": {"id": "item"},
            "options": [{"id": ids["option_id"], "price": {"value": 2.0}}],
            "products": [{"id": ids["product_id"], "name": "Cebola"}],
        }

    backend.read_item.side_effect = read_item
    with patch.object(service, "_backend", return_value=backend), patch.object(
        service, "_projected_item", return_value=_item()
    ):
        receipt = service.add_addon(group_id=group.pk, name="Cebola", price_q=200)

    assert "confirmado" in receipt.message
    assert group.addons.filter(ref="cebola", price_q=200).exists()


def test_new_addon_is_rolled_back_when_the_put_fails(group):
    backend = MagicMock()
    backend.project.return_value = ProjectionResult(success=False, errors=["HTTP 400"], channel="ifood")
    with patch.object(service, "_backend", return_value=backend), patch.object(
        service, "_projected_item", return_value=_item()
    ):
        with pytest.raises(service.AddonRemoteError):
            service.add_addon(group_id=group.pk, name="Cebola", price_q=200)

    assert not group.addons.filter(ref="cebola").exists()


def test_addons_exist_only_in_the_ifood_channel():
    Channel.objects.create(ref="web", name="Loja online")
    with pytest.raises(service.AddonError):
        service.create_group(channel_ref="web", sku="PAO", name="Molhos")


def test_ifood_refusal_is_shown_with_ifoods_own_reason(group):
    refused = MagicMock(status_code=400, headers={})
    refused.json.return_value = {"error": {"code": "BadRequest", "message": "FullItemDto is not valid", "details": [
        {"code": "NotAnUUID", "field": "OptionGroupDto.optionIds", "message": "each value in optionIds must be a UUID"}]}}
    with patch.object(adapter.requests, "put", return_value=refused), pytest.raises(adapter.IFoodRejected) as exc:
        adapter._upsert_item(_item(), adapter._get_config("ifood"), {"Authorization": "x"}, channel="ifood")

    friendly, original = str(exc.value).split(adapter.IFOOD_ORIGINAL_MARK)
    assert friendly == "O grupo de complementos não foi aceito pelo iFood."
    assert original == "each value in optionIds must be a UUID (OptionGroupDto.optionIds)"
    assert "HTTP" not in friendly


def test_photo_refusal_is_translated():
    text = adapter.ifood_rejection_text(
        [{"code": "InvalidImage", "field": "ProductDto.imagePath", "message": "image could not be processed"}], "",
    )
    assert text.startswith("A foto não foi aceita pelo iFood: formato, tamanho ou endereço inválido.")
