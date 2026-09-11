"""The documented partial product patch preserves untargeted canonical facts."""
import pytest
from shopman.offerman.models import Product

from shopman.backstage.services import catalog
from shopman.backstage.services.exceptions import CatalogError

pytestmark = pytest.mark.django_db


def test_partial_nutrient_patch_preserves_untouched_values():
    product = Product.objects.create(sku="NUTRIENT-PARTIAL", name="Synthetic product", base_price_q=1000,
        nutrition_facts={"serving_size_g": 50, "energy_kcal": 120, "proteins_g": 4, "auto_filled": True})
    result = catalog.update_product_detail(product.sku, {"nutrition_facts": {"sodium_mg": 25}})
    assert result["nutrition_facts"]["serving_size_g"] == 50
    assert result["nutrition_facts"]["energy_kcal"] == 120
    assert result["nutrition_facts"]["proteins_g"] == 4
    assert result["nutrition_facts"]["sodium_mg"] == 25
    assert not result["nutrition_auto_filled"]


def test_empty_nutrition_patch_does_not_remove_recipe_provenance():
    facts = {"serving_size_g": 50, "energy_kcal": 120, "auto_filled": True}
    product = Product.objects.create(sku="NUTRIENT-EMPTY", name="Synthetic product", base_price_q=1000, nutrition_facts=facts)
    catalog.update_product_detail(product.sku, {"nutrition_facts": {}})
    product.refresh_from_db()
    assert product.nutrition_facts == facts


@pytest.mark.parametrize("field", ["allergens", "dietary_info"])
@pytest.mark.parametrize("invalid", ["leite", [12], {"unexpected": "shape"}])
def test_label_list_has_strict_shape_and_no_partial_name_save(field, invalid):
    product = Product.objects.create(sku="STRICT-LABEL", name="Before", base_price_q=1000)
    with pytest.raises(CatalogError):
        catalog.update_product_detail(product.sku, {"name": "After", field: invalid})
    product.refresh_from_db()
    assert product.name == "Before"
