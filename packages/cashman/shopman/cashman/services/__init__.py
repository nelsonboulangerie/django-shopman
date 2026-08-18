"""Services do Cashman: os únicos escritores do turno e do livro.

    from shopman.cashman import services as cash

    shift = cash.open_shift(operator=user, float_q=10000)
    cash.record("cash_out", shift=shift, operator=user, amount_q=-5000, approved_by=manager, reason="Cofre")
    cash.close_shift(shift, counted_q=4990, actor=user)
    cash.difference(shift)   # -10
"""

from shopman.cashman.services.ledger import (
    balance,
    change_requests,
    counted,
    difference,
    expected_before_count,
    record,
    timeline,
)
from shopman.cashman.services.shifts import (
    close_shift,
    correct_count,
    is_closed,
    open_shift,
    open_shift_for,
    open_shift_for_terminal,
)

__all__ = [
    "balance",
    "change_requests",
    "close_shift",
    "correct_count",
    "counted",
    "difference",
    "expected_before_count",
    "is_closed",
    "open_shift",
    "open_shift_for",
    "open_shift_for_terminal",
    "record",
    "timeline",
]
