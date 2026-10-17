"""A5: Stockman's promise refusal vocabulary is canonical end to end."""

from __future__ import annotations

from pathlib import Path

from shopman.stockman.protocols.sku import PromiseReasonCode


def test_insufficient_supply_is_the_only_active_python_spelling():
    repository = Path(__file__).resolve().parents[3]
    forbidden = "insufficient_" + "stock"
    offenders: list[str] = []

    for root_name in ("shopman", "packages", "config"):
        root = repository / root_name
        for path in root.rglob("*.py"):
            if forbidden in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(repository)))

    assert PromiseReasonCode.INSUFFICIENT_SUPPLY.value == "insufficient_supply"
    assert offenders == [], f"retired promise spelling remains in active Python: {offenders}"


def test_no_legacy_promise_translator_or_bilingual_reason_set():
    repository = Path(__file__).resolve().parents[3]

    assert not (repository / "shopman/shop/services/promise_refusal.py").exists()
    assert "STOCK_SHORTAGE_REASONS" not in (
        repository / "shopman/shop/services/external_availability.py"
    ).read_text(encoding="utf-8")


def test_retired_spelling_does_not_survive_in_active_ui_or_reference_docs():
    repository = Path(__file__).resolve().parents[3]
    forbidden = "insufficient_" + "stock"
    offenders: list[str] = []

    for path in (repository / "surfaces").rglob("*"):
        if (
            path.is_file()
            and "node_modules" not in path.parts
            and path.suffix in {".js", ".mjs", ".ts", ".vue"}
            and forbidden in path.read_text(
                encoding="utf-8"
            )
        ):
            offenders.append(str(path.relative_to(repository)))
    for path in (repository / "docs/reference").rglob("*.md"):
        if forbidden in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(repository)))

    assert offenders == [], f"retired promise spelling remains in an active surface: {offenders}"
