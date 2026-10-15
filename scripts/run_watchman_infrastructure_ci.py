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


def classify_results(payload: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Return ``(blocking, pending, warnings)`` using Watchman's real schema."""

    blocking: list[dict] = []
    pending: list[dict] = []
    warnings: list[dict] = []
    for result in payload.get("checks", []):
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
        elif status == "warn":
            warnings.append(result)
    return blocking, pending, warnings


def notify_sentry(attention: list[dict], *, blocking: bool) -> bool:
    """Send a sanitized escalation event when CI has a configured ingestion DSN."""

    if not os.environ.get("SENTRY_DSN", "").strip():
        return False
    import sentry_sdk

    ids = sorted(str(result.get("id", "unknown")) for result in attention)
    summaries = [
        {"id": str(result.get("id", "unknown")), "summary": str(result.get("summary", ""))[:300]}
        for result in attention
    ]
    renewable_actions: list[dict] = []
    for result in attention:
        if result.get("id") != "expiry_lifecycle":
            continue
        for resource in (result.get("evidence") or {}).get("resources", []):
            if resource.get("status") == "pass":
                continue
            renewable_actions.append({
                key: str(resource.get(key, ""))[:500]
                for key in (
                    "label",
                    "status",
                    "deadline_type",
                    "deadline_on",
                    "days_remaining",
                    "owner",
                    "impact",
                    "action",
                    "runbook",
                    "verification",
                )
            })
    with sentry_sdk.push_scope() as scope:
        scope.set_level("error" if blocking else "warning")
        scope.set_tag("watchman.profile", "infrastructure")
        scope.set_tag("watchman.source", "scheduled_ci")
        scope.set_context("watchman", {"checks": summaries, "renewable_actions": renewable_actions})
        sentry_sdk.capture_message(f"Watchman requires action: {', '.join(ids)}")
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
    blocking, pending, warnings = classify_results(payload)

    for result in pending:
        print(f"::warning title=Watchman pendente::{result['id']}: {result['summary']}")
    for result in warnings:
        print(f"::warning title=Watchman ação necessária::{result['id']}: {result['summary']}")
    if not blocking:
        notified = notify_sentry(warnings, blocking=False) if warnings else False
        print(json.dumps({
            "status": "pass",
            "pending": [item["id"] for item in pending],
            "warnings": [item["id"] for item in warnings],
            "sentry_notified": notified,
        }))
        return 0

    notified = notify_sentry([*blocking, *warnings], blocking=True)
    ids = [item["id"] for item in blocking]
    print(f"::error title=Watchman infrastructure::checks requerem atenção: {', '.join(ids)}")
    print(json.dumps({"status": "fail", "blocking": ids, "sentry_notified": notified}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
