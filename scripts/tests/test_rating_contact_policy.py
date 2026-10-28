"""Ouvidoria: nota até 3 oferece o contato, uma vez por pedido."""

from __future__ import annotations

import pytest

from shopman.shop.policies import rating_contact


@pytest.mark.parametrize(
    ("rating", "already_requested", "expected"),
    [
        (1, False, True),
        (3, False, True),
        (4, False, False),
        (5, False, False),
        (2, True, False),
        (None, False, False),
        (0, False, False),
    ],
)
def test_rating_contact_truth_table(rating, already_requested, expected):
    assert rating_contact.can_request_contact(rating, already_requested=already_requested) is expected
