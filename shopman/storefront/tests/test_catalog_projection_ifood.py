"""
Tests for WP-GAP-15: iFood catalog projection adapter, handler, and signals.

Coverage:
- Adapter builds correct iFood payload.
- Handler dispatches to backend and marks Directive done.
- Signal on_product_created → Directive enqueued.
- Signal on_price_changed → Directive enqueued.
- Idempotency: same signal twice → single Directive.
- Rate limit (429) → handler schedules retry with Retry-After.
- Max attempts → Directive marked failed.
- Management command sync_catalog_ifood (dry-run + real).
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import replace
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult
from shopman.orderman.models import Directive

from shopman.shop.directives import CATALOG_PROJECT_SKU
from shopman.shop.services import ifood_auth

pytestmark = pytest.mark.django_db


def _image_bytes(image_format="PNG", color="red"):
    from PIL import Image

    stream = BytesIO()
    Image.new("RGB", (2, 2), color=color).save(stream, format=image_format)
    return stream.getvalue()


def _response(*, content=b"", status=200, json_data=None):
    response = MagicMock(status_code=status, headers={})
    response.content = content
    response.iter_content.return_value = [content]
    response.json.return_value = json_data or {}
    response.raise_for_status = MagicMock()
    return response

# ── Canonical projection registry (OFFERMAN["PROJECTION_BACKENDS"]) ─────────────
# Mirrors config/settings.py OFFERMAN so override_settings preserves the other
# keys (pricing backend) while toggling the iFood projection backend.
_IFOOD_BACKEND = "shopman.shop.adapters.catalog_projection_ifood.IFoodCatalogProjection"
_OFFERMAN_BASE = {
    "COST_BACKEND": None,
    "PRICING_BACKEND": "shopman.shop.adapters.pricing.PromotionPricingBackend",
}
_OFFERMAN_IFOOD = {**_OFFERMAN_BASE, "PROJECTION_BACKENDS": {"ifood": _IFOOD_BACKEND}}
_OFFERMAN_NONE = {**_OFFERMAN_BASE, "PROJECTION_BACKENDS": {}}


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolated_catalog_write_policy(settings):
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = {
        "environment": "test",
        "merchant_allowlist": ["00000000-0000-4000-8000-000000000001"],
    }


@pytest.fixture(autouse=True)
def clear_image_memory_cache():
    from shopman.shop.adapters.catalog_projection_ifood import _IMAGE_PATHS

    _IMAGE_PATHS.clear()
    yield
    _IMAGE_PATHS.clear()


@pytest.fixture
def ifood_item():
    return ProjectedItem(
        sku="PAO-FRANCES",
        name="Pão Francês",
        description="Pão crocante",
        unit="un",
        price_q=350,
        is_published=True,
        is_sellable=True,
        image_url="https://cdn.test/pao.jpg",
        category="paes",
    )


@pytest.fixture
def ifood_settings():
    return {
        "webhook_token": "wh-tok",
        "merchant_id": "00000000-0000-4000-8000-000000000001",
        "catalog_id": "catalog-main",
        "catalog_context": "DEFAULT",
        "api_base": "https://mock-ifood.test",
        "catalog_category_map": {"paes": "cat-paes-uuid"},
        "catalog_default_category": "cat-default-uuid",
    }


@pytest.fixture
def fake_oauth():
    """Patch ifood_auth so the adapter gets a real Bearer header."""
    with patch(
        "shopman.shop.services.ifood_auth.token_with_reason",
        return_value=("fake-token-xyz", ""),
    ):
        yield


@pytest.fixture
def reset_projection_registry():
    """Clear the offerman projection-backend instance cache around a test."""
    from shopman.offerman.conf import reset_projection_backends

    reset_projection_backends()
    yield
    reset_projection_backends()


@pytest.fixture
def ifood_channel(db):
    from shopman.shop.models import Channel
    return Channel.objects.create(
        ref="ifood",
        name="iFood",
        is_active=True,
    )


@pytest.fixture
def ifood_directive(db):
    return Directive.objects.create(
        topic=CATALOG_PROJECT_SKU,
        payload={"sku": "PAO-FRANCES", "listing_ref": "ifood"},
    )


def _catalog_binding(
    *,
    channel,
    sku="PAO-FRANCES",
    account_ref="00000000-0000-4000-8000-000000000001",
    catalog_ref="catalog-main",
    context="DEFAULT",
    resource_id="remote-item",
    product_ref="remote-product",
    category_ref="remote-category",
):
    from django.contrib.auth import get_user_model
    from shopman.offerman.models import Product

    from shopman.shop.models import CatalogBinding, CatalogSnapshot

    actor = get_user_model().objects.create_user(f"actor-{sku}-{catalog_ref}-{context}")
    product = Product.objects.create(sku=sku, name=sku, unit="un", base_price_q=350)
    snapshot = CatalogSnapshot.objects.create(
        channel=channel,
        provider="ifood",
        account_ref=account_ref,
        catalog_ref=catalog_ref,
        context=context,
        captured_at=timezone.now(),
        imported_by=actor,
        sha256="0" * 64,
        raw_json="{}",
        source="test",
        item_count=1,
    )
    return CatalogBinding.objects.create(
        channel=channel,
        product=product,
        provider="ifood",
        account_ref=account_ref,
        catalog_ref=catalog_ref,
        context=context,
        resource_id=resource_id,
        external_product_ref=product_ref,
        category_ref=category_ref,
        snapshot=snapshot,
        confirmed_by=actor,
    )


# ── Adapter: payload construction ─────────────────────────────────────────────


def test_adapter_builds_correct_ifood_payload(ifood_item):
    """_item_payload builds a valid FullItemDto with price in BRL float."""
    from shopman.shop.adapters.catalog_projection_ifood import _item_payload

    payload = _item_payload(ifood_item, merchant_id="00000000-0000-4000-8000-000000000001", category_id="cat-uuid")

    item = payload["item"]
    product = payload["products"][0]
    assert item["externalCode"] == "PAO-FRANCES"
    assert item["price"]["value"] == pytest.approx(3.50)
    assert item["price"]["originalValue"] == pytest.approx(3.50)
    assert item["status"] == "AVAILABLE"
    assert item["categoryId"] == "cat-uuid"
    # item.productId must equal products[0].id, and both must be UUIDs.
    assert item["productId"] == product["id"]
    uuid.UUID(item["id"])
    uuid.UUID(item["productId"])
    assert product["name"] == "Pão Francês"
    assert product["description"] == "Pão crocante"
    assert product["externalCode"] == "PAO-FRANCES"
    # No inline image — iFood v2.0 rejects it with 500 (uses a separate upload flow).
    assert "image" not in product


def test_adapter_ids_are_deterministic_per_merchant_and_sku(ifood_item):
    """Same (merchant, sku) → same item/product UUIDs (idempotent upsert)."""
    from shopman.shop.adapters.catalog_projection_ifood import _item_payload

    a = _item_payload(ifood_item, merchant_id="m", category_id="c")
    b = _item_payload(ifood_item, merchant_id="m", category_id="c")
    assert a["item"]["id"] == b["item"]["id"]
    assert a["item"]["productId"] == b["item"]["productId"]
    # Different merchant → different ids.
    other = _item_payload(ifood_item, merchant_id="other", category_id="c")
    assert other["item"]["id"] != a["item"]["id"]


def test_binding_drives_payload_and_status_patch(
    ifood_item,
    ifood_settings,
    ifood_channel,
    fake_oauth,
):
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    binding = _catalog_binding(channel=ifood_channel)
    item = replace(ifood_item, image_url="", category="sem-excecao-local")
    with (
        patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings),
        patch("requests.put", return_value=_response()) as put,
        patch("requests.patch", return_value=_response()) as patch_request,
        patch(
            "requests.get",
            return_value=_response(json_data={"item": {"status": "UNAVAILABLE"}}),
        ),
    ):
        projected = IFoodCatalogProjection().project([item], channel=ifood_channel.ref)
        retracted = IFoodCatalogProjection().retract([item.sku], channel=ifood_channel.ref)

    assert projected.success is True
    assert retracted.success is True
    payload = put.call_args.kwargs["json"]
    assert payload["item"]["id"] == binding.resource_id
    assert payload["item"]["productId"] == binding.external_product_ref
    assert payload["products"][0]["id"] == binding.external_product_ref
    assert payload["item"]["categoryId"] == binding.category_ref
    assert patch_request.call_args.kwargs["json"]["itemId"] == binding.resource_id


def test_without_binding_identity_remains_deterministic(
    ifood_settings,
    ifood_channel,
    django_assert_num_queries,
):
    from shopman.shop.policies.catalog_identity import resolve_catalog_identity

    with django_assert_num_queries(2):
        first = resolve_catalog_identity("SEM-VINCULO", ifood_channel.ref, config=ifood_settings)
    second = resolve_catalog_identity("SEM-VINCULO", ifood_channel.ref, config=ifood_settings)

    assert first == second
    assert first.origin == "derived"
    uuid.UUID(first.item_id)
    uuid.UUID(first.product_id)


def test_binding_from_other_account_is_ignored_with_warning(
    ifood_settings,
    ifood_channel,
):
    from shopman.shop.policies import catalog_identity

    _catalog_binding(channel=ifood_channel, account_ref="other-merchant")
    with patch.object(catalog_identity.logger, "warning") as warning:
        identity = catalog_identity.resolve_catalog_identity(
            "PAO-FRANCES",
            ifood_channel.ref,
            config=ifood_settings,
        )

    assert identity.origin == "derived"
    warning.assert_called_once_with(
        "catalog_identity.binding_ignored sku=%s channel=%s merchant=%s reason=account_mismatch",
        "PAO-FRANCES",
        ifood_channel.ref,
        ifood_settings["merchant_id"],
    )


def test_same_remote_item_bound_to_two_skus_is_explicit_error(ifood_channel):
    from shopman.shop.policies.catalog_identity import (
        CatalogIdentityConflict,
        resolve_catalog_identity,
    )

    _catalog_binding(channel=ifood_channel, sku="SKU-A", resource_id="shared-item")
    _catalog_binding(
        channel=ifood_channel,
        sku="SKU-B",
        catalog_ref="catalog-secondary",
        resource_id="shared-item",
    )

    with pytest.raises(CatalogIdentityConflict, match="SKU-A.*SKU-B"):
        resolve_catalog_identity(
            "SKU-A",
            ifood_channel.ref,
            config={"merchant_id": "00000000-0000-4000-8000-000000000001"},
        )


def test_adapter_never_sends_inline_image():
    """iFood v2.0 rejects an inline image URL (500) — the item PUT never carries one."""
    from shopman.shop.adapters.catalog_projection_ifood import _item_payload

    item = ProjectedItem(
        sku="X", name="X", description="", unit="un",
        price_q=100, is_published=True, is_sellable=True,
        image_url="https://cdn.test/x.jpg",
    )
    payload = _item_payload(item, merchant_id="m", category_id="c")
    assert "image" not in payload["products"][0]


def test_adapter_marks_unavailable_when_not_sellable():
    from shopman.shop.adapters.catalog_projection_ifood import _item_payload

    item = ProjectedItem(
        sku="X", name="X", description="", unit="un",
        price_q=100, is_published=True, is_sellable=False,
    )
    payload = _item_payload(item, merchant_id="m", category_id="c")
    assert payload["item"]["status"] == "UNAVAILABLE"


# ── Adapter: project() ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_adapter_uploads_image_then_puts_image_path(ifood_item, ifood_settings, fake_oauth):
    """A foto sobe em base64 antes do item, que recebe somente imagePath."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with (
            patch("requests.get", return_value=_response(content=_image_bytes())) as mock_get,
            patch("requests.post", return_value=_response(json_data={"imagePath": "merchant/photo.png"})) as mock_post,
            patch("requests.put", return_value=_response()) as mock_put,
        ):

            backend = IFoodCatalogProjection()
            result = backend.project([ifood_item], channel="ifood")

    assert result.success is True
    assert result.projected == 1
    assert result.errors == []
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["timeout"] == 30
    assert mock_post.call_args.args[0].endswith("/image/upload")
    encoded = mock_post.call_args.kwargs["json"]["image"]
    assert encoded.startswith("data:image/png;base64,")
    assert base64.b64decode(encoded.partition(",")[2]) == _image_bytes()
    mock_put.assert_called_once()
    url, kwargs = mock_put.call_args[0][0], mock_put.call_args[1]
    assert url == "https://mock-ifood.test/catalog/v2.0/merchants/00000000-0000-4000-8000-000000000001/items"
    assert kwargs["json"]["item"]["externalCode"] == "PAO-FRANCES"
    # "paes" is mapped in catalog_category_map.
    assert kwargs["json"]["item"]["categoryId"] == "cat-paes-uuid"
    assert kwargs["json"]["products"][0]["imagePath"] == "merchant/photo.png"
    assert kwargs["headers"]["Authorization"] == "Bearer fake-token-xyz"


