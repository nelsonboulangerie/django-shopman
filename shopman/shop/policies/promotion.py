"""Pure promotion decisions shared by pricing consumers."""

from __future__ import annotations


def promotion_minimum_eligible(
    *,
    min_order_q: int,
    merchandise_subtotal_q: int,
) -> bool:
    """Return whether the merchandise subtotal reaches the promotion minimum.

    A zero minimum keeps the promotion open even for a defensive negative subtotal,
    matching the historical guard that only compared truthy minimums. Callers own the
    adaptation from models or session data to integer monetary quantities.
    """
    minimum_q = int(min_order_q or 0)
    subtotal_q = int(merchandise_subtotal_q or 0)
    return not minimum_q or subtotal_q >= minimum_q
