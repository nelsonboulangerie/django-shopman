from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from scripts.evaluate_continuum_shadow import evaluate


def _args(**overrides):
    values = {
        "minimum_samples": 3,
        "minimum_window_seconds": 60,
        "maximum_p95_shadow_ms": 25.0,
        "maximum_p95_shadow_queries": 2.0,
        "maximum_snapshot_bytes": 1_048_576,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _records():
    started = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    return [
        {
            "timestamp": (started + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z"),
            "shadow_ms": duration,
            "shadow_query_count": 1,
            "snapshot_bytes": 2048,
            "shadow_equal": True,
            "shadow_error": False,
            "cache_status": "hit:hit",
        }
        for offset, duration in ((0, 2.0), (30, 3.0), (60, 4.0))
    ]


def test_shadow_evaluator_passes_only_when_every_gate_passes():
    result = evaluate(_records(), _args())

    assert result["status"] == "pass"
    assert all(result["checks"].values())
    assert result["shadow_ms"] == {"p50": 3.0, "p75": 4.0, "p95": 4.0}


def test_shadow_evaluator_fails_closed_on_divergence_error_or_malformed_log():
    records = _records()
    records[0]["shadow_equal"] = False
    records[1]["shadow_error"] = True

    result = evaluate(records, _args(), malformed=1)

    assert result["status"] == "fail"
    assert result["checks"]["matching_logs_well_formed"] is False
    assert result["checks"]["zero_semantic_divergence"] is False
    assert result["checks"]["zero_shadow_errors"] is False


def test_shadow_evaluator_fails_closed_on_sample_window_performance_and_size():
    records = _records()[:2]
    records[-1].update(shadow_ms=26.0, shadow_query_count=3, snapshot_bytes=1_048_577)

    result = evaluate(records, _args())

    assert result["status"] == "fail"
    assert result["checks"] == {
        "matching_logs_well_formed": True,
        "minimum_samples": False,
        "minimum_window_seconds": False,
        "zero_semantic_divergence": True,
        "zero_shadow_errors": True,
        "p95_shadow_ms": False,
        "p95_shadow_queries": False,
        "snapshot_size": False,
    }