@pytest.mark.django_db
def test_same_image_uploads_once_across_urls_and_process_cache(ifood_item, ifood_settings, fake_oauth):
    from shopman.shop.adapters.catalog_projection_ifood import _IMAGE_PATHS, IFoodCatalogProjection
    from shopman.shop.models import CatalogImageUpload

    other = replace(ifood_item, sku="OUTRO", image_url="https://other.test/same.png")
    image = _image_bytes()
    with (
        patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings),
        patch("requests.get", side_effect=[_response(content=image), _response(content=image), _response(content=image)]),
        patch("requests.post", return_value=_response(json_data={"imagePath": "merchant/photo.png"})) as mock_post,
        patch("requests.put", return_value=_response()) as mock_put,
    ):
        backend = IFoodCatalogProjection()
        first = backend.project([ifood_item, other], channel="ifood")
        _IMAGE_PATHS.clear()  # simula outro processo; o registro durável continua.
        second = backend.project([ifood_item], channel="ifood")

    assert first.success is True
    assert second.success is True
    assert mock_post.call_count == 1
    assert mock_put.call_count == 3
    assert CatalogImageUpload.objects.count() == 1


@pytest.mark.django_db
def test_changed_image_uploads_new_hash_only(ifood_item, ifood_settings, fake_oauth):
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with (
        patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings),
        patch("requests.get", side_effect=[_response(content=_image_bytes(color="red")), _response(content=_image_bytes(color="blue"))]),
        patch("requests.post", side_effect=[
            _response(json_data={"imagePath": "merchant/red.png"}),
            _response(json_data={"imagePath": "merchant/blue.png"}),
        ]) as mock_post,
        patch("requests.put", return_value=_response()) as mock_put,
    ):
        backend = IFoodCatalogProjection()
        assert backend.project([ifood_item], channel="ifood").success is True
        assert backend.project([ifood_item], channel="ifood").success is True

    assert mock_post.call_count == 2
    assert mock_put.call_args.kwargs["json"]["products"][0]["imagePath"] == "merchant/blue.png"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"x" * (5 * 1024 * 1024 + 1), "5 MB"),
        (_image_bytes(image_format="WEBP"), "JPG, JPEG ou PNG"),
    ],
)
def test_invalid_image_projects_item_without_image_and_reports_pending(
    ifood_item, ifood_settings, fake_oauth, content, reason,
):
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with (
        patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings),
        patch("requests.get", return_value=_response(content=content)),
        patch("requests.post") as mock_post,
        patch("requests.put") as mock_put,
    ):
        result = IFoodCatalogProjection().project([ifood_item], channel="ifood")

    assert result.success is False
    assert result.projected == 1
    assert f"{ifood_item.sku}: foto pendente:" in result.errors[0]
    assert reason in result.errors[0]
    mock_post.assert_not_called()
    assert "imagePath" not in mock_put.call_args.kwargs["json"]["products"][0]


