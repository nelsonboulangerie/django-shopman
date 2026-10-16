"""Stockman remains the single owner of operational promise decisions."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_orchestrator_has_no_duplicate_promise_implementation_or_sentinel():
    adapter_source = (ROOT / "shopman" / "shop" / "adapters" / "stock.py").read_text()
    service_source = (ROOT / "shopman" / "shop" / "services" / "availability.py").read_text()

    assert "def promise_decision_from_availability" not in adapter_source
    assert 'Decimal("999999")' not in service_source
    assert "effective_available_qty" not in service_source


def test_orchestrator_delegates_loaded_reading_to_stockman():
    service_source = (ROOT / "shopman" / "shop" / "services" / "availability.py").read_text()

    assert "from shopman.stockman.services.availability import decision_from_availability" in service_source
    assert "decision = decision_from_availability(" in service_source


def test_untracked_hold_marker_has_one_canonical_shape():
    from shopman.shop.services.stock import untracked_hold_entry

    assert untracked_hold_entry("NO-LEDGER") == {
        "sku": "NO-LEDGER",
        "hold_id": None,
        "qty": 0,
        "is_tracked": False,
    }


def test_untracked_hold_reader_rejects_historical_shapes():
    from shopman.shop.services.stock import is_untracked_hold_entry

    assert is_untracked_hold_entry({"is_tracked": False}) is True
    assert is_untracked_hold_entry({"is_tracked": True}) is False
    assert is_untracked_hold_entry({"untracked": True}) is False
    assert is_untracked_hold_entry({"source": "stock.untracked"}) is False
    assert is_untracked_hold_entry({"is_tracked": True, "untracked": True}) is False


def test_cached_availability_accepts_only_canonical_tracking_flag():
    from shopman.shop.services.stock import _is_untracked

    assert _is_untracked("NO-LEDGER", {"NO-LEDGER": {"is_tracked": False}}, None) is True
    assert _is_untracked("NO-LEDGER", {"NO-LEDGER": {"untracked": True}}, None) is False
    assert _is_untracked(
        "NO-LEDGER",
        {"NO-LEDGER": {"source": "stock.untracked"}},
        None,
    ) is False


def test_stock_runtime_contains_no_historical_untracked_contract():
    service_source = (ROOT / "shopman" / "shop" / "services" / "stock.py").read_text()

    assert '"untracked": True' not in service_source
    assert '.get("untracked")' not in service_source
    assert '"stock.untracked"' not in service_source
