#!/usr/bin/env python
"""Check the versioned Watchman detectors through Sentry's read-only API.

Authentication is intentionally environment-only.  The command never stores or
prints the token. Changes belong to the owner in Sentry's panel; this client has
no mutating method by construction.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "ops" / "watchman" / "sentry.json"


class SentryClient:
    def __init__(self, *, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def get(self, path: str):
        request = urllib.request.Request(
            self.base_url + path,
            method="GET",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Sentry base
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read(1000).decode(errors="replace")
            raise RuntimeError(f"Sentry API GET {path} returned {exc.code}: {detail}") from exc


def _index(items: list[dict]) -> dict[str, dict]:
    return {str(item.get("name", "")): item for item in items}


def _uptime_matches(found: dict, expected: dict, environment: str) -> bool:
    sources = found.get("dataSources") or []
    query = sources[0].get("queryObj", {}) if sources else {}
    config = found.get("config") or {}
    return (
        found.get("type") == "uptime_domain_failure"
        and found.get("enabled", found.get("status") == "active") is True
        and query.get("url", found.get("url")) == expected["url"]
        and query.get("method", found.get("method")) == "GET"
        and query.get("intervalSeconds", found.get("intervalSeconds")) == expected["interval_seconds"]
        and query.get("timeoutMs", found.get("timeoutMs")) == expected["timeout_ms"]
        and config.get("environment", found.get("environment")) == environment
        and config.get("downtimeThreshold", found.get("downtimeThreshold")) == expected["downtime_threshold"]
        and config.get("recoveryThreshold", found.get("recoveryThreshold")) == expected["recovery_threshold"]
    )


def _error_matches(found: dict, contract: dict) -> bool:
    expected = contract["error_rate"]
    sources = found.get("dataSources") or []
    query_obj = sources[0].get("queryObj", {}) if sources else {}
    query = query_obj.get("snubaQuery", query_obj)
    group = found.get("conditionGroup") or {}
    conditions = group.get("conditions") or []
    thresholds = {(item.get("type"), item.get("comparison"), item.get("conditionResult")) for item in conditions}
    return (
        found.get("type") == "metric_issue"
        and found.get("enabled") is True
        and query.get("aggregate") == expected["aggregate"]
        and query.get("dataset") == expected["dataset"]
        and query.get("environment") == contract["environment"]
        and query.get("query") == expected["query"]
        and query.get("timeWindow") == expected["time_window_seconds"]
        and ("gt", expected["open_above"], 75) in thresholds
        and ("lte", expected["resolve_at_or_below"], 0) in thresholds
    )


def _workflow_matches(found: dict, contract: dict, detector_ids: set[str]) -> bool:
    expected = contract["notification"]
    conditions = (found.get("triggers") or {}).get("conditions") or []
    condition_types = {item.get("type") for item in conditions}
    encoded = json.dumps(found, ensure_ascii=False).lower()
    return (
        found.get("name") == expected["name"]
        and found.get("enabled") is True
        and found.get("environment") == contract["environment"]
        and (found.get("config") or {}).get("frequency") == expected["frequency_minutes"]
        and {str(item) for item in found.get("detectorIds", [])} == detector_ids
        and expected["recipient"].lower() in encoded
        and (not expected["send_resolved"] or "issue_resolved_trigger" in condition_types)
    )


def reconcile(client: SentryClient, contract: dict) -> list[str]:
    org, project = contract["organization"], contract["project"]
    detectors = client.get(f"/api/0/organizations/{org}/detectors/?project={project}")
    existing = _index(detectors)
    changes: list[str] = []
    expected_detectors: list[dict] = []
    for uptime in contract["uptime"]:
        found = existing.get(uptime["name"])
        if found:
            expected_detectors.append(found)
        if not found:
            changes.append(f"missing uptime detector: {uptime['name']}")
        elif not _uptime_matches(found, uptime, contract["environment"]):
            changes.append(f"uptime detector has drift: {uptime['name']}")
    rate = contract["error_rate"]
    found_rate = existing.get(rate["name"])
    if not found_rate:
        changes.append(f"missing error-rate detector: {rate['name']}")
    elif not _error_matches(found_rate, contract):
        expected_detectors.append(found_rate)
        changes.append(f"error-rate detector has drift: {rate['name']}")
    else:
        expected_detectors.append(found_rate)

    workflows = client.get(f"/api/0/organizations/{org}/workflows/")
    expected_workflow = _index(workflows).get(contract["notification"]["name"])
    detector_ids = {str(item["id"]) for item in expected_detectors if item.get("id") is not None}
    if not expected_workflow:
        changes.append(f"missing notification workflow: {contract['notification']['name']}")
    elif len(detector_ids) != 3 or not _workflow_matches(expected_workflow, contract, detector_ids):
        changes.append(f"notification workflow has drift: {contract['notification']['name']}")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check",), default="check", nargs="?")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    token = os.environ.get("SENTRY_AUTH_TOKEN", "").strip()
    if not token:
        print(
            "SENTRY_AUTH_TOKEN ausente: o DSN envia eventos, mas a conferência requer alerts:read ou org:read",
            file=sys.stderr,
        )
        return 2
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    client = SentryClient(base_url=os.environ.get("SENTRY_API_BASE", "https://sentry.io"), token=token)
    changes = reconcile(client, contract)
    if changes:
        print(json.dumps({"status": "drift", "changes": changes}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
