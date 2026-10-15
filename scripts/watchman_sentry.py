#!/usr/bin/env python
"""Check or create the versioned Watchman detectors through Sentry's API.

Authentication is intentionally environment-only.  The command never stores or
prints the token.  Notification workflows are checked, not guessed: Sentry needs
the account-specific email action identifier for ``ti@boulangerie.com.br``.
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

    def request(self, method: str, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Sentry base
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read(1000).decode(errors="replace")
            raise RuntimeError(f"Sentry API {method} {path} returned {exc.code}: {detail}") from exc


def _index(items: list[dict]) -> dict[str, dict]:
    return {str(item.get("name", "")): item for item in items}


def _uptime_payload(item: dict, environment: str) -> dict:
    return {
        "name": item["name"],
        "url": item["url"],
        "method": "GET",
        "intervalSeconds": item["interval_seconds"],
        "timeoutMs": item["timeout_ms"],
        "downtimeThreshold": item["downtime_threshold"],
        "recoveryThreshold": item["recovery_threshold"],
        "environment": environment,
        "status": "active",
        "responseCaptureEnabled": False,
    }


def _error_payload(contract: dict) -> dict:
    item = contract["error_rate"]
    return {
        "name": item["name"],
        "type": "metric_issue",
        "dataSources": [
            {
                "aggregate": item["aggregate"],
                "dataset": item["dataset"],
                "environment": contract["environment"],
                "eventTypes": ["default", "error"],
                "query": item["query"],
                "queryType": 0,
                "timeWindow": item["time_window_seconds"],
            }
        ],
        "conditionGroup": {
            "logicType": "any",
            "conditions": [
                {"type": "gt", "comparison": item["open_above"], "conditionResult": 75},
                {"type": "lte", "comparison": item["resolve_at_or_below"], "conditionResult": 0},
            ],
            "actions": [],
        },
        "config": {"detectionType": "static"},
        "enabled": True,
    }


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


def reconcile(client: SentryClient, contract: dict, *, apply: bool) -> list[str]:
    org, project = contract["organization"], contract["project"]
    detectors = client.request("GET", f"/api/0/organizations/{org}/detectors/?project={project}")
    existing = _index(detectors)
    changes: list[str] = []
    for uptime in contract["uptime"]:
        found = existing.get(uptime["name"])
        if found and _uptime_matches(found, uptime, contract["environment"]):
            continue
        if found:
            changes.append(f"uptime detector has drift: {uptime['name']}")
        elif apply:
            client.request(
                "POST",
                f"/api/0/projects/{org}/{project}/uptime/",
                _uptime_payload(uptime, contract["environment"]),
            )
        else:
            changes.append(f"missing uptime detector: {uptime['name']}")
    rate = contract["error_rate"]
    found_rate = existing.get(rate["name"])
    if not found_rate:
        if apply:
            client.request(
                "POST",
                f"/api/0/organizations/{org}/projects/{project}/detectors/",
                _error_payload(contract),
            )
        else:
            changes.append(f"missing error-rate detector: {rate['name']}")
    elif not _error_matches(found_rate, contract):
        changes.append(f"error-rate detector has drift: {rate['name']}")

    workflows = client.request("GET", f"/api/0/organizations/{org}/workflows/")
    recipient = contract["notification"]["recipient"].lower()
    encoded = json.dumps(workflows).lower()
    if recipient not in encoded:
        changes.append(f"notification workflow does not target {recipient}")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "apply"), default="check", nargs="?")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    token = os.environ.get("SENTRY_AUTH_TOKEN", "").strip()
    if not token:
        print("SENTRY_AUTH_TOKEN ausente (requer alerts:read e, para apply, alerts:write)", file=sys.stderr)
        return 2
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    client = SentryClient(base_url=os.environ.get("SENTRY_API_BASE", "https://sentry.io"), token=token)
    changes = reconcile(client, contract, apply=args.action == "apply")
    if changes:
        print(json.dumps({"status": "drift", "changes": changes}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
