"""Read-side projection of temporary provider payment capabilities."""

from __future__ import annotations


def payment_constraints_payload() -> dict:
    """Expose canonical constraints without coupling surfaces to write services."""
    from shopman.shop.services.pix_policy import payment_constraints_payload as build_payload

    return build_payload()


__all__ = ["payment_constraints_payload"]
