"""O peso anunciado é PISO, nunca média.

Bloco D do WP-FICHA-DE-PRODUTO-E-PROMESSA. Cobre:

- a conta (cru por unidade → assado esperado → anunciado);
- o invariante: anunciado ≤ assado esperado ≤ cru, e o arredondamento é para baixo;
- a conta dá o mesmo na ficha por fornada e na ficha por unidade;
- a perda de forno da casa sai rotulada como estimativa não auditada;
- peso posto à mão não é sobrescrito;
- ficha sem ponte até grama recusa derivar, em vez de estimar por baixo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.models import Recipe, RecipeItem
from shopman.offerman.models import Product, ProductComponent

from shopman.shop.services.derived_provenance import (
    FACT_UNIT_WEIGHT,
    SOURCE_RECIPE,
    read_stamp,
    record_manual_audit,
)
from shopman.shop.services.unit_weight_from_recipe import (
    BAKE_LOSS_ESTIMATED,
    BAKE_LOSS_HOUSE_DEFAULT,
    BAKE_LOSS_WEIGHED,
    derive_unit_weight,
    fill_unit_weight_from_recipe,
    raw_unit_grams,
    weight_is_writable,
)

pytestmark = pytest.mark.django_db


def _product(sku: str = "BGT", **extra) -> Product:
    extra.setdefault("unit_weight_g", None)
    return Product.objects.create(sku=sku, name="Baguete", base_price_q=900, **extra)


def _recipe(
    sku: str = "BGT",
    *,
    batch_size: str = "25",
    grams_per_batch: str = "7000",
    meta: dict | None = None,
) -> Recipe:
    """Ficha que rende ``batch_size`` peças a partir de ``grams_per_batch`` de massa."""
    recipe = Recipe.objects.create(
        ref=f"{sku.lower()}-v1", name=f"Receita {sku}", output_sku=sku,
        batch_size=Decimal(batch_size), is_active=True,
        meta={"version_ref": f"{sku.lower()}@1", **(meta or {})},
    )
    RecipeItem.objects.create(
        recipe=recipe, input_sku="MASSA-TRADICAO",
        quantity=Decimal(grams_per_batch) / Decimal("1000"), unit="kg",
        meta={"label": "Massa tradição"},
    )
    return recipe


class TestTheMath:
    def test_raw_unit_grams_divides_the_batch_by_the_yield(self):
        recipe = _recipe()
        # 7 kg rendendo 25 peças = 280 g de massa crua por baguete.
        assert raw_unit_grams(recipe) == Decimal("280")

    def test_the_same_ficha_expressed_per_unit_gives_the_same_weight(self):
        """A ficha por unidade é reexpressão: a razão não muda, o peso não muda."""
        per_batch = derive_unit_weight(_recipe(sku="BGT"))
        per_unit = derive_unit_weight(
            _recipe(sku="BGU", batch_size="1", grams_per_batch="280")
        )
        assert per_batch.raw_unit_g == per_unit.raw_unit_g
        assert per_batch.announced_g == per_unit.announced_g

    def test_the_announced_weight_is_a_floor(self):
        derivation = derive_unit_weight(_recipe())
        # 280 g cru − 12% de forno = 246,4 g assados; −5% de folga = 234,08 g.
        assert derivation.expected_baked_g == Decimal("246.4")
        assert derivation.announced_g == 234

    @pytest.mark.parametrize(
        ("batch_size", "grams_per_batch"),
        [
            ("25", "7000"), ("1", "280"), ("12", "3600"), ("40", "2400"),
            ("25", "7001"), ("3", "181"), ("7", "1000"), ("100", "9999"),
        ],
    )
    def test_announced_never_exceeds_expected_baked_nor_raw(self, batch_size, grams_per_batch):
        """O invariante do bloco D, em oito fichas de tamanhos diferentes."""
        derivation = derive_unit_weight(
            _recipe(sku=f"P{batch_size}{grams_per_batch}", batch_size=batch_size, grams_per_batch=grams_per_batch)
        )
        assert derivation is not None
        assert Decimal(derivation.announced_g) <= derivation.expected_baked_g
        assert derivation.expected_baked_g <= derivation.raw_unit_g

    def test_rounding_goes_down_and_never_up(self):
        """Uma ficha cuja conta cai em 234,08 g anuncia 234, não 235."""
        derivation = derive_unit_weight(_recipe())
        exact = derivation.expected_baked_g * (Decimal("1") - derivation.slack_pct / Decimal("100"))
        assert exact == Decimal("234.08")
        assert derivation.announced_g == 234

    def test_a_ficha_that_yields_dough_has_no_piece_weight(self):
        recipe = _recipe(sku="MASSA", meta={"output_unit": "kg"})
        assert derive_unit_weight(recipe) is None


class TestBakeLoss:
    def test_the_house_default_is_labelled_as_an_unaudited_estimate(self):
        derivation = derive_unit_weight(_recipe())
        assert derivation.bake_loss_pct == Decimal("12")
        assert derivation.bake_loss_source == BAKE_LOSS_HOUSE_DEFAULT
        assert derivation.bake_loss_is_audited is False

    def test_a_declared_loss_without_a_scale_is_an_estimate(self):
        derivation = derive_unit_weight(_recipe(meta={"bake_loss_pct": "15"}))
        assert derivation.bake_loss_pct == Decimal("15")
        assert derivation.bake_loss_source == BAKE_LOSS_ESTIMATED
        assert derivation.bake_loss_is_audited is False

    def test_only_a_weighed_loss_with_author_and_date_counts_as_audited(self):
        derivation = derive_unit_weight(_recipe(meta={
            "bake_loss_pct": "13.5",
            "bake_loss_source": "weighed",
            "bake_loss_weighed_by": "pablo",
            "bake_loss_weighed_at": "2026-09-05",
        }))
        assert derivation.bake_loss_source == BAKE_LOSS_WEIGHED
        assert derivation.bake_loss_is_audited is True

    def test_weighed_without_a_signer_fails_closed(self):
        derivation = derive_unit_weight(_recipe(meta={
            "bake_loss_pct": "13.5", "bake_loss_source": "weighed",
        }))
        assert derivation.bake_loss_source == BAKE_LOSS_WEIGHED
        assert derivation.bake_loss_is_audited is False

    def test_an_unreadable_loss_falls_back_to_the_house_number(self):
        derivation = derive_unit_weight(_recipe(meta={"bake_loss_pct": "cento e dez"}))
        assert derivation.bake_loss_pct == Decimal("12")
        assert derivation.bake_loss_source == BAKE_LOSS_HOUSE_DEFAULT


class TestSlack:
    def test_the_ficha_can_declare_its_own_slack(self):
        derivation = derive_unit_weight(_recipe(meta={"weight_slack_pct": "0"}))
        assert derivation.slack_pct == Decimal("0")
        assert derivation.announced_g == 246  # 246,4 arredondado para baixo

    def test_more_slack_never_announces_more(self):
        tight = derive_unit_weight(_recipe(sku="A", meta={"weight_slack_pct": "2"}))
        loose = derive_unit_weight(_recipe(sku="B", meta={"weight_slack_pct": "10"}))
        assert loose.announced_g < tight.announced_g


class TestWriting:
    def test_an_empty_weight_is_filled_and_stamped(self):
        product = _product()
        _recipe()

        assert fill_unit_weight_from_recipe(product) is True
        product.refresh_from_db()
        assert product.unit_weight_g == 234
        stamp = read_stamp(product, FACT_UNIT_WEIGHT)
        assert stamp["source"] == SOURCE_RECIPE
        assert stamp["version_ref"] == "bgt@1"

    def test_a_hand_typed_weight_is_never_overwritten(self):
        product = _product(unit_weight_g=280)
        _recipe()

        assert weight_is_writable(product) is False
        assert fill_unit_weight_from_recipe(product) is False
        product.refresh_from_db()
        assert product.unit_weight_g == 280

    def test_a_signed_manual_weight_is_never_overwritten_either(self):
        product = _product(unit_weight_g=280)
        _recipe()
        record_manual_audit(product, FACT_UNIT_WEIGHT, actor="pablo")

        assert fill_unit_weight_from_recipe(product) is False
        product.refresh_from_db()
        assert product.unit_weight_g == 280
        assert read_stamp(product, FACT_UNIT_WEIGHT)["by"] == "pablo"

    def test_a_derived_weight_is_recalculated_when_the_ficha_moves(self):
        product = _product()
        recipe = _recipe()
        fill_unit_weight_from_recipe(product)
        product.refresh_from_db()
        assert product.unit_weight_g == 234

        recipe.meta = {**recipe.meta, "version_ref": "bgt@2"}
        recipe.items.all().update(quantity=Decimal("8.000"))
        recipe.save()  # o signal recalcula

        product.refresh_from_db()
        # 8 kg / 25 = 320 g cru → 281,6 assados → 267,52 → 267.
        assert product.unit_weight_g == 267
        assert read_stamp(product, FACT_UNIT_WEIGHT)["version_ref"] == "bgt@2"

    def test_editing_a_derived_weight_by_hand_wins_over_the_next_derivation(self):
        """Corrigir o peso no Admin não pode ser revertido calado pela ficha."""
        product = _product()
        recipe = _recipe()
        fill_unit_weight_from_recipe(product)
        product.refresh_from_db()
        assert product.unit_weight_g == 234

        product.unit_weight_g = 240
        product.save(update_fields=["unit_weight_g"])

        assert weight_is_writable(product) is False
        recipe.save()
        product.refresh_from_db()
        assert product.unit_weight_g == 240

    def test_a_ficha_edited_without_a_new_version_still_recalculates(self):
        """Sem versão nova o número muda mesmo assim — e o carimbo o acompanha.

        Se o carimbo guardasse o valor antigo, a derivação seguinte veria uma
        divergência que ela mesma criou e travaria o peso para sempre.
        """
        product = _product()
        recipe = _recipe()
        fill_unit_weight_from_recipe(product)

        recipe.items.all().update(quantity=Decimal("8.000"))
        recipe.save()  # mesma versão, massa diferente

        product.refresh_from_db()
        assert product.unit_weight_g == 267
        assert read_stamp(product, FACT_UNIT_WEIGHT)["value"] == 267
        assert weight_is_writable(product) is True

    def test_the_signal_does_not_touch_a_hand_typed_weight(self):
        product = _product(unit_weight_g=300)
        recipe = _recipe()
        recipe.save()

        product.refresh_from_db()
        assert product.unit_weight_g == 300

    def test_a_bundle_is_skipped(self):
        child = _product(sku="PAO-SIMPLES")
        bundle = _product(sku="COMBO")
        ProductComponent.objects.create(parent=bundle, component=child, qty=Decimal("1"))

        assert fill_unit_weight_from_recipe(bundle) is False
        bundle.refresh_from_db()
        assert bundle.unit_weight_g is None


class TestRefusals:
    def test_an_insumo_without_a_bridge_to_grams_refuses_to_derive(self):
        """Contagem sem peso unitário não vira peso menor; vira recusa."""
        recipe = _recipe()
        RecipeItem.objects.create(
            recipe=recipe, input_sku="OVO", quantity=Decimal("12"), unit="un",
            meta={"label": "Ovo"},
        )
        assert raw_unit_grams(recipe) is None
        assert derive_unit_weight(recipe) is None

    def test_a_counted_insumo_with_a_declared_unit_weight_does_derive(self):
        recipe = _recipe(sku="BRI")
        RecipeItem.objects.create(
            recipe=recipe, input_sku="OVO", quantity=Decimal("25"), unit="un",
            meta={"label": "Ovo", "unit_weight_g": "50"},
        )
        # 7000 g + 25 ovos × 50 g = 8250 g / 25 peças = 330 g crus.
        assert raw_unit_grams(recipe) == Decimal("330")

    def test_a_ficha_without_items_derives_nothing(self):
        recipe = Recipe.objects.create(
            ref="vazia", name="Vazia", output_sku="VAZ",
            batch_size=Decimal("10"), is_active=True,
        )
        assert derive_unit_weight(recipe) is None
