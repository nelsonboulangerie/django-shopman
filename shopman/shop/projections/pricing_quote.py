"""Stable read-side representation of Offerman's contextual price quote."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from shopman.offerman.protocols import ContextualPrice


@dataclass(frozen=True)
class PriceAdjustmentProjection:
    code: str
    label: str
    amount_q: int
    badge_label: str | None


@dataclass(frozen=True)
class PriceQuoteProjection:
    qty: Decimal
    listing_ref: str | None
    list_unit_price_q: int
    list_line_total_q: int
    final_unit_price_q: int
    final_line_total_q: int
    adjustments: tuple[PriceAdjustmentProjection, ...]


def project_price_quote(price: ContextualPrice) -> PriceQuoteProjection:
    """Copy the complete quote without exposing backend-only metadata."""
    return PriceQuoteProjection(
        qty=price.qty,
        listing_ref=price.listing,
        list_unit_price_q=price.list_unit_price_q,
        list_line_total_q=price.list_line_total_q,
        final_unit_price_q=price.final_unit_price_q,
        final_line_total_q=price.final_line_total_q,
        adjustments=tuple(
            PriceAdjustmentProjection(
                code=adjustment.code,
                label=adjustment.label,
                amount_q=adjustment.amount_q,
                badge_label=(
                    str(adjustment.metadata["badge_label"]) if adjustment.metadata.get("badge_label") else None
                ),
            )
            for adjustment in price.adjustments
        ),
    )
