"""Bundle availability = min() dos componentes (o mais escasso limita).

Regressão do audit pré-staging: o card de um bundle (ex.: COMBO-PETIT-DEJ)
mostrava "Disponível" mesmo com um componente esgotado, porque o bundle não tem
quant próprio — o raw vinha ``None`` e resolvia para AVAILABLE. Agora a
disponibilidade do bundle é derivada dos componentes: o menos disponível manda.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.offerman.models import ListingItem, Product, ProductComponent

from shopman.shop.projections.types import Availability
from shopman.storefront.presentation import build_catalog

pytestmark = pytest.mark.django_db


def _seed_stock(sku: str, qty: Decimal) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(quantity=qty, sku=sku, position=position, target_date=date.today(), reason="bundle test")


def _publish(listing, product: Product) -> None:
    ListingItem.objects.get_or_create(
        listing=listing,
        product=product,
        defaults={"price_q": product.base_price_q, "is_published": True, "is_sellable": True},
    )


def _bundle_item(listing):
    """COMBO com dois componentes; o combo publicado no cardápio, componentes só como insumos."""
    combo = Product.objects.create(
        sku="COMBO-PETIT-DEJ", name="Combo Petit Déjeuner", base_price_q=1500,
        is_published=True, is_sellable=True,
    )
    pao = Product.objects.create(sku="PAO-COMBO", name="Pão", base_price_q=500, is_published=True, is_sellable=True)
    cafe = Product.objects.create(sku="CAFE-COMBO", name="Café", base_price_q=600, is_published=True, is_sellable=True)
    ProductComponent.objects.create(parent=combo, component=pao, qty=Decimal("1"))
    ProductComponent.objects.create(parent=combo, component=cafe, qty=Decimal("1"))
    _publish(listing, combo)
    return combo, pao, cafe


def _combo_projection(channel_ref: str = "web"):
    catalog = build_catalog(channel_ref=channel_ref)
    for item in catalog.items:
        if item.sku == "COMBO-PETIT-DEJ":
            return item
    return None


def test_bundle_unavailable_when_a_tracked_component_is_sold_out(listing):
    from shopman.stockman import stock
    from shopman.stockman.models import Quant

    _bundle_item(listing)
    _seed_stock("PAO-COMBO", Decimal("50"))
    _seed_stock("CAFE-COMBO", Decimal("1"))
    stock.adjust(Quant.objects.get(sku="CAFE-COMBO"), 0, reason="sold out")
    item = _combo_projection()
    assert item is not None
    assert item.availability == Availability.UNAVAILABLE
    assert item.can_add_to_cart is False


def test_bundle_available_when_all_components_have_stock(listing):
    _bundle_item(listing)
    _seed_stock("PAO-COMBO", Decimal("50"))
    _seed_stock("CAFE-COMBO", Decimal("50"))
    item = _combo_projection()
    assert item is not None
    assert item.availability == Availability.AVAILABLE
    assert item.can_add_to_cart is True


def test_untracked_component_does_not_hide_tracked_bundle_limit():
    from shopman.shop.projections.catalog_context import bundle_availability_from_components

    raw = bundle_availability_from_components([
        (
            Decimal("1"),
            {
                "is_tracked": False,
                "total_promisable": Decimal("0"),
                "available": Decimal("0"),
            },
        ),
        (
            Decimal("2"),
            {
                "is_tracked": True,
                "total_promisable": Decimal("8"),
                "available": Decimal("8"),
                "ready_physical": Decimal("8"),
            },
        ),
    ])

    assert raw is not None
    assert raw["total_promisable"] == Decimal("4")


def test_bundle_capped_by_scarcest_component(listing):
    _bundle_item(listing)
    _seed_stock("PAO-COMBO", Decimal("50"))
    _seed_stock("CAFE-COMBO", Decimal("3"))  # só 3 combos possíveis
    item = _combo_projection()
    assert item is not None
    # 3 combos <= low-stock threshold (default 5) → LOW_STOCK, ainda vendável.
    assert item.availability == Availability.LOW_STOCK
    assert item.can_add_to_cart is True
    assert item.available_qty == 3
