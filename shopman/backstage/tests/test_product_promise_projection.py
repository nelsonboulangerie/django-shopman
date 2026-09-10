"""A leitura que responde: o que este produto mostra ao cliente está atualizado?

Bloco C do WP-FICHA-DE-PRODUTO-E-PROMESSA. Cobre a projection e o endpoint:
valor, origem, versão, defasagem, quem conferiu — e a divergência do peso à
mão, que acusa sem nunca sobrescrever.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman.models import Product

from shopman.backstage.projections.product_promise import (
    SOURCE_UNKNOWN,
    VERSION_LABEL_UNVERSIONED,
    build_catalog_promise,
    build_product_promise,
)
from shopman.shop.services.derived_provenance import (
    FACT_DIETARY,
    FACT_NUTRITION,
    FACT_UNIT_WEIGHT,
    SOURCE_MANUAL,
    SOURCE_RECIPE,
    record_manual_audit,
)

pytestmark = pytest.mark.django_db

FLOUR = {
    "label": "Farinha de trigo", "diet": "vegan", "allergens": ["glúten"],
    "nutrition": {"energy_kcal": 364, "proteins_g": 10},
}


def _product(sku: str = "BGT", **extra) -> Product:
    extra.setdefault("unit_weight_g", None)
    return Product.objects.create(sku=sku, name="Baguete", base_price_q=900, **extra)


def _recipe(sku: str = "BGT", *, version_ref: str | None = "bgt@1") -> Recipe:
    meta = {} if version_ref is None else {"version_ref": version_ref}
    recipe = Recipe.objects.create(
        ref=f"{sku.lower()}-v1", name=f"Receita {sku}", output_sku=sku,
        batch_size=Decimal("25"), is_active=True, meta=meta,
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku="MASSA", quantity=Decimal("7.000"), unit="kg", meta=dict(FLOUR),
    )
    return recipe


def _fact(promise, name):
    return next(fact for fact in promise.facts if fact.fact == name)


class TestProjection:
    def test_a_derived_product_reads_as_in_sync_with_its_version(self):
        product = _product()
        recipe = _recipe()
        recipe.save()  # o signal deriva peso, nutrição e dieta

        product.refresh_from_db()
        promise = build_product_promise(product)

        assert promise.has_recipe is True
        assert promise.recipe_version_ref == "bgt@1"
        assert promise.is_stale is False

        weight = _fact(promise, FACT_UNIT_WEIGHT)
        assert weight.source == SOURCE_RECIPE
        assert weight.version_ref == "bgt@1"
        assert weight.is_versioned is True
        assert weight.has_value is True
        assert weight.value.endswith(" g")
        assert weight.note == "Em dia com a versão publicada da ficha."

    def test_publishing_a_new_version_makes_the_manual_fact_read_stale(self):
        product = _product(
            unit_weight_g=280,
            nutrition_facts={"energy_kcal": 111, "serving_size_g": 50, "auto_filled": False},
        )
        recipe = _recipe()
        record_manual_audit(product, FACT_NUTRITION, actor="pablo")
        product.refresh_from_db()

        recipe.meta = {**recipe.meta, "version_ref": "bgt@2"}
        recipe.save()
        product.refresh_from_db()

        nutrition = _fact(build_product_promise(product), FACT_NUTRITION)
        assert nutrition.source == SOURCE_MANUAL
        assert nutrition.is_stale is True
        assert nutrition.audited_by == "pablo"
        assert nutrition.audited_at
        assert nutrition.version_ref == "bgt@1"
        assert "Reconfira" in nutrition.note
        # E o valor manual continua intocado.
        assert product.nutrition_facts["energy_kcal"] == 111

    def test_a_value_without_a_stamp_reads_as_never_audited(self):
        product = _product(unit_weight_g=300)
        _recipe()

        weight = _fact(build_product_promise(product), FACT_UNIT_WEIGHT)
        assert weight.source == SOURCE_UNKNOWN
        assert weight.needs_audit is True
        assert weight.value == "300 g"
        assert "assine" in weight.note.lower()

    def test_a_hand_typed_weight_that_diverges_accuses_without_being_overwritten(self):
        product = _product(unit_weight_g=300)
        recipe = _recipe()
        recipe.save()  # o signal tenta derivar e recusa

        product.refresh_from_db()
        assert product.unit_weight_g == 300  # intocado

        weight = _fact(build_product_promise(product), FACT_UNIT_WEIGHT)
        assert weight.value == "300 g"
        # 7 kg / 25 = 280 g crus → 246,4 assados → 234 anunciados.
        assert weight.expected_value == "234 g"
        assert weight.diverges is True

    def test_a_derived_weight_edited_by_hand_stops_reading_as_derived(self):
        """Carimbo que descreve um número que já não está lá é carimbo mentindo."""
        product = _product()
        _recipe().save()
        product.refresh_from_db()
        assert product.unit_weight_g == 234

        product.unit_weight_g = 240
        product.save(update_fields=["unit_weight_g"])

        weight = _fact(build_product_promise(product), FACT_UNIT_WEIGHT)
        assert weight.source == SOURCE_UNKNOWN
        assert weight.needs_audit is True
        assert weight.value == "240 g"
        assert weight.expected_value == "234 g"

    def test_a_recipe_without_a_version_says_so_instead_of_promising_freshness(self):
        product = _product()
        recipe = _recipe(version_ref=None)
        recipe.save()

        product.refresh_from_db()
        promise = build_product_promise(product)
        assert promise.recipe_version_label == VERSION_LABEL_UNVERSIONED

        weight = _fact(promise, FACT_UNIT_WEIGHT)
        assert weight.version_ref == ""
        assert weight.version_label == VERSION_LABEL_UNVERSIONED
        assert weight.is_versioned is False
        assert weight.is_stale is False
        assert "não dá para detectar defasagem" in weight.note

    def test_a_product_without_a_recipe_is_nobody_elses_promise(self):
        product = _product(sku="AGUA", unit_weight_g=None)
        promise = build_product_promise(product)
        assert promise.has_recipe is False
        assert promise.is_stale is False
        assert _fact(promise, FACT_DIETARY).has_value is False

    def test_the_catalog_reading_counts_the_whole_catalog_even_when_filtered(self):
        fresh = _product(sku="BGT")
        _recipe("BGT").save()
        fresh.refresh_from_db()

        stale = _product(sku="CGO", unit_weight_g=300)
        recipe = _recipe("CGO", version_ref="cgo@1")
        recipe.save()
        record_manual_audit(stale, FACT_UNIT_WEIGHT, actor="pablo")
        recipe.meta = {**recipe.meta, "version_ref": "cgo@2"}
        recipe.save()

        everything = build_catalog_promise()
        assert everything.total_count == 2
        assert everything.stale_count == 1

        only_stale = build_catalog_promise(only_stale=True)
        assert [p.sku for p in only_stale.products] == ["CGO"]
        assert only_stale.total_count == 2  # a contagem não encolhe com o filtro


class TestEndpoint:
    @pytest.fixture
    def manager(self, client):
        user = get_user_model().objects.create_user(username="gestor", password="x")
        user.user_permissions.add(
            Permission.objects.get(codename="view_production_reports")
        )
        user.is_staff = True
        user.save()
        client.force_login(user)
        return user

    def test_the_catalog_promise_is_readable_by_the_manager(self, client, manager):
        product = _product()
        _recipe().save()
        product.refresh_from_db()

        response = client.get("/api/v1/backstage/catalog/promise/")
        assert response.status_code == 200
        promise = response.json()["promise"]
        assert promise["total_count"] == 1
        assert promise["products"][0]["sku"] == "BGT"
        assert {f["fact"] for f in promise["products"][0]["facts"]} == {
            FACT_UNIT_WEIGHT, FACT_NUTRITION, FACT_DIETARY,
        }

    def test_one_product_by_sku(self, client, manager):
        product = _product()
        _recipe().save()
        product.refresh_from_db()

        response = client.get("/api/v1/backstage/catalog/promise/BGT/")
        assert response.status_code == 200
        assert response.json()["promise"]["recipe_version_ref"] == "bgt@1"

    def test_an_unknown_sku_is_a_404(self, client, manager):
        assert client.get("/api/v1/backstage/catalog/promise/NAOEXISTE/").status_code == 404

    def test_without_the_permission_there_is_no_reading(self, client):
        user = get_user_model().objects.create_user(username="peao", password="x")
        user.is_staff = True
        user.save()
        client.force_login(user)
        assert client.get("/api/v1/backstage/catalog/promise/").status_code == 403
