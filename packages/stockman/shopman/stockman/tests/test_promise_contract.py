"""Pure contract tests for Stockman's canonical promise decision."""

from datetime import date
from decimal import Decimal

from shopman.stockman.protocols.sku import PromiseReasonCode
from shopman.stockman.services.availability import decision_from_availability


def _info(**overrides):
    info = {
        "availability_policy": "planned_ok",
        "total_promisable": Decimal("7"),
        "available": Decimal("7"),
        "expected": Decimal("7"),
        "planned": Decimal("0"),
        "is_planned": False,
        "is_paused": False,
        "is_tracked": True,
        "positions": [],
    }
    info.update(overrides)
    return info


def test_tracked_supply_has_factual_quantity_and_finite_ceiling():
    decision = decision_from_availability(
        "SKU-1", Decimal("5"), _info(), target_date=date(2026, 10, 16)
    )

    assert decision.approved is True
    assert decision.available_qty == Decimal("7")
    assert decision.orderable_ceiling == Decimal("7")
    assert decision.is_tracked is True


def test_insufficient_supply_uses_closed_reason_vocabulary():
    decision = decision_from_availability("SKU-1", Decimal("8"), _info())

    assert decision.approved is False
    assert decision.reason_code is PromiseReasonCode.INSUFFICIENT_SUPPLY


def test_demand_policy_does_not_turn_requested_quantity_into_supply():
    decision = decision_from_availability(
        "SKU-1",
        Decimal("12"),
        _info(
            availability_policy="demand_ok",
            total_promisable=Decimal("2"),
            available=Decimal("2"),
            expected=Decimal("2"),
        ),
    )

    assert decision.approved is True
    assert decision.available_qty == Decimal("2")
    assert decision.orderable_ceiling is None


def test_untracked_sku_has_neither_factual_quantity_nor_policy_ceiling():
    decision = decision_from_availability(
        "SKU-1",
        Decimal("12"),
        _info(is_tracked=False, total_promisable=Decimal("0")),
    )

    assert decision.approved is True
    assert decision.available_qty is None
    assert decision.orderable_ceiling is None
    assert decision.is_tracked is False


def test_paused_tracked_sku_keeps_tracking_and_refuses_with_zero_ceiling():
    decision = decision_from_availability(
        "SKU-1",
        Decimal("1"),
        _info(is_paused=True, total_promisable=Decimal("0")),
    )

    assert decision.approved is False
    assert decision.reason_code is PromiseReasonCode.PAUSED
    assert decision.available_qty == Decimal("0")
    assert decision.orderable_ceiling == Decimal("0")
    assert decision.is_tracked is True
