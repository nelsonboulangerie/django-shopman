"""Reconciliação isolada: anúncios e códigos nunca confirmam vínculo sozinhos."""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest

from shopman.shop.services.ifood_catalog_reconciliation import reconcile_ifood_inventory


@dataclass(frozen=True)
class Product:
    sku: str
    name: str


@pytest.fixture
def inventory():
    return json.loads((Path(__file__).parent / "fixtures/ifood_catalog_inventory.json").read_text())


def reconcile(categories, products=None, **scope):
    return reconcile_ifood_inventory(
        merchant_id=scope.get("merchant_id", "merchant-a"),
        catalog_id=scope.get("catalog_id", "catalog-a"),
        context=scope.get("context", "DEFAULT"),
        categories=categories,
        products=products if products is not None else [Product("BG-1", "Baguete"), Product("CR-1", "Croissant")],
    )


def test_fixture_preserves_every_ad_and_pending_summary(inventory):
    before = deepcopy(inventory)
    result = reconcile(inventory)
    assert inventory == before
    assert [row.status for row in result.items] == [
        "suggested", "ambiguous_code", "missing_code", "ambiguous_code", "unmatched_code",
    ]
    assert result.summary.total_items == result.summary.pending == 5
    assert result.summary.suggested == 1
    assert result.summary.ambiguous == 2
    assert result.summary.unmatched == 2
    assert result.summary.invalid_identity == 0
    first = result.items[0]
    assert (first.item_id, first.product_id, first.category_id) == (
        "item-baguette", "product-baguette", "category-bread",
    )
    assert first.candidate_skus == ("BG-1",)
    duplicates = [row for row in result.items if row.external_code == "CR-1"]
    assert len(duplicates) == 2
    assert len({row.item_id for row in duplicates}) == 2
    assert len({row.category_id for row in duplicates}) == 2
    assert {row.product_id for row in duplicates} == {"product-croissant"}
    with pytest.raises(FrozenInstanceError):
        first.status = "confirmed"


def test_name_never_provides_identity_candidate(inventory):
    rows = reconcile(inventory).items
    assert rows[2].name == rows[4].name == "Baguete"
    assert rows[2].candidate_skus == rows[4].candidate_skus == ()


@pytest.mark.parametrize("code", ["bg-1", " BG-1", "BG-1 ", 123, None])
def test_exact_code_does_not_normalize_or_coerce(inventory, code):
    inventory[0]["items"] = [dict(inventory[0]["items"][0], externalCode=code)]
    row = reconcile(inventory[:1]).items[0]
    assert row.status != "suggested"
    assert row.candidate_skus == ()


def test_duplicate_local_code_is_ambiguous(inventory):
    row = reconcile(inventory, [Product("BG-1", "A"), Product("BG-1", "B")]).items[0]
    assert row.status == "ambiguous_code"
    assert row.candidate_skus == ("BG-1",)


def test_duplicate_remote_identity_is_not_collapsed(inventory):
    inventory[1]["items"].append(deepcopy(inventory[0]["items"][0]))
    rows = [r for r in reconcile(inventory).items if r.item_id == "item-baguette"]
    assert len(rows) == 2
    assert {r.status for r in rows} == {"duplicate_identity"}


@pytest.mark.parametrize("field", ["id", "productId"])
def test_missing_identity_never_suggests(inventory, field):
    inventory[0]["items"][0].pop(field)
    result = reconcile(inventory)
    assert result.items[0].status == "invalid_identity"
    assert result.summary.invalid_identity == 1


def test_category_identity_required(inventory):
    inventory[0].pop("id")
    assert reconcile(inventory).items[0].status == "invalid_identity"


def test_scopes_remain_distinct_and_do_not_share_code_counts(inventory):
    one = inventory[:1]
    one[0]["items"] = one[0]["items"][:1]
    results = [reconcile(one, **scope) for scope in [
        {}, {"merchant_id": "merchant-b"}, {"catalog_id": "catalog-b"}, {"context": "INDOOR"},
    ]]
    assert all(r.items[0].status == "suggested" for r in results)
    assert len({(r.items[0].merchant_id, r.items[0].catalog_id, r.items[0].context) for r in results}) == 4


