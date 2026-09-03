"""Unit tests for shopman.shop.projections.product_detail.

Reuses the storefront web fixtures (collection, listing, product, etc.)
from ``tests/web/conftest.py``. Mirrors the CatalogProjection tests: the
PDP builder shares the same listing + availability assumptions.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import ListingItem, Product

from shopman.shop.models import Promotion
from shopman.shop.projections.types import Availability
from shopman.storefront.presentation import build_product_detail
from shopman.storefront.presentation.product_detail import (
    AllergenInfoProjection,
    ConservationInfoProjection,
    ProductDetailProjection,
)

pytestmark = pytest.mark.django_db


DEFAULT_LOW_STOCK_THRESHOLD = Decimal("5")


def _seed_stock(sku: str, qty: Decimal) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={
            "name": "Loja Principal",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    stock.receive(
        quantity=qty,
        sku=sku,
        position=position,
        target_date=date.today(),
        reason="pdp projection test seed",
    )


def _publish_on_listing(listing, product: Product, price_q: int | None = None) -> None:
    ListingItem.objects.get_or_create(
        listing=listing,
        product=product,
        defaults={
            "price_q": price_q if price_q is not None else product.base_price_q,
            "is_published": True,
            "is_sellable": True,
        },
    )


# ──────────────────────────────────────────────────────────────────────
# Basic shape
# ──────────────────────────────────────────────────────────────────────


class TestBuildProductDetailShape:
    def test_returns_none_for_unknown_sku(self):
        assert build_product_detail(sku="does-not-exist", channel_ref="web") is None

    def test_returns_none_for_unpublished_product(self, product_unpublished):
        assert build_product_detail(sku=product_unpublished.sku, channel_ref="web") is None

    def test_basic_shape(self, listing, collection, collection_item, product):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert isinstance(proj, ProductDetailProjection)
        assert proj.sku == product.sku
        assert proj.slug == product.sku
        assert proj.name == "Pão Francês"
        assert proj.base_price_q == 80
        assert proj.price_display == "R$ 0,80"
        assert proj.has_promotion is False
        assert proj.original_price_display is None
        assert proj.promotion_label is None
        assert proj.max_qty == 99
        assert proj.is_bundle is False
        assert proj.components == ()

    def test_projection_is_immutable(self, listing, collection, collection_item, product):
        from dataclasses import FrozenInstanceError

        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        with pytest.raises(FrozenInstanceError):
            proj.name = "x"  # type: ignore[misc]

    def test_listing_price_wins_over_base(self, listing, product, listing_item):
        # listing_item fixture seeds price_q=90
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.base_price_q == 90
        assert proj.price_display == "R$ 0,90"

    def test_breadcrumb_category_is_first_collection(
        self, listing, collection, collection_item, product,
    ):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.breadcrumb_category is not None
        assert proj.breadcrumb_category.ref == "paes"
        assert proj.breadcrumb_category.name == "Pães"
        assert proj.breadcrumb_category.icon
        assert proj.breadcrumb_category.url == "/menu#paes"

    def test_pdp_exposes_primary_collection_color_and_icon(
        self, listing, collection, product,
    ):
        """Cor + ícone da coleção PRIMÁRIA vestem o hero-fallback da PDP sem foto."""
        from shopman.offerman.models import CollectionItem

        collection.metadata = {"color": "#B49B7F", "icon": "wheat"}
        collection.save()
        CollectionItem.objects.create(
            collection=collection, product=product, sort_order=1, is_primary=True,
        )
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.category_color == "#B49B7F"
        assert proj.category_icon == "wheat"

    def test_pdp_without_primary_collection_has_no_category_dressing(
        self, listing, collection, collection_item, product,
    ):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.category_color is None
        assert proj.category_icon is None


# ──────────────────────────────────────────────────────────────────────
# Availability
# ──────────────────────────────────────────────────────────────────────


class TestAvailability:
    def test_available_when_stock_seeded(self, listing, product):
        _publish_on_listing(listing, product)
        _seed_stock(product.sku, Decimal("50"))
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.availability is Availability.AVAILABLE
        assert proj.availability_label == "Disponível"
        assert proj.can_add_to_cart is True
        assert proj.available_qty == 50

    def test_low_stock_under_threshold(self, listing, product):
        _publish_on_listing(listing, product)
        _seed_stock(product.sku, DEFAULT_LOW_STOCK_THRESHOLD - Decimal("1"))
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.availability is Availability.LOW_STOCK
        assert proj.can_add_to_cart is True

    def test_channel_paused_renders_the_page_as_unavailable(self, listing, product):
        """Pausar não é ocultar: o item continua na vitrine e continua tendo PDP.

        Enquanto o portão do canal exigia ``is_sellable``, o card do cardápio
        (que mostra o pausado como "Indisponível", de propósito) linkava para uma
        PDP que devolvia 404 no toque.
        """
        ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=product.base_price_q,
            is_published=True,
            is_sellable=False,
        )
        _seed_stock(product.sku, Decimal("50"))

        proj = build_product_detail(sku=product.sku, channel_ref="web")

        assert proj is not None, "pausado no canal não pode virar 404"
        assert proj.availability is Availability.UNAVAILABLE
        assert proj.can_add_to_cart is False
        assert proj.is_paused is True
        # Pausa é decisão do operador — nem aqui vira promessa de volta.
        assert proj.is_notifiable is False

    def test_hidden_in_channel_is_a_404(self, listing, product):
        """Ocultar (o antigo "despublicar") É o eixo do sumiço."""
        ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=product.base_price_q,
            is_published=False,
            is_sellable=True,
        )

        assert build_product_detail(sku=product.sku, channel_ref="web") is None

    def test_absent_from_the_channel_is_a_404(self, listing, product):
        """Sem linha no listing, o produto nunca foi para esta vitrine."""
        assert build_product_detail(sku=product.sku, channel_ref="web") is None

    def test_unsellable_product_is_unavailable(self, listing, product_unavailable):
        _publish_on_listing(listing, product_unavailable)
        proj = build_product_detail(
            sku=product_unavailable.sku, channel_ref="web",
        )
        assert proj is not None
        assert proj.availability is Availability.UNAVAILABLE
        assert proj.can_add_to_cart is False

    def test_demand_ok_has_no_stepper_ceiling(self, listing, product):
        """``demand_ok`` promete pela demanda, não pela prateleira: teto é None.

        Lendo ``total_promisable`` cru, a PDP projetava ``available_qty: 0`` num
        item "Disponível" e adicionável — e o "+" morria no primeiro toque com
        "Só temos 0 disponíveis". O card já guardava contra isso; a PDP não.
        """
        from unittest.mock import patch

        _publish_on_listing(listing, product)
        raw = {"availability_policy": "demand_ok", "total_promisable": Decimal("0")}
        with patch(
            "shopman.storefront.presentation.product_detail._availability",
            return_value=raw,
        ):
            proj = build_product_detail(sku=product.sku, channel_ref="web")

        assert proj is not None
        assert proj.availability is Availability.AVAILABLE
        assert proj.can_add_to_cart is True
        assert proj.available_qty is None

    def test_planned_batch_has_no_stepper_ceiling(self, listing, product):
        """Encomenda: sem prateleira, com lote. Teto 0 travaria o "+" na 1ª unidade."""
        from unittest.mock import patch

        _publish_on_listing(listing, product)
        raw = {
            "availability_policy": "planned_ok",
            "total_promisable": Decimal("0"),
            "is_planned": True,
        }
        with patch(
            "shopman.storefront.presentation.product_detail._availability",
            return_value=raw,
        ):
            proj = build_product_detail(sku=product.sku, channel_ref="web")

        assert proj is not None
        assert proj.availability is Availability.PLANNED_OK
        assert proj.can_add_to_cart is True
        assert proj.available_qty is None


# ──────────────────────────────────────────────────────────────────────
# Promotions
# ──────────────────────────────────────────────────────────────────────


class TestPromotions:
    def test_active_auto_promotion_reflected(
        self, listing, collection, collection_item, product,
    ):
        _publish_on_listing(listing, product)
        now = timezone.now()
        Promotion.objects.create(
            ref="testao-20-off",
            name="Testão 20% OFF",
            type="percent",
            value=20,
            skus=[product.sku],
            is_active=True,
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(hours=1),
        )
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.has_promotion is True
        assert proj.original_price_display == "R$ 0,80"
        assert proj.base_price_q == 64  # 80 - 20%
        assert proj.price_display == "R$ 0,64"
        assert proj.promotion_label


# ──────────────────────────────────────────────────────────────────────
# Allergens / Conservation
# ──────────────────────────────────────────────────────────────────────


class TestCartAnnotation:
    """``qty_in_cart`` should mirror the visitor's open cart for the PDP SKU."""

    def test_qty_in_cart_zero_without_request(self, listing, product):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.qty_in_cart == 0

    def test_qty_in_cart_reflects_cart_session(
        self, listing, collection, collection_item, cart_session, product,
    ):
        from django.test import RequestFactory

        rf = RequestFactory()
        request = rf.get(f"/produto/{product.sku}/")
        request.session = cart_session.session  # type: ignore[attr-defined]

        proj = build_product_detail(
            sku=product.sku, channel_ref="web", request=request,
        )
        assert proj is not None
        assert proj.qty_in_cart == 2


