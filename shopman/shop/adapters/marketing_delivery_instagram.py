"""Durable Instagram publication lane (Story by default, Feed only explicit)."""

from shopman.shop.adapters.marketing_delivery_meta import (
    instagram_available as is_available,
)
from shopman.shop.adapters.marketing_delivery_meta import (
    lookup_instagram as lookup,
)
from shopman.shop.adapters.marketing_delivery_meta import send_instagram as send

__all__ = ["is_available", "lookup", "send"]