@pytest.mark.parametrize("scope", [{"merchant_id": ""}, {"catalog_id": None}, {"context": " "}])
def test_scope_is_mandatory(inventory, scope):
    with pytest.raises(ValueError, match="loja, catálogo e contexto"):
        reconcile(inventory, **scope)


@pytest.mark.parametrize("categories", [{}, [{"id": "category"}], [{"items": None}], [{"items": [None]}]])
def test_malformed_snapshot_is_explicit_error(categories):
    with pytest.raises(ValueError):
        reconcile(categories)


def test_empty_snapshot_and_empty_categories_are_valid():
    for categories in [[], [{"id": "category", "items": []}]]:
        result = reconcile(categories)
        assert result.items == ()
        assert result.summary.pending == 0


def test_context_override_resolves_effective_code(inventory):
    categories = inventory[:1]
    categories[0]["items"] = categories[0]["items"][:1]
    categories[0]["items"][0]["contextModifiers"] = [
        {"catalogContext": "WHITELABEL", "externalCode": "CR-1"},
    ]
    default = reconcile(categories).items[0]
    white = reconcile(categories, context="WHITELABEL").items[0]
    assert default.external_code == default.root_external_code == "BG-1"
    assert white.root_external_code == "BG-1"
    assert white.external_code == "CR-1"
    assert white.candidate_skus == ("CR-1",)
    assert white.status == default.status == "suggested"


@pytest.mark.parametrize("modifier", [
    {"catalogContext": "WHITELABEL"},
    {"catalogContext": "WHITELABEL", "itemContextId": "context-item"},
    {"catalogContext": "INDOOR", "externalCode": "CR-1"},
])
def test_absent_override_preserves_root(inventory, modifier):
    inventory[0]["items"][0]["contextModifiers"] = [modifier]
    row = reconcile(inventory, context="WHITELABEL").items[0]
    assert row.external_code == "BG-1"
    assert row.status == "suggested"


def test_empty_override_does_not_fall_back(inventory):
    inventory[0]["items"][0]["contextModifiers"] = [
        {"catalogContext": "DEFAULT", "externalCode": ""},
    ]
    row = reconcile(inventory).items[0]
    assert row.status == "missing_code"
    assert row.candidate_skus == ()
    assert row.external_code == ""
    assert row.root_external_code == "BG-1"


@pytest.mark.parametrize("modifiers", [
    None, {}, [None], [{}], [{"catalogContext": ""}],
    [{"catalogContext": "DEFAULT", "externalCode": None}],
    [{"catalogContext": "DEFAULT", "externalCode": 123}],
    [{"catalogContext": "DEFAULT"}, {"catalogContext": "DEFAULT"}],
    [{"catalogContext": "WHITELABEL", "externalCode": "BG-1"},
     {"catalogContext": "WHITELABEL", "externalCode": "CR-1"}],
])
def test_malformed_or_duplicate_modifier_never_suggests(inventory, modifiers):
    inventory[0]["items"][0]["contextModifiers"] = modifiers
    result = reconcile(inventory)
    assert result.items[0].status == "invalid_context"
    assert result.items[0].candidate_skus == ()
    assert result.summary.invalid_context == 1


def test_duplicate_codes_count_effective_context(inventory):
    inventory[0]["items"][0]["contextModifiers"] = [
        {"catalogContext": "WHITELABEL", "externalCode": "CR-1"},
    ]
    assert reconcile(inventory).items[0].status == "suggested"
    result = reconcile(inventory, context="WHITELABEL")
    assert result.items[0].status == "ambiguous_code"
    assert result.summary.ambiguous == 3


@pytest.mark.parametrize("category_id", [None, "other-category"])
def test_conflicting_category_identity_rejects_snapshot(inventory, category_id):
    inventory[0]["items"][0]["categoryId"] = category_id
    with pytest.raises(ValueError, match="diverge"):
        reconcile(inventory)


def test_matching_category_identity_is_valid(inventory):
    inventory[0]["items"][0]["categoryId"] = inventory[0]["id"]
    assert reconcile(inventory).items[0].status == "suggested"
