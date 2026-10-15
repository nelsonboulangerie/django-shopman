#!/usr/bin/env python
"""Run Watchman's read-only infrastructure profile for scheduled CI.

The runner preserves the complete JSON report as an artifact, fails on real
drift (including unavailable DigitalOcean evidence), and treats the explicitly
accepted absence of Sentry read access as a visible pending item.  It never
calls a mutating provider API.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

SENTRY_PENDING_ENV = "SENTRY_AUTH_TOKEN"


def classify_results(payload: dict) -> tuple[list[dict], list[dict]]:
    """Return ``(blocking, pending)`` without hiding an unexpected UNKNOWN."""

    blocking: list[dict] = []
    pending: list[dict] = []
    for result in payload.get("results", []):
        status = result.get("status")
        evidence = result.get("evidence") or {}
        is_expected_sentry_pending = (
            result.get("id") == "external_monitoring"
            and status == "unknown"
            and evidence.get("required_env") == SENTRY_PENDING_ENV
        )
        if is_expected_sentry_pending:
            pending.append(result)
        elif status in {"fail", "unknown"}:
            blocking.append(result)
    return blocking, pending


def notify_sentry(blocking: list[dict]) -> bool:
    """Send a sanitized escalation event when CI has a configured ingestion DSN."""

    if not os.environ.get("SENTRY_DSN", "").strip():
        return False
    import sentry_sdk

    ids = sorted(str(result.get("id", "unknown")) for result in blocking)
    with sentry_sdk.push_scope() as scope:
        scope.set_level("error")
        scope.set_tag("watchman.profile", "infrastructure")
        scope.set_tag("watchman.source", "scheduled_ci")
        scope.set_context("watchman", {"blocking_checks": ids})
        sentry_sdk.capture_message("Watchman infrastructure profile requires attention")
    sentry_sdk.flush(timeout=5)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("watchman-infrastructure.json"))
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from shopman.watchman.runner import run_profile

    payload = run_profile("infrastructure").to_dict()
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    blocking, pending = classify_results(payload)

    for result in pending:
        print(f"::warning title=Watchman pendente::{result['id']}: {result['summary']}")
    if not blocking:
        print(json.dumps({"status": "pass", "pending": [item["id"] for item in pending]}))
        return 0

    notified = notify_sentry(blocking)
    ids = [item["id"] for item in blocking]
    print(f"::error title=Watchman infrastructure::checks requerem atenção: {', '.join(ids)}")
    print(json.dumps({"status": "fail", "blocking": ids, "sentry_notified": notified}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
