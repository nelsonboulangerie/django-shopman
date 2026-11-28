"""The promotion minimum is a pure policy with one canonical truth table."""

from __future__ import annotations

import pytest

from shopman.shop.policies.promotion import promotion_minimum_eligible


@pytest.mark.parametrize(
    ("min_order_q", "merchandise_subtotal_q", "expected"),
    [
        (0, 0, True),
        (3_000, 2_999, False),
        (3_000, 3_000, True),
        (3_000, 3_001, True),
    ],
)
def test_promotion_minimum_truth_table(
    min_order_q: int,
    merchandise_subtotal_q: int,
    expected: bool,
) -> None:
    assert (
        promotion_minimum_eligible(
            min_order_q=min_order_q,
            merchandise_subtotal_q=merchandise_subtotal_q,
        )
        is expected
    )
