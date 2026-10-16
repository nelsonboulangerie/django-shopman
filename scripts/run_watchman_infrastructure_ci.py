#!/usr/bin/env python
"""Run Watchman's read-only infrastructure profile for scheduled CI.

The runner preserves the complete JSON report as an artifact and fails closed
on drift, unavailable provider evidence, or an incomplete/malformed report. It
never calls a mutating provider API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

EXPECTED_CHECK_IDS = frozenset({
    "production_contract",
    "deployment_drift",
    "external_monitoring",
    "expiry_lifecycle",
})
VALID_STATUSES = frozenset({"pass", "warn", "fail", "unknown", "skipped"})


def _contract_failure(errors: list[str]) -> dict:
    return {
        "id": "watchman_report_contract",
        "status": "fail",
        "summary": "Watchman returned an incomplete or malformed infrastructure report",
        "evidence": {"errors": errors},
    }


def _is_non_negative_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def _is_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def classify_results(payload: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Return ``(blocking, pending, warnings)`` using Watchman's real schema."""

    blocking: list[dict] = []
    pending: list[dict] = []
    warnings: list[dict] = []
    if not isinstance(payload, dict):
        blocking.append(_contract_failure(["report must be an object"]))
        return blocking, pending, warnings

    checks = payload.get("checks")
    contract_errors: list[str] = []
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        contract_errors.append("schema_version must be 1")
    if payload.get("profile") != "infrastructure":
        contract_errors.append("profile must be infrastructure")
    if not isinstance(payload.get("status"), str) or payload["status"] not in VALID_STATUSES:
        contract_errors.append("status is invalid")
    if not _is_timestamp(payload.get("started_at")):
        contract_errors.append("started_at must be a timezone-aware ISO timestamp")
    if not _is_non_negative_number(payload.get("duration_ms")):
        contract_errors.append("duration_ms must be a non-negative number")
    if not isinstance(checks, list) or not checks:
        contract_errors.append("checks must be a non-empty list")
        blocking.append(_contract_failure(contract_errors))
        return blocking, pending, warnings

    seen_ids: list[str] = []
    for index, result in enumerate(checks):
        if not isinstance(result, dict):
            contract_errors.append(f"checks[{index}] must be an object")
            continue
        check_id = result.get("id")
        if not isinstance(check_id, str) or not check_id.strip():
            contract_errors.append(f"checks[{index}].id must be a non-empty string")
        else:
            seen_ids.append(check_id)
        status = result.get("status")
        if not isinstance(status, str) or status not in VALID_STATUSES:
            contract_errors.append(f"checks[{index}].status is invalid")
        if not isinstance(result.get("summary"), str) or not result["summary"].strip():
            contract_errors.append(f"checks[{index}].summary must be a non-empty string")
        if not isinstance(result.get("evidence"), dict):
            contract_errors.append(f"checks[{index}].evidence must be an object")
        if not _is_timestamp(result.get("observed_at")):
            contract_errors.append(f"checks[{index}].observed_at must be a timezone-aware ISO timestamp")
        if not _is_non_negative_number(result.get("duration_ms")):
            contract_errors.append(f"checks[{index}].duration_ms must be a non-negative number")
        if result.get("remediation") is not None and not isinstance(result.get("remediation"), str):
            contract_errors.append(f"checks[{index}].remediation must be a string or null")

    duplicate_ids = sorted({check_id for check_id in seen_ids if seen_ids.count(check_id) > 1})
    actual_ids = set(seen_ids)
    missing_ids = sorted(EXPECTED_CHECK_IDS - actual_ids)
    unexpected_ids = sorted(actual_ids - EXPECTED_CHECK_IDS)
    if duplicate_ids:
        contract_errors.append(f"duplicate check ids: {', '.join(duplicate_ids)}")
    if missing_ids:
        contract_errors.append(f"missing check ids: {', '.join(missing_ids)}")
    if unexpected_ids:
        contract_errors.append(f"unexpected check ids: {', '.join(unexpected_ids)}")
    valid_check_statuses = [result.get("status") for result in checks if isinstance(result, dict)]
    expected_report_status = next(
        (status for status in ("fail", "unknown", "warn", "pass") if status in valid_check_statuses),
        "skipped",
    )
    if payload.get("status") != expected_report_status:
        contract_errors.append(
            f"report status {payload.get('status')!r} does not match checks ({expected_report_status!r})"
        )
    if contract_errors:
        blocking.append(_contract_failure(contract_errors))
        return blocking, pending, warnings

    for result in checks:
        status = result.get("status")
        if status in {"fail", "unknown", "skipped"}:
            blocking.append(result)
        elif status == "warn":
            warnings.append(result)
    return blocking, pending, warnings


def capture_sentry_event(attention: list[dict], *, blocking: bool) -> bool:
    """Capture sanitized evidence when a DSN exists; never claim delivery."""

    if not os.environ.get("SENTRY_DSN", "").strip():
        return False
    try:
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
            event_id = sentry_sdk.capture_message(f"Watchman requires action: {', '.join(ids)}")
        sentry_sdk.flush(timeout=5)
        return bool(event_id)
    except Exception as exc:  # noqa: BLE001 - escalation failure must not hide the report
        print(f"::warning title=Watchman Sentry::event capture failed: {exc.__class__.__name__}", file=sys.stderr)
        return False


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
        captured = capture_sentry_event(warnings, blocking=False) if warnings else False
        print(json.dumps({
            "status": "pass",
            "pending": [item["id"] for item in pending],
            "warnings": [item["id"] for item in warnings],
            "sentry_event_captured": captured,
        }))
        return 0

    captured = capture_sentry_event([*blocking, *warnings], blocking=bool(blocking))
    ids = [item["id"] for item in blocking]
    warning_ids = [item["id"] for item in warnings]
    attention_ids = [*ids, *warning_ids]
    print(f"::error title=Watchman infrastructure::checks requerem atenção: {', '.join(attention_ids)}")
    print(json.dumps({
        "status": "fail",
        "blocking": ids,
        "warnings": warning_ids,
        "sentry_event_captured": captured,
    }))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