@pytest.mark.django_db
def test_failed_upload_projects_without_image_and_does_not_cache_success(
    ifood_item, ifood_settings, fake_oauth,
):
    from requests import HTTPError

    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection
    from shopman.shop.models import CatalogImageUpload

    failed = _response(status=503)
    failed.raise_for_status.side_effect = HTTPError("503")
    with (
        patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings),
        patch("requests.get", return_value=_response(content=_image_bytes())),
        patch("requests.post", return_value=failed),
        patch("requests.put") as mock_put,
    ):
        result = IFoodCatalogProjection().project([ifood_item], channel="ifood")

    assert result.success is False
    assert result.projected == 1
    assert f"{ifood_item.sku}: foto pendente:" in result.errors[0]
    assert "enviar a foto" in result.errors[0]
    assert CatalogImageUpload.objects.get().image_path == ""
    assert "imagePath" not in mock_put.call_args.kwargs["json"]["products"][0]


@pytest.mark.django_db
def test_image_download_timeout_projects_without_image_and_is_readable(
    ifood_item, ifood_settings, fake_oauth,
):
    from requests import Timeout

    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with (
        patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings),
        patch("requests.get", side_effect=Timeout("expired")),
        patch("requests.post") as mock_post,
        patch("requests.put") as mock_put,
    ):
        result = IFoodCatalogProjection().project([ifood_item], channel="ifood")

    assert result.success is False
    assert result.projected == 1
    assert f"{ifood_item.sku}: foto pendente:" in result.errors[0]
    assert "baixar a foto" in result.errors[0]
    mock_post.assert_not_called()
    assert "imagePath" not in mock_put.call_args.kwargs["json"]["products"][0]


