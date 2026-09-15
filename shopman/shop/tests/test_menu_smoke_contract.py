import pytest

from scripts.check_menu_smoke import check_menu


def product(sku, *, paused=False, available=True):
    return {"sku": sku, "is_paused": paused, "availability": "available" if available else "unavailable",
            "can_add_to_cart": available and not paused}


def test_curated_pauses_do_not_demand_ten_sellable_products():
    data = {"catalog": {"items": [product(str(i), paused=i < 28) for i in range(30)]}}
    assert check_menu(data) == {"skus": 30, "paused": 28, "active": 2, "available": 2}


def test_sections_and_cart_cannot_inflate_canonical_catalog():
    data = {"catalog": {"items": [product("A")], "featured": [product(str(i)) for i in range(40)]},
            "cart": {"items": [product("B")]}}
    with pytest.raises(ValueError, match="piso"):
        check_menu(data)


def test_duplicate_sku_is_only_one_product():
    with pytest.raises(ValueError, match="piso"):
        check_menu({"catalog": {"items": [product("A")] * 30}})


@pytest.mark.parametrize("paused,reason", [(True, "curadoria"), (False, "disponibilidade")])
def test_zero_purchase_capacity_still_fails(paused, reason):
    with pytest.raises(ValueError, match=reason):
        check_menu({"catalog": {"items": [product(str(i), paused=paused, available=False) for i in range(30)]}})


def test_missing_canonical_catalog_is_a_contract_failure():
    with pytest.raises(ValueError, match="contrato"):
        check_menu({"sections": [product("A")]})