class TestAllergenAndConservation:
    def test_allergen_panel_populated_from_metadata(self, listing, product):
        product.metadata = {
            "allergens": ["glúten", "leite"],
            "dietary_info": ["vegetariano"],
            "serves": "2",
        }
        product.save()
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert isinstance(proj.allergen, AllergenInfoProjection)
        assert proj.allergen.allergens == ("glúten", "leite")
        assert proj.allergen.dietary_info == ("vegetariano",)
        assert proj.allergen.serves == "2"
        assert proj.allergen.has_any is True

    def test_gallery_populated_from_metadata(self, listing, product):
        product.metadata = {
            "gallery": [
                "https://menu.example/img/products/ct2.webp",
                "",
                42,
            ],
        }
        product.save()
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        # Vazios caem; valores não-string são coagidos (a projection não julga).
        assert proj.gallery == ("https://menu.example/img/products/ct2.webp", "42")

    def test_gallery_empty_when_metadata_absent_or_malformed(self, listing, product):
        product.metadata = {"gallery": "not-a-list"}
        product.save()
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.gallery == ()

    def test_purchase_measurements_from_metadata(self, listing, product):
        product.unit_weight_g = 400
        product.metadata = {
            "serves": "2 a 4 pessoas",
            "approx_dimensions": "aprox. 24 x 12 x 10 cm",
        }
        product.save()
        _publish_on_listing(listing, product)

        proj = build_product_detail(sku=product.sku, channel_ref="web")

        assert proj is not None
        assert proj.unit_weight_label == "~400g a unidade"
        assert proj.approx_dimensions_label == "aprox. 24 x 12 x 10 cm"
        assert proj.allergen is not None
        assert proj.allergen.serves == "2 a 4 pessoas"

    def test_allergen_is_none_when_metadata_empty(self, listing, product):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.allergen is None

    def test_conservation_panel_same_day(self, listing, product):
        product.shelf_life_days = 0
        product.storage_tip = "Consumir fresco."
        product.unit_weight_g = 150
        product.save()
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert isinstance(proj.conservation, ConservationInfoProjection)
        assert proj.conservation.shelf_life_label == "Melhor consumido no mesmo dia"
        assert proj.conservation.storage_tip == "Consumir fresco."
        assert proj.unit_weight_label == "~150g a unidade"

    def test_conservation_plural_days(self, listing, product):
        product.shelf_life_days = 3
        product.save()
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.conservation is not None
        assert proj.conservation.shelf_life_label == "Conserva bem por 3 dias"

    def test_conservation_none_when_empty(self, listing, product):
        _publish_on_listing(listing, product)
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.conservation is None


class TestCrossSell:
    """"Você também pode gostar" — lateral discovery via shared keywords,
    rendered with the canonical catalog card (one card shape)."""

    def test_cross_sell_surfaces_keyword_relatives(self, listing, product, croissant):
        _publish_on_listing(listing, product)
        _publish_on_listing(listing, croissant)
        product.keywords.add("fermentação natural")
        croissant.keywords.add("fermentação natural")

        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        cross_sell_skus = {item.sku for item in proj.cross_sell}
        assert croissant.sku in cross_sell_skus
        assert product.sku not in cross_sell_skus  # never recommends itself
        # Título via registro omotenashi (PRODUCT_CROSS_SELL_HEADING) — o
        # operador reescreve no Admin sem tocar na tela.
        assert proj.cross_sell_heading == "Você também pode gostar"

    def test_cross_sell_empty_without_shared_keywords(self, listing, product, croissant):
        _publish_on_listing(listing, product)
        _publish_on_listing(listing, croissant)
        # No keywords → nothing to relate on.
        proj = build_product_detail(sku=product.sku, channel_ref="web")
        assert proj is not None
        assert proj.cross_sell == ()