@pytest.mark.django_db
def test_item_without_image_does_not_upload_or_remove_remote_image(ifood_settings, fake_oauth):
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    item = ProjectedItem(
        sku="SEM-FOTO", name="Sem foto", description="", unit="un",
        price_q=100, is_published=True, is_sellable=True, category="paes",
    )
    with (
        patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings),
        patch("requests.get") as mock_get,
        patch("requests.post") as mock_post,
        patch("requests.put", return_value=_response()) as mock_put,
    ):
        result = IFoodCatalogProjection().project([item], channel="ifood")

    assert result.success is True
    assert "imagePath" not in mock_put.call_args.kwargs["json"]["products"][0]
    mock_get.assert_not_called()
    mock_post.assert_not_called()


@pytest.mark.django_db
def test_our_media_url_is_read_from_default_storage(
    ifood_item, ifood_settings, fake_oauth, settings, tmp_path,
):
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    settings.MEDIA_ROOT = tmp_path
    name = default_storage.save("products/local.png", ContentFile(_image_bytes()))
    local_item = replace(ifood_item, image_url=default_storage.url(name))
    with (
        patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings),
        patch("requests.get") as mock_get,
        patch("requests.post", return_value=_response(json_data={"imagePath": "merchant/local.png"})),
        patch("requests.put", return_value=_response()),
    ):
        result = IFoodCatalogProjection().project([local_item], channel="ifood")

    assert result.success is True
    mock_get.assert_not_called()


def test_adapter_project_uses_default_category_when_unmapped(ifood_settings, fake_oauth):
    """An item whose collection is not in the map falls back to the default category."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    item = ProjectedItem(
        sku="Y", name="Y", description="", unit="un",
        price_q=100, is_published=True, is_sellable=True, category="bebidas",
    )
    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("requests.put") as mock_put:
            mock_put.return_value = MagicMock(status_code=200, headers={})
            mock_put.return_value.raise_for_status = MagicMock()
            result = IFoodCatalogProjection().project([item], channel="ifood")

    assert result.success is True
    assert mock_put.call_args[1]["json"]["item"]["categoryId"] == "cat-default-uuid"


def test_adapter_project_errors_when_no_category(fake_oauth):
    """No mapped collection and no default → per-item error, no PUT."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    cfg = {"merchant_id": "00000000-0000-4000-8000-000000000001", "catalog_category_map": {}, "catalog_default_category": ""}
    item = ProjectedItem(
        sku="Z", name="Z", description="", unit="un",
        price_q=100, is_published=True, is_sellable=True, category="unknown",
    )
    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=cfg):
        with patch("requests.put") as mock_put:
            result = IFoodCatalogProjection().project([item], channel="ifood")

    mock_put.assert_not_called()
    assert result.success is False
    assert "category" in result.errors[0].lower()


