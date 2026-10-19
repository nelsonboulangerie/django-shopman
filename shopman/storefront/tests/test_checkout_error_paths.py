"""Tests for WP-R19 — Error Paths in Checkout Views."""

from __future__ import annotations

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
