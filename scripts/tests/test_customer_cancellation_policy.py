"""Régua do cliente que quer cancelar (dono, 06/11/2026): antes do preparo cancela,
pago ou não; depois, não cancela e fala com o responsável."""

from __future__ import annotations

import pytest

from shopman.shop.policies import customer_cancellation


@pytest.mark.parametrize(
    ("status", "payment_status", "expected"),
    [
        ("new", "pending", True),
        ("accepted", "captured", True),
        ("accepted", "authorized", True),
        ("new", "", True),
        ("accepted", "unknown", False),
        ("preparing", "captured", False),
        ("ready", "pending", False),
        ("dispatched", "captured", False),
        ("cancelled", "refunded", False),
    ],
)
def test_customer_self_cancel_truth_table(status, payment_status, expected):
    assert customer_cancellation.can_self_cancel(status, payment_status=payment_status) is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("new", False),
        ("accepted", False),
        ("preparing", True),
        ("ready", True),
        ("dispatched", True),
        ("delivered", False),
        ("completed", False),
        ("cancelled", False),
    ],
)
def test_contact_replaces_cancel_after_preparation(status, expected):
    assert customer_cancellation.offers_contact_instead(status) is expected
