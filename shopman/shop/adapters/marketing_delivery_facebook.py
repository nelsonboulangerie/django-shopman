"""Durable Facebook Page publication lane."""

from shopman.shop.adapters.marketing_delivery_meta import (
    facebook_available as is_available,
)
from shopman.shop.adapters.marketing_delivery_meta import lookup_facebook as lookup
from shopman.shop.adapters.marketing_delivery_meta import send_facebook as send

__all__ = ["is_available", "lookup", "send"]
