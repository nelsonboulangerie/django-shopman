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
        versioned = os.environ.get("WATCHMAN_VERSIONED_DO_SPEC", ".do/app.alpha-subdomains.yaml")
        return _run(
            self.id,
            [sys.executable, "scripts/check_do_spec_drift.py", "--spec", versioned, "--live-spec", live_spec],
            40.0,
        )


class ExternalMonitoringContractCheck:
    id = "external_monitoring"
    description = "Versioned Sentry uptime and rate-alert contract is valid."
    scopes = frozenset({Scope.SECURITY, Scope.DIAGNOSTIC})
    timeout_seconds = 2.0

    def run(self, context: CheckContext) -> CheckResult:
        path = ROOT / "ops" / "watchman" / "sentry.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            endpoints = payload["uptime"]
            rate = payload["error_rate"]
            recipient = payload["notification"]["recipient"]
            valid = (
                isinstance(endpoints, list)
                and len(endpoints) >= 2
                and all(item["url"].startswith("https://") and item["interval_seconds"] == 60 for item in endpoints)
                and rate["aggregate"] == "count()"
                and recipient == "ti@boulangerie.com.br"
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return CheckResult(
                id=self.id,
                status=Status.FAIL,
                summary="external monitoring contract is invalid",
                evidence={"error": exc.__class__.__name__},
                remediation="Repair ops/watchman/sentry.json.",
            )
        return CheckResult(
            id=self.id,
            status=Status.PASS if valid else Status.FAIL,
            summary="external monitoring contract is versioned" if valid else "external monitoring contract is incomplete",
            evidence={"uptime_monitors": len(endpoints), "recipient": recipient},
            remediation=None if valid else "Declare both services, one-minute cadence, rate alert and ti@ recipient.",
        )