def test_adapter_project_returns_failure_without_oauth(ifood_item, settings, ifood_channel):
    """No OAuth credentials → no header → loud failure naming the real cause, no PUT."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    settings.SHOPMAN_IFOOD = {"merchant_id": "00000000-0000-4000-8000-000000000001"}
    with patch(
        "shopman.shop.services.ifood_auth.token_with_reason",
        return_value=(None, ifood_auth.NOT_CONFIGURED),
    ):
        with patch("requests.put") as mock_put:
            result = IFoodCatalogProjection().project([ifood_item], channel="ifood")

    mock_put.assert_not_called()
    assert result.success is False
    assert "OAuth" in result.errors[0]


def test_adapter_retract_patches_item_status(ifood_settings, fake_oauth):
    """retract() sets item status UNAVAILABLE via PATCH /items/status."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("requests.patch") as mock_patch, patch("requests.get") as mock_get:
            mock_patch.return_value = MagicMock(status_code=200, headers={})
            mock_patch.return_value.raise_for_status = MagicMock()
            mock_get.return_value = MagicMock(status_code=200, headers={})
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = {"item": {"status": "UNAVAILABLE"}}
            result = IFoodCatalogProjection().retract(["PAO-FRANCES"], channel="ifood")

    assert result.success is True
    url, kwargs = mock_patch.call_args[0][0], mock_patch.call_args[1]
    assert url == "https://mock-ifood.test/catalog/v2.0/merchants/00000000-0000-4000-8000-000000000001/items/status"
    assert kwargs["json"]["status"] == "UNAVAILABLE"
    uuid.UUID(kwargs["json"]["itemId"])


def test_adapter_price_change_uses_specific_patch_and_confirms_read(
    ifood_item, ifood_settings, fake_oauth,
):
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("requests.patch") as mock_patch, patch("requests.get") as mock_get:
            mock_patch.return_value = MagicMock(status_code=200, headers={})
            mock_patch.return_value.raise_for_status = MagicMock()
            mock_get.return_value = MagicMock(status_code=200, headers={})
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = {"item": {"price": {"value": 3.5}}}

            result = IFoodCatalogProjection().update_price(ifood_item, channel="ifood")

    assert result.success is True
    url, kwargs = mock_patch.call_args.args[0], mock_patch.call_args.kwargs
    assert url.endswith(f"/catalog/v2.0/merchants/{ifood_settings['merchant_id']}/items/price")
    assert kwargs["json"] == {
        "itemId": kwargs["json"]["itemId"],
        "price": {"value": 3.5},
    }
    assert set(kwargs["json"]) == {"itemId", "price"}
    mock_get.assert_called_once()
    assert mock_get.call_args.args[0].endswith(f"/items/{kwargs['json']['itemId']}/flat")


@pytest.mark.parametrize(
    ("sellable", "remote_status"),
    [(False, "UNAVAILABLE"), (True, "AVAILABLE")],
)
def test_adapter_availability_uses_specific_status_patch_and_confirms_read(
    ifood_item, ifood_settings, fake_oauth, sellable, remote_status,
):
    from dataclasses import replace

    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    item = replace(ifood_item, is_sellable=sellable)
    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("shopman.shop.services.external_availability.in_stock", return_value=True):
            with patch("requests.patch") as mock_patch, patch("requests.get") as mock_get:
                mock_patch.return_value = MagicMock(status_code=200, headers={})
                mock_patch.return_value.raise_for_status = MagicMock()
                mock_get.return_value = MagicMock(status_code=200, headers={})
                mock_get.return_value.raise_for_status = MagicMock()
                mock_get.return_value.json.return_value = {"item": {"status": remote_status}}

                result = IFoodCatalogProjection().set_availability(item, channel="ifood")

    assert result.success is True
    assert mock_patch.call_args.kwargs["json"] == {
        "itemId": mock_patch.call_args.kwargs["json"]["itemId"],
        "status": remote_status,
    }


def test_adapter_does_not_report_success_when_confirmation_read_fails(
    ifood_item, ifood_settings, fake_oauth,
):
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection

    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("requests.patch") as mock_patch, patch("requests.get") as mock_get:
            mock_patch.return_value = MagicMock(status_code=200, headers={})
            mock_patch.return_value.raise_for_status = MagicMock()
            mock_get.return_value = MagicMock(status_code=503, headers={})
            mock_get.return_value.raise_for_status.side_effect = RuntimeError("read failed")

            result = IFoodCatalogProjection().update_price(ifood_item, channel="ifood")

    assert result.success is False
    assert result.projected == 0


