#!/usr/bin/env python3
"""Evaluate the production shadow window from privacy-safe JSON logs.

Usage:
    doctl apps logs APP_ID web --type run --no-prefix --tail 20000 \
      | python scripts/evaluate_continuum_shadow.py

The command fails closed: malformed matching observations, too few samples,
too short a window, any semantic divergence/error, or a performance/size
threshold violation returns a non-zero status.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from typing import Any


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _observations(lines) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    malformed = 0
    for raw in lines:
        raw = raw.strip()
        if not raw or "storefront_catalog_observation" not in raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if record.get("message") != "storefront_catalog_observation":
            continue
        if record.get("path") == "storefront_menu" and record.get("mode") == "shadow":
            records.append(record)
    return records, malformed


def evaluate(records: list[dict[str, Any]], args: argparse.Namespace, *, malformed: int = 0) -> dict[str, Any]:
    timestamps = [stamp for record in records if (stamp := _timestamp(record.get("timestamp")))]
    window_seconds = (
        max(0.0, (max(timestamps) - min(timestamps)).total_seconds())
        if len(timestamps) >= 2
        else 0.0
    )
    shadow_ms = [float(record.get("shadow_ms", 0.0)) for record in records]
    shadow_queries = [float(record.get("shadow_query_count", 0.0)) for record in records]
    snapshot_bytes = [int(record.get("snapshot_bytes", 0)) for record in records]
    divergences = sum(record.get("shadow_equal") is not True for record in records)
    errors = sum(record.get("shadow_error") is True for record in records)
    cache_statuses = Counter(str(record.get("cache_status", "missing")) for record in records)

    checks = {
        "matching_logs_well_formed": malformed == 0,
        "minimum_samples": len(records) >= args.minimum_samples,
        "minimum_window_seconds": window_seconds >= args.minimum_window_seconds,
        "zero_semantic_divergence": divergences == 0,
        "zero_shadow_errors": errors == 0,
        "p95_shadow_ms": _percentile(shadow_ms, 0.95) <= args.maximum_p95_shadow_ms,
        "p95_shadow_queries": _percentile(shadow_queries, 0.95) <= args.maximum_p95_shadow_queries,
        "snapshot_size": max(snapshot_bytes, default=0) <= args.maximum_snapshot_bytes,
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "samples": len(records),
        "window_seconds": round(window_seconds, 3),
        "malformed_matching_lines": malformed,
        "semantic_divergences": divergences,
        "shadow_errors": errors,
        "shadow_ms": {
            "p50": round(_percentile(shadow_ms, 0.50), 3),
            "p75": round(_percentile(shadow_ms, 0.75), 3),
            "p95": round(_percentile(shadow_ms, 0.95), 3),
        },
        "shadow_queries": {
            "p50": _percentile(shadow_queries, 0.50),
            "p75": _percentile(shadow_queries, 0.75),
            "p95": _percentile(shadow_queries, 0.95),
        },
        "snapshot_bytes": {
            "p50": _percentile([float(value) for value in snapshot_bytes], 0.50),
            "p75": _percentile([float(value) for value in snapshot_bytes], 0.75),
            "p95": _percentile([float(value) for value in snapshot_bytes], 0.95),
            "max": max(snapshot_bytes, default=0),
        },
        "cache_statuses": dict(sorted(cache_statuses.items())),
        "thresholds": {
            "minimum_samples": args.minimum_samples,
            "minimum_window_seconds": args.minimum_window_seconds,
            "maximum_p95_shadow_ms": args.maximum_p95_shadow_ms,
            "maximum_p95_shadow_queries": args.maximum_p95_shadow_queries,
            "maximum_snapshot_bytes": args.maximum_snapshot_bytes,
        },
        "checks": checks,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minimum-samples", type=int, default=500)
    parser.add_argument("--minimum-window-seconds", type=int, default=86_400)
    parser.add_argument("--maximum-p95-shadow-ms", type=float, default=25.0)
    parser.add_argument("--maximum-p95-shadow-queries", type=float, default=2.0)
    parser.add_argument("--maximum-snapshot-bytes", type=int, default=1_048_576)
    return parser


def main() -> int:
    args = _parser().parse_args()
    records, malformed = _observations(sys.stdin)
    result = evaluate(records, args, malformed=malformed)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
