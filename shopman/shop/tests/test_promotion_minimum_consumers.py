"""Pricing consumers delegate the promotion minimum to its canonical policy."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from shopman.shop import modifiers
from shopman.shop.adapters import pricing


def _promotion(*, kind: str, value: int = 10):
    return SimpleNamespace(
        type=kind,
        value=value,
        min_order_q=3_000,
        name="Promoção",
        ref="promotion-minimum-test",
        fulfillment_types=[],
        customer_segments=[],
        birthday_only=False,
    )


def test_catalog_pricing_delegates_the_minimum(monkeypatch):
    monkeypatch.setattr(pricing, "promotion_minimum_eligible", lambda **_kwargs: False)
    monkeypatch.setattr(modifiers.DiscountModifier, "_matches", lambda *_args: True)

    result = pricing.PromotionPricingBackend().get_price(
        sku="PAO",
        qty=Decimal("1"),
        listing="web",
        list_unit_price_q=1_000,
        list_line_total_q=1_000,
        context={"active_promotions": [_promotion(kind="percent")]},
    )

    assert result.final_line_total_q == 1_000
    assert result.adjustments == []


def test_order_discount_delegates_the_minimum(monkeypatch):
    monkeypatch.setattr(modifiers, "promotion_minimum_eligible", lambda **_kwargs: False)

    result = modifiers.DiscountModifier._best_fixed_discount(
        [_promotion(kind="fixed", value=500)],
        coupon_promo=None,
        coupon_code=None,
        session_total=3_000,
    )

    assert result is None


def test_free_delivery_delegates_the_minimum(monkeypatch):
    monkeypatch.setattr(modifiers, "promotion_minimum_eligible", lambda **_kwargs: False)

    assert not modifiers._free_delivery_covers_order(
        _promotion(kind="free_delivery"),
        customer_ref="",
        merchandise_q=3_000,
    )
