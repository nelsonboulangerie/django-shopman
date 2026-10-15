"""Shopman-specific infrastructure checks for Watchman's CLI-only profile."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from shopman.watchman.contracts import CheckContext, CheckResult, Scope, Status

ROOT = Path(settings.BASE_DIR)


def _run(check_id: str, command: list[str], timeout: float) -> CheckResult:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            id=check_id,
            status=Status.UNKNOWN,
            summary="infrastructure command exceeded its deadline",
            remediation="Run the command directly and inspect the slow dependency.",
        )
    output = (result.stdout or result.stderr or "").strip()
    evidence = {"exit_code": result.returncode, "output_tail": output[-2000:]}
    return CheckResult(
        id=check_id,
        status=Status.PASS if result.returncode == 0 else Status.FAIL,
        summary="infrastructure contract passed" if result.returncode == 0 else "infrastructure contract failed",
        evidence=evidence,
        remediation="Run the reported command from the repository root." if result.returncode else None,
    )


class ProductionContractCheck:
    id = "production_contract"
    description = "Hermetic production configuration and dangerous fallbacks pass."
    scopes = frozenset({Scope.SECURITY, Scope.DIAGNOSTIC})
    timeout_seconds = 180.0

    def run(self, context: CheckContext) -> CheckResult:
        return _run(self.id, [sys.executable, "scripts/check_production_contract.py"], 170.0)


class DeploymentDriftCheck:
    id = "deployment_drift"
    description = "The versioned DigitalOcean spec matches a supplied live spec."
    scopes = frozenset({Scope.SECURITY, Scope.DIAGNOSTIC})
    timeout_seconds = 45.0

    def run(self, context: CheckContext) -> CheckResult:
        live_spec = os.environ.get("WATCHMAN_LIVE_DO_SPEC", "").strip()
        if not live_spec:
            return CheckResult(
                id=self.id,
                status=Status.SKIPPED,
                summary="live DigitalOcean spec was not supplied",
                evidence={"required_env": "WATCHMAN_LIVE_DO_SPEC"},
                remediation="Download the live spec read-only and rerun with WATCHMAN_LIVE_DO_SPEC.",
            )
        versioned = os.environ.get("WATCHMAN_VERSIONED_DO_SPEC", ".do/app.subdomains.yaml")
        return _run(
            self.id,
            [sys.executable, "scripts/check_do_spec_drift.py", "--spec", versioned, "--live-spec", live_spec],
            40.0,
        )


class ExternalMonitoringContractCheck:
    id = "external_monitoring"
    description = "Versioned Sentry monitoring contract matches the live account."
    scopes = frozenset({Scope.SECURITY, Scope.DIAGNOSTIC})
    timeout_seconds = 30.0

    def run(self, context: CheckContext) -> CheckResult:
        path = ROOT / "ops" / "watchman" / "sentry.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            endpoints = payload["uptime"]
            rate = payload["error_rate"]
            recipient = payload["notification"]["recipient"]
            notification = payload["notification"]
            valid = (
                payload["schema_version"] == 1
                and bool(payload["organization"])
                and bool(payload["project"])
                and payload["environment"] == "production"
                and isinstance(endpoints, list)
                and len(endpoints) == 2
                and len({item["url"] for item in endpoints}) == 2
                and all(
                    item["url"].startswith("https://")
                    and item["interval_seconds"] == 60
                    and item["timeout_ms"] > 0
                    and item["downtime_threshold"] > 0
                    and item["recovery_threshold"] > 0
                    for item in endpoints
                )
                and rate["aggregate"] == "count()"
                and rate["time_window_seconds"] == 300
                and rate["open_above"] > rate["resolve_at_or_below"] >= 0
                and recipient == "ti@boulangerie.com.br"
                and notification["repeat_minutes"] == [0, 5, 10, 30, 60, 180]
                and notification["send_resolved"] is True
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return CheckResult(
                id=self.id,
                status=Status.FAIL,
                summary="external monitoring contract is invalid",
                evidence={"error": exc.__class__.__name__},
                remediation="Repair ops/watchman/sentry.json.",
            )
        if not valid:
            return CheckResult(
                id=self.id,
                status=Status.FAIL,
                summary="external monitoring contract is incomplete",
                evidence={"uptime_monitors": len(endpoints), "recipient": recipient},
                remediation="Declare both services, cadence, rate alert, repetition, recovery and ti@ recipient.",
            )
        if not os.environ.get("SENTRY_AUTH_TOKEN", "").strip():
            return CheckResult(
                id=self.id,
                status=Status.SKIPPED,
                summary="contract is valid; live Sentry drift was not checked",
                evidence={
                    "uptime_monitors": len(endpoints),
                    "recipient": recipient,
                    "required_env": "SENTRY_AUTH_TOKEN",
                },
                remediation="Provide a read-only SENTRY_AUTH_TOKEN and rerun the infrastructure profile.",
            )
        return _run(self.id, [sys.executable, "scripts/watchman_sentry.py", "check"], 25.0)