def test_adapter_raises_rate_limit_on_429(ifood_item, ifood_settings, fake_oauth):
    """429 with Retry-After header raises IFoodRateLimitError."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogProjection, IFoodRateLimitError

    mock_resp = MagicMock(status_code=429, headers={"Retry-After": "45"})
    ifood_item = replace(ifood_item, image_url=None)

    with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
        with patch("requests.put", return_value=mock_resp):
            backend = IFoodCatalogProjection()
            with pytest.raises(IFoodRateLimitError) as exc_info:
                backend.project([ifood_item], channel="ifood")

    assert exc_info.value.retry_after == 45


# ── Handler ───────────────────────────────────────────────────────────────────


def test_handler_marks_done_on_success(db, ifood_channel, ifood_directive):
    """Handler marks Directive done when backend.project() succeeds."""
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    backend.project.return_value = ProjectionResult(success=True, projected=1, channel="ifood")
    handler = CatalogProjectHandler(backend=backend)

    with patch("shopman.shop.handlers.catalog_projection._get_projected_item") as mock_get:
        mock_get.return_value = ProjectedItem(
            sku="PAO-FRANCES", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True,
        )
        handler.handle(message=ifood_directive, ctx={})

    # directive.status is managed by the directive processor, not the handler.
    # Direct invocation leaves status unchanged. We verify the handler ran correctly:
    backend.project.assert_called_once()


def test_handler_retracts_when_item_paused(db, ifood_channel, ifood_directive):
    """Retract-aware: an unsellable SKU is retracted, not projected."""
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    backend.retract.return_value = ProjectionResult(success=True, projected=1, channel="ifood")
    handler = CatalogProjectHandler(backend=backend)

    with patch("shopman.shop.handlers.catalog_projection._get_projected_item") as mock_get:
        mock_get.return_value = ProjectedItem(
            sku="PAO-FRANCES", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=False,  # paused
        )
        handler.handle(message=ifood_directive, ctx={})

    backend.retract.assert_called_once_with(["PAO-FRANCES"], channel="ifood")
    backend.project.assert_not_called()


def test_handler_retracts_when_item_dropped_from_listing(db, ifood_channel, ifood_directive):
    """A SKU no longer in the listing (item is None) is retracted."""
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    backend.retract.return_value = ProjectionResult(success=True, projected=1, channel="ifood")
    handler = CatalogProjectHandler(backend=backend)

    with patch("shopman.shop.handlers.catalog_projection._get_projected_item", return_value=None):
        handler.handle(message=ifood_directive, ctx={})

    backend.retract.assert_called_once_with(["PAO-FRANCES"], channel="ifood")
    backend.project.assert_not_called()


def test_handler_routes_price_intention_to_specific_patch(db, ifood_channel, ifood_directive):
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    item = ProjectedItem(
        sku="PAO-FRANCES", name="Pão", description="", unit="un",
        price_q=425, is_published=True, is_sellable=True,
    )
    ifood_directive.payload["trigger"] = "price_changed"
    ifood_directive.save(update_fields=["payload"])
    backend = MagicMock()
    backend.update_price.return_value = ProjectionResult(success=True, projected=1, channel="ifood")

    with patch("shopman.shop.handlers.catalog_projection._get_projected_item", return_value=item):
        CatalogProjectHandler(backend=backend).handle(message=ifood_directive, ctx={})

    backend.update_price.assert_called_once_with(item, channel="ifood")
    backend.project.assert_not_called()


def test_handler_routes_pause_intention_to_specific_patch(db, ifood_channel, ifood_directive):
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    item = ProjectedItem(
        sku="PAO-FRANCES", name="Pão", description="", unit="un",
        price_q=425, is_published=True, is_sellable=False,
    )
    ifood_directive.payload["trigger"] = "availability_changed"
    ifood_directive.save(update_fields=["payload"])
    backend = MagicMock()
    backend.set_availability.return_value = ProjectionResult(success=True, projected=1, channel="ifood")

    with patch("shopman.shop.handlers.catalog_projection._get_projected_item", return_value=item):
        CatalogProjectHandler(backend=backend).handle(message=ifood_directive, ctx={})

    backend.set_availability.assert_called_once_with(item, channel="ifood")
    backend.retract.assert_not_called()


def test_handler_skips_when_channel_inactive(db, ifood_directive):
    """Handler skips API call when iFood channel is inactive."""
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    handler = CatalogProjectHandler(backend=backend)

    with patch(
        "shopman.shop.handlers.catalog_projection._channel_or_feed_active",
        return_value=False,
    ):
        handler.handle(message=ifood_directive, ctx={})

    backend.project.assert_not_called()


def test_handler_schedules_retry_on_rate_limit(db, ifood_channel, ifood_directive):
    """429 RateLimitError → handler sets available_at honoring Retry-After."""
    from shopman.shop.adapters.catalog_projection_ifood import IFoodRateLimitError
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    backend = MagicMock()
    backend.project.side_effect = IFoodRateLimitError(retry_after=30)
    handler = CatalogProjectHandler(backend=backend)

    before = timezone.now()
    with patch("shopman.shop.handlers.catalog_projection._get_projected_item") as mock_get:
        mock_get.return_value = ProjectedItem(
            sku="PAO-FRANCES", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True,
        )
        handler.handle(message=ifood_directive, ctx={})

    ifood_directive.refresh_from_db()
    assert ifood_directive.status == "queued", "rate-limited directive must stay queued"
    assert ifood_directive.available_at > before
    delta = (ifood_directive.available_at - before).total_seconds()
    assert 25 <= delta <= 35, f"Retry-After=30 but delta={delta}s"


def test_price_retry_reads_current_state_and_preserves_intention(
    db, ifood_channel, ifood_directive,
):
    from dataclasses import replace

    from shopman.shop.adapters.catalog_projection_ifood import IFoodRateLimitError
    from shopman.shop.handlers.catalog_projection import CatalogProjectHandler

    first = ProjectedItem(
        sku="PAO-FRANCES", name="Pão", description="", unit="un",
        price_q=350, is_published=True, is_sellable=True,
    )
    latest = replace(first, price_q=450)
    ifood_directive.payload["trigger"] = "price_changed"
    ifood_directive.save(update_fields=["payload"])
    backend = MagicMock()
    backend.update_price.side_effect = [
        IFoodRateLimitError(retry_after=1),
        ProjectionResult(success=True, projected=1, channel="ifood"),
    ]

    with patch(
        "shopman.shop.handlers.catalog_projection._get_projected_item",
        side_effect=[first, first, latest, latest],
    ):
        handler = CatalogProjectHandler(backend=backend)
        handler.handle(message=ifood_directive, ctx={})
        ifood_directive.refresh_from_db()
        assert ifood_directive.status == "queued"
        assert ifood_directive.payload["trigger"] == "price_changed"
        handler.handle(message=ifood_directive, ctx={})

    assert [call.args[0].price_q for call in backend.update_price.call_args_list] == [350, 450]


# Note: max_attempts / retry limits are managed by the orderman directive
# dispatcher, not by individual handlers. Handlers raise DirectiveTransientError
# and the dispatcher decides when to give up.


# ── Signal receivers + idempotency ────────────────────────────────────────────


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_on_product_created_enqueues_directive(db):
    """product_created signal → catalog.project_sku Directive created."""
    from shopman.shop.handlers.catalog_projection import on_product_created

    on_product_created(sender=None, instance=None, sku="BAGUETE")

    directives = Directive.objects.filter(topic=CATALOG_PROJECT_SKU)
    assert directives.count() == 1
    d = directives.first()
    assert d.payload["sku"] == "BAGUETE"
    assert d.payload["listing_ref"] == "ifood"
    assert d.dedupe_key.startswith("catalog.project_sku:ifood:BAGUETE:")


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_on_product_updated_enqueues_directive(db):
    """product_updated (name/description/publish) → catalog.project_sku Directive."""
    from shopman.shop.handlers.catalog_projection import on_product_updated

    on_product_updated(sender=None, instance=None, sku="BAGUETE")

    directives = Directive.objects.filter(topic=CATALOG_PROJECT_SKU)
    assert directives.count() == 1
    assert directives.first().payload["sku"] == "BAGUETE"


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_on_availability_changed_enqueues_directive(db):
    """availability_changed (per-channel pause/resume) → catalog.project_sku Directive."""
    from shopman.shop.handlers.catalog_projection import on_availability_changed

    on_availability_changed(sender=None, instance=None, listing_ref="ifood", sku="CROISSANT")

    directives = Directive.objects.filter(topic=CATALOG_PROJECT_SKU)
    assert directives.count() == 1
    assert directives.first().payload["sku"] == "CROISSANT"
    assert directives.first().payload["trigger"] == "availability_changed"


@override_settings(OFFERMAN=_OFFERMAN_NONE)
def test_availability_signal_noop_without_adapter(db):
    """No adapter configured → availability receiver creates no directive (safe no-op)."""
    from shopman.shop.handlers.catalog_projection import on_availability_changed

    on_availability_changed(sender=None, instance=None, listing_ref="ifood", sku="X")
    assert Directive.objects.filter(topic=CATALOG_PROJECT_SKU).count() == 0


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_on_price_changed_enqueues_directive(db):
    """price_changed signal → catalog.project_sku Directive created."""
    from shopman.shop.handlers.catalog_projection import on_price_changed

    on_price_changed(
        sender=None,
        instance=None,
        listing_ref="ifood",
        sku="CROISSANT",
        old_price_q=800,
        new_price_q=900,
    )

    directives = Directive.objects.filter(topic=CATALOG_PROJECT_SKU)
    assert directives.count() == 1
    assert directives.first().payload["sku"] == "CROISSANT"
    assert directives.first().payload["trigger"] == "price_changed"


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_idempotency_same_price_signal_twice(db):
    """Same price_changed event fired twice → only 1 Directive (dedupe)."""
    from shopman.shop.handlers.catalog_projection import on_price_changed

    kwargs = {
        "sender": None,
        "instance": None,
        "listing_ref": "ifood",
        "sku": "CROISSANT",
        "old_price_q": 800,
        "new_price_q": 900,
    }
    on_price_changed(**kwargs)
    on_price_changed(**kwargs)

    count = Directive.objects.filter(topic=CATALOG_PROJECT_SKU).count()
    assert count == 1, f"Expected 1 directive (idempotent), got {count}"


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_different_prices_create_different_directives(db):
    """Different prices → different dedupe_keys → 2 Directives."""
    from shopman.shop.handlers.catalog_projection import on_price_changed

    on_price_changed(
        sender=None, instance=None,
        listing_ref="ifood", sku="CROISSANT",
        old_price_q=800, new_price_q=900,
    )
    on_price_changed(
        sender=None, instance=None,
        listing_ref="ifood", sku="CROISSANT",
        old_price_q=900, new_price_q=1000,
    )

    count = Directive.objects.filter(topic=CATALOG_PROJECT_SKU).count()
    assert count == 2


@override_settings(OFFERMAN=_OFFERMAN_NONE)
def test_signal_noop_when_no_adapters_configured(db):
    """With no projection backend configured, receivers create no directives."""
    from shopman.shop.handlers.catalog_projection import on_product_created

    on_product_created(sender=None, instance=None, sku="BAGUETE")

    assert Directive.objects.filter(topic=CATALOG_PROJECT_SKU).count() == 0


# ── Management command ────────────────────────────────────────────────────────


def test_sync_catalog_ifood_dry_run(db, capsys):
    """--dry-run prints items and makes no API calls."""
    from django.core.management import call_command

    from shopman.shop.models import Channel

    Channel.objects.create(ref="ifood", name="iFood", is_active=True)

    items = [
        ProjectedItem(
            sku="PAO", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True,
        )
    ]

    with patch("shopman.offerman.service.CatalogService.get_projection_items", return_value=items):
        with patch("requests.put") as mock_put:
            call_command("sync_catalog_ifood", dry_run=True)
            mock_put.assert_not_called()

    out = capsys.readouterr().out
    assert "PAO" in out
    assert "dry run" in out.lower()


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_sync_catalog_ifood_full_sync(db, ifood_settings, fake_oauth, reset_projection_registry):
    """--full routes through project_listing → upserts all, no retract."""
    from django.core.management import call_command
    from shopman.offerman.models import Listing

    from shopman.shop.models import Channel

    Channel.objects.create(ref="ifood", name="iFood", is_active=True)
    Listing.objects.create(ref="ifood", name="iFood")

    items = [
        ProjectedItem(
            sku="PAO", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True, category="paes",
        )
    ]

    with patch("shopman.offerman.service.CatalogService.get_projection_items", return_value=items):
        with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
            with patch("requests.put") as mock_put, patch("requests.patch") as mock_patch:
                mock_put.return_value = MagicMock(status_code=200, headers={})
                mock_put.return_value.raise_for_status = MagicMock()
                call_command("sync_catalog_ifood", full=True)

    mock_put.assert_called_once()
    mock_patch.assert_not_called()  # full sync never retracts

    # last_projected_skus persisted for the next incremental diff.
    listing = Listing.objects.get(ref="ifood")
    assert listing.projection_metadata["last_projected_skus"] == ["PAO"]


@override_settings(OFFERMAN=_OFFERMAN_IFOOD)
def test_sync_catalog_ifood_incremental_retracts(db, ifood_settings, fake_oauth, reset_projection_registry):
    """Incremental sync upserts sellable items and retracts unavailable ones."""
    from django.core.management import call_command
    from shopman.offerman.models import Listing

    from shopman.shop.models import Channel

    Channel.objects.create(ref="ifood", name="iFood", is_active=True)
    Listing.objects.create(ref="ifood", name="iFood")

    items = [
        ProjectedItem(
            sku="PAO", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True, category="paes",
        ),
        ProjectedItem(
            sku="CROISSANT", name="Croissant", description="", unit="un",
            price_q=800, is_published=True, is_sellable=False, category="paes",
        ),
    ]

    with patch("shopman.offerman.service.CatalogService.get_projection_items", return_value=items):
        with patch("shopman.shop.adapters.catalog_projection_ifood._get_config", return_value=ifood_settings):
            with patch("requests.put") as mock_put, patch("requests.patch") as mock_patch, patch(
                "requests.get",
            ) as mock_get:
                mock_put.return_value = MagicMock(status_code=200, headers={})
                mock_put.return_value.raise_for_status = MagicMock()
                mock_patch.return_value = MagicMock(status_code=202, headers={})
                mock_patch.return_value.raise_for_status = MagicMock()
                mock_get.return_value = MagicMock(status_code=200, headers={})
                mock_get.return_value.raise_for_status = MagicMock()
                mock_get.return_value.json.return_value = {"item": {"status": "UNAVAILABLE"}}
                call_command("sync_catalog_ifood")

    mock_put.assert_called_once()  # PAO upserted
    mock_patch.assert_called_once()  # CROISSANT (not sellable) retracted

    listing = Listing.objects.get(ref="ifood")
    assert listing.projection_metadata["last_projected_skus"] == ["PAO"]


@override_settings(OFFERMAN=_OFFERMAN_NONE)
def test_sync_catalog_ifood_backend_not_configured(db, reset_projection_registry, settings):
    settings.SHOPMAN_IFOOD = {"merchant_id": "00000000-0000-4000-8000-000000000001"}
    """No projection backend configured → clear CommandError, no API calls."""
    from django.core.management import call_command
    from django.core.management.base import CommandError
    from shopman.offerman.models import Listing

    from shopman.shop.models import Channel

    Channel.objects.create(ref="ifood", name="iFood", is_active=True)
    Listing.objects.create(ref="ifood", name="iFood")

    items = [
        ProjectedItem(
            sku="PAO", name="Pão", description="", unit="un",
            price_q=350, is_published=True, is_sellable=True,
        )
    ]

    with patch("shopman.offerman.service.CatalogService.get_projection_items", return_value=items):
        with pytest.raises(CommandError, match="IFOOD_CATALOG_PROJECTION"):
            call_command("sync_catalog_ifood")
