from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shopman.shop.services import ifood_catalog_categories as categories

MERCHANT = "00000000-0000-4000-8000-000000000001"
CFG = {
    "merchant_id": MERCHANT,
    "api_base": "https://mock-ifood.test",
    "timeout": 7,
}


@pytest.fixture(autouse=True)
def ifood_configuration(settings):
    settings.SHOPMAN_IFOOD = dict(CFG)
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = {
        "environment": "test",
        "merchant_allowlist": [MERCHANT],
    }


@pytest.fixture
def channel(db):
    from shopman.shop.models import Channel

    return Channel.objects.create(ref="ifood", name="iFood")


@pytest.fixture
def collection(db):
    from shopman.offerman.models import Collection

    return Collection.objects.create(ref="paes", name="Pães")


@pytest.fixture
def oauth_headers():
    with patch(
        "shopman.shop.services.ifood_catalog_categories.ifood_auth.headers_with_reason",
        return_value=({"Authorization": "Bearer test"}, ""),
    ):
        yield


def _response(status=200, body=None, headers=None):
    response = MagicMock(status_code=status, headers=headers or {})
    response.json.return_value = {} if body is None else body
    response.raise_for_status.side_effect = None
    return response


def test_list_categories_uses_include_items(channel, oauth_headers):
    with patch("requests.get", return_value=_response(body=[{"id": "cat-1"}])) as request:
        result = categories.list_categories(channel_ref="ifood", catalog_ref="catalog-1")

    assert result == [{"id": "cat-1"}]
    request.assert_called_once_with(
        "https://mock-ifood.test/catalog/v2.0/merchants/"
        f"{MERCHANT}/catalogs/catalog-1/categories?includeItems=true",
        headers={"Authorization": "Bearer test"},
        timeout=7,
    )


def test_create_category_sends_only_required_fields(channel, oauth_headers):
    with patch("requests.post", return_value=_response(status=201)) as request:
        categories.create_category(
            channel_ref="ifood", catalog_ref="catalog-1", name="Pães",
        )

    assert request.call_args.kwargs["json"] == {
        "name": "Pães",
        "status": "AVAILABLE",
        "template": "DEFAULT",
    }


@pytest.mark.parametrize(
    ("operation", "argument", "expected"),
    [
        (categories.rename_category, {"name": "Padaria"}, {"name": "Padaria"}),
        (categories.reorder_category, {"index": 3}, {"index": 3}),
        (categories.set_category_status, {"status": "UNAVAILABLE"}, {"status": "UNAVAILABLE"}),
    ],
)
def test_patch_category_sends_only_the_intended_field(
    channel, oauth_headers, operation, argument, expected,
):
    with patch("requests.patch", return_value=_response()) as request:
        operation(
            channel_ref="ifood",
            catalog_ref="catalog-1",
            category_ref="category-1",
            **argument,
        )

    assert request.call_args.kwargs["json"] == expected


def test_conflict_never_attempts_a_second_creation(channel, oauth_headers):
    with patch("requests.post", return_value=_response(status=409)) as request:
        with pytest.raises(categories.IFoodCategoryConflict, match="reconcilie"):
            categories.create_category(
                channel_ref="ifood", catalog_ref="catalog-1", name="Pães",
            )

    assert request.call_count == 1


def test_rate_limit_preserves_intention(channel, oauth_headers):
    from shopman.shop.adapters.catalog_projection_ifood import IFoodRateLimitError

    with patch(
        "requests.patch",
        return_value=_response(status=429, headers={"Retry-After": "23"}),
    ):
        with pytest.raises(IFoodRateLimitError) as caught:
            categories.reorder_category(
                channel_ref="ifood",
                catalog_ref="catalog-1",
                category_ref="category-1",
                index=4,
            )

    assert caught.value.retry_after == 23
    assert caught.value.intention == {"index": 4}


def test_write_guard_runs_before_oauth_or_http(channel, settings):
    settings.SHOPMAN_IFOOD_CATALOG_WRITE_POLICY = None
    with patch(
        "shopman.shop.services.ifood_catalog_categories.ifood_auth.headers_with_reason",
    ) as oauth:
        with patch("requests.get") as request:
            from shopman.shop.adapters.catalog_projection_ifood import IFoodCatalogWriteBlocked

            with pytest.raises(IFoodCatalogWriteBlocked):
                categories.list_categories(channel_ref="ifood", catalog_ref="catalog-1")

    oauth.assert_not_called()
    request.assert_not_called()


def test_managed_mapping_overrides_legacy_and_keeps_legacy_default(channel, collection):
    categories.set_collection_category(
        channel_ref="ifood", collection_ref="paes", category_ref="managed-category",
    )

    mapping, default = categories.category_mapping(
        "ifood",
        {
            "catalog_category_map": {"paes": "legacy-category", "bolos": "legacy-cakes"},
            "catalog_default_category": "legacy-default",
        },
    )

    assert mapping == {"paes": "managed-category", "bolos": "legacy-cakes"}
    assert default == "legacy-default"


def test_adapter_reads_managed_mapping_before_legacy(
    channel, collection, settings, django_assert_num_queries,
):
    from shopman.shop.adapters.catalog_projection_ifood import _get_config

    settings.SHOPMAN_IFOOD = {
        **CFG,
        "catalog_category_map": {"paes": "legacy-category"},
        "catalog_default_category": "legacy-default",
    }
    categories.set_collection_category(
        channel_ref="ifood", collection_ref="paes", category_ref="managed-category",
    )

    with django_assert_num_queries(1):
        resolved = _get_config("ifood")

    assert resolved["catalog_category_map"] == {"paes": "managed-category"}
    assert resolved["catalog_default_category"] == "legacy-default"


def test_empty_mapping_does_not_create_category(channel, oauth_headers):
    with patch("requests.post") as request:
        with pytest.raises(categories.IFoodCategoryOperationError, match="Nenhuma categoria"):
            categories.resolve_category_ref(
                channel_ref="ifood", collection_ref="paes", legacy_config={},
            )

    request.assert_not_called()
