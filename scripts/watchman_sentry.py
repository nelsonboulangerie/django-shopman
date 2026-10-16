#!/usr/bin/env python
"""Check the versioned Watchman detectors through Sentry's read-only API.

Authentication is intentionally environment-only. The command never stores or
prints the token. Changes belong to the owner in Sentry's panel; this client has
no mutating method by construction.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "ops" / "watchman" / "sentry.json"
MAX_PAGES = 100


class SentryClient:
    def __init__(self, *, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _get_page(self, path: str) -> tuple[object, str]:
        request = urllib.request.Request(
            self.base_url + path,
            method="GET",
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - configured Sentry base
                return json.load(response), response.headers.get("Link", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read(1000).decode(errors="replace")
            raise RuntimeError(f"Sentry API GET {path} returned {exc.code}: {detail}") from exc

    def get_all(self, path: str) -> list[dict]:
        """Read every page of a list endpoint, failing closed on ambiguous pagination."""
        separator = "&" if "?" in path else "?"
        current = f"{path}{separator}per_page=100"
        items: list[dict] = []
        visited: set[str] = set()
        for _ in range(MAX_PAGES):
            if current in visited:
                raise RuntimeError("Sentry API pagination cycle detected")
            visited.add(current)
            payload, link = self._get_page(current)
            if not isinstance(payload, list):
                raise RuntimeError(f"Sentry API GET {current} did not return a list")
            items.extend(payload)
            next_url = _next_page_url(link)
            if next_url is None:
                return items
            parsed = urllib.parse.urlsplit(next_url)
            if parsed.scheme and parsed.netloc:
                expected = urllib.parse.urlsplit(self.base_url)
                if (parsed.scheme, parsed.netloc) != (expected.scheme, expected.netloc):
                    raise RuntimeError("Sentry API pagination points outside configured API base")
                current = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))
            else:
                current = next_url
        raise RuntimeError(f"Sentry API pagination exceeded {MAX_PAGES} pages")


def _next_page_url(link: str) -> str | None:
    if not link:
        return None
    for entry in link.split(","):
        if not re.search(r'\brel="?next"?', entry):
            continue
        if re.search(r'\bresults="?false"?', entry):
            return None
        if re.search(r'\bresults="?true"?', entry):
            match = re.match(r"\s*<([^>]+)>", entry)
            if not match:
                raise RuntimeError("Sentry API returned an invalid next-page Link")
            return match.group(1)
        raise RuntimeError("Sentry API returned an ambiguous next-page Link")
    return None


def _duplicates(items: list[dict], expected_names: set[str]) -> set[str]:
    counts = Counter(str(item.get("name", "")) for item in items)
    return {name for name in expected_names if counts[name] > 1}


def _unique_by_name(items: list[dict], name: str) -> dict | None:
    matches = [item for item in items if item.get("name") == name]
    return matches[0] if len(matches) == 1 else None


def _uptime_matches(found: dict, expected: dict, environment: str) -> bool:
    sources = found.get("dataSources") or []
    query = sources[0].get("queryObj", {}) if len(sources) == 1 else {}
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
    query_obj = sources[0].get("queryObj", {}) if len(sources) == 1 else {}
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


def _active_email_targets(found: dict) -> set[tuple[str, str]]:
    targets: set[tuple[str, str]] = set()
    for action_filter in found.get("actionFilters") or []:
        if action_filter.get("conditions"):
            continue
        for action in action_filter.get("actions") or []:
            config = action.get("config") or {}
            target_type = config.get("targetType")
            target_identifier = config.get("targetIdentifier")
            if (
                action.get("type") == "email"
                and action.get("status") == "active"
                and target_type in {"user", "team"}
                and target_identifier not in (None, "")
            ):
                targets.add((str(target_type), str(target_identifier)))
    return targets


def _workflow_matches(found: dict, contract: dict, detector_ids: set[str]) -> bool:
    expected = contract["notification"]
    triggers = found.get("triggers") or {}
    conditions = triggers.get("conditions") or []
    condition_types = {
        item.get("type")
        for item in conditions
        if item.get("comparison") is True and item.get("conditionResult") is True
    }
    required_triggers = set(expected["trigger_types"])
    email = expected["email_action"]
    expected_target = (email.get("target_type"), str(email.get("target_identifier")))
    return (
        found.get("name") == expected["name"]
        and found.get("enabled") is True
        and found.get("environment") == contract["environment"]
        and (found.get("config") or {}).get("frequency") == expected["frequency_minutes"]
        and {str(item) for item in found.get("detectorIds", [])} == detector_ids
        and triggers.get("logicType") == "any-short"
        and required_triggers <= condition_types
        and "issue_resolved_trigger" in condition_types
        and any(item != "issue_resolved_trigger" for item in required_triggers)
        and expected_target in _active_email_targets(found)
    )


def _contract_errors(contract: dict) -> list[str]:
    detector_names = [item.get("name") for item in contract.get("uptime", [])]
    detector_names.append((contract.get("error_rate") or {}).get("name"))
    errors = [
        f"invalid contract: duplicate expected detector name: {name}"
        for name, count in Counter(detector_names).items()
        if name and count > 1
    ]
    notification = contract.get("notification") or {}
    email = notification.get("email_action") or {}
    target_type = email.get("target_type")
    target_identifier = email.get("target_identifier")
    if target_type not in {"user", "team"}:
        errors.append("invalid contract: notification email target_type must be user or team")
    if target_identifier in (None, ""):
        errors.append("invalid contract: notification email target_identifier is not declared")
    delivery = notification.get("delivery_assurance") or {}
    delivery_method = delivery.get("method")
    if delivery_method not in {"dedicated_sentry_member", "evidenced_email_routing"}:
        errors.append("invalid contract: unsupported notification delivery assurance method")
    if delivery_method == "dedicated_sentry_member" and target_type != "user":
        errors.append("invalid contract: dedicated Sentry member must use a user target")
    review_days = delivery.get("evidence_review_days")
    if (
        not delivery.get("intended_address")
        or not isinstance(review_days, int)
        or isinstance(review_days, bool)
        or review_days <= 0
    ):
        errors.append("invalid contract: notification delivery assurance is incomplete")
    triggers = notification.get("trigger_types") or []
    if "issue_resolved_trigger" not in triggers or not any(item != "issue_resolved_trigger" for item in triggers):
        errors.append("invalid contract: notification must declare opening and resolution triggers")
    return errors


def reconcile(client: SentryClient, contract: dict) -> list[str]:
    contract_errors = _contract_errors(contract)
    if contract_errors:
        return contract_errors

    org, project = contract["organization"], contract["project"]
    detectors = client.get_all(f"/api/0/organizations/{org}/detectors/?project={project}")
    expected_names = {item["name"] for item in contract["uptime"]} | {contract["error_rate"]["name"]}
    duplicate_detectors = _duplicates(detectors, expected_names)
    changes = [f"duplicate detector name: {name}" for name in sorted(duplicate_detectors)]
    expected_detectors: list[dict] = []
    for uptime in contract["uptime"]:
        found = _unique_by_name(detectors, uptime["name"])
        if found:
            expected_detectors.append(found)
        if uptime["name"] in duplicate_detectors:
            continue
        if not found:
            changes.append(f"missing uptime detector: {uptime['name']}")
        elif not _uptime_matches(found, uptime, contract["environment"]):
            changes.append(f"uptime detector has drift: {uptime['name']}")
    rate = contract["error_rate"]
    found_rate = _unique_by_name(detectors, rate["name"])
    if rate["name"] not in duplicate_detectors:
        if not found_rate:
            changes.append(f"missing error-rate detector: {rate['name']}")
        elif not _error_matches(found_rate, contract):
            expected_detectors.append(found_rate)
            changes.append(f"error-rate detector has drift: {rate['name']}")
        else:
            expected_detectors.append(found_rate)

    workflows = client.get_all(f"/api/0/organizations/{org}/workflows/")
    workflow_name = contract["notification"]["name"]
    duplicate_workflows = _duplicates(workflows, {workflow_name})
    expected_workflow = _unique_by_name(workflows, workflow_name)
    detector_ids = {str(item["id"]) for item in expected_detectors if item.get("id") is not None}
    if workflow_name in duplicate_workflows:
        changes.append(f"duplicate notification workflow name: {workflow_name}")
    elif not expected_workflow:
        changes.append(f"missing notification workflow: {workflow_name}")
    elif len(detector_ids) != len(expected_names) or not _workflow_matches(expected_workflow, contract, detector_ids):
        changes.append(f"notification workflow has drift: {workflow_name}")
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
