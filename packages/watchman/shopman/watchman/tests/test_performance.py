from __future__ import annotations

import time

import pytest

from shopman.watchman.performance import BudgetRecorder, RouteBudget


def _budget(**overrides):
    values = {
        "name": "catalog",
        "method": "GET",
        "route": "/catalog/",
        "max_duration_ms": 100,
        "max_queries": 10,
        "consecutive_failures": 3,
        "recovery_samples": 2,
    }
    values.update(overrides)
    return RouteBudget(**values)


def test_budget_uses_hysteresis_backoff_and_resolution():
    recorder = BudgetRecorder((_budget(),))

    assert recorder.record(method="GET", route="/catalog/", duration_ms=101, query_count=1) is None
    assert recorder.record(method="GET", route="/catalog/", duration_ms=101, query_count=1) is None
    opened = recorder.record(method="GET", route="/catalog/", duration_ms=101, query_count=1)
    ongoing = recorder.record(method="GET", route="/catalog/", duration_ms=101, query_count=1)
    assert opened and opened.kind == "opened"
    assert ongoing and ongoing.kind == "ongoing"

    assert recorder.record(method="GET", route="/catalog/", duration_ms=10, query_count=1) is None
    resolved = recorder.record(method="GET", route="/catalog/", duration_ms=10, query_count=1)
    assert resolved and resolved.kind == "resolved"
    assert recorder.snapshot()["catalog"]["incident_open"] is False


def test_query_budget_is_only_applied_when_measurement_exists():
    recorder = BudgetRecorder((_budget(consecutive_failures=1),))

    assert recorder.record(method="GET", route="/catalog/", duration_ms=10, query_count=None) is None
    event = recorder.record(method="GET", route="/catalog/", duration_ms=10, query_count=11)

    assert event and event.kind == "opened"


def test_unconfigured_route_is_constant_time_noop():
    recorder = BudgetRecorder((_budget(),))
    started = time.perf_counter()
    for _ in range(20_000):
        assert recorder.record(method="GET", route="/other/", duration_ms=10) is None
    average_ms = (time.perf_counter() - started) * 1000 / 20_000

    assert average_ms < 0.5


def test_invalid_budget_configuration_fails_closed(settings):
    settings.WATCHMAN = {"BUDGETS": {"broken": {"route": "/x/"}}}

    with pytest.raises(Exception, match="invalid Watchman budget"):
        BudgetRecorder.from_settings()
