"""Tests for WP-R19 — Error Paths in Checkout Views."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase


def _make_shop():
    from shopman.shop.models import Shop
    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channels():
    from shopman.shop.models import Channel
    Channel.objects.get_or_create(
        ref="web",
        defaults={
            "name": "Web",
            "is_active": True,
        },
    )
    Channel.objects.get_or_create(
        ref="pdv",
        defaults={
            "name": "Balcão",
            "is_active": True,
        },
    )


class PaymentMethodUnavailableTests(TestCase):
    """Payment method removed from channel config → clear error message."""

    def setUp(self):
        _make_shop()
        _make_channels()

    def test_payment_method_available_cash(self) -> None:
        """cash is available when channel returns only cash."""
        with patch("shopman.shop.projections.checkout_context.payment_methods", return_value=["cash"]) as mock:
            methods = mock("web")
            self.assertIn("cash", methods)
            self.assertNotIn("pix", methods)

    def test_payment_method_unavailable_returns_false(self) -> None:
        """pix not in channel methods → not available."""
        from unittest.mock import MagicMock

        from shopman.storefront.intents.checkout import _resolve_payment_method
        post = MagicMock()
        post.get.return_value = "pix"
        result = _resolve_payment_method(post, ["cash"])
        self.assertEqual(result, "cash")  # falls back to first available


class StockErrorCopyTests(TestCase):
    """Checkout stock errors should read naturally in singular and plural."""

    def test_limited_stock_uses_singular_unit_copy(self) -> None:
        from shopman.storefront.presentation.checkout import present_stock_errors

        errors = present_stock_errors([
            SimpleNamespace(
                line_id="line-1",
                sku="CROISSANT",
                name="Croissant",
                requested_qty=2,
                available_qty=1,
            ),
        ])

        self.assertEqual(errors[0]["message"], "Croissant: temos 1 unidade disponível agora.")

    def test_limited_stock_uses_plural_unit_copy(self) -> None:
        from shopman.storefront.presentation.checkout import present_stock_errors

        errors = present_stock_errors([
            SimpleNamespace(
                line_id="line-1",
                sku="PAO",
                name="Pão",
                requested_qty=4,
                available_qty=2,
            ),
        ])

        self.assertEqual(errors[0]["message"], "Pão: temos 2 unidades disponíveis agora.")
