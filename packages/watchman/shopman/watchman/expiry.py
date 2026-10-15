"""Lifecycle checks for credentials, certificates and other renewable resources.

The checker stores metadata about a resource, never the resource itself.  A host
declares where the deadline is published (normally an environment variable) and
what a human must do.  That keeps a token value out of logs while making its
lifecycle observable and actionable.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from django.conf import settings

from shopman.watchman.contracts import CheckContext, CheckResult, Scope, Status

DEFAULT_WARNING_DAYS = 60
DEFAULT_CRITICAL_DAYS = 14


@dataclass(frozen=True, slots=True)
class DeadlineAssessment:
    status: Status
    days_remaining: int
    milestone: str


def reached_milestone(
    deadline: date,
    *,
    today: date,
    milestones: Sequence[tuple[int, str]],
    expired: bool = False,
) -> tuple[str, str] | None:
    """Return the nearest reached milestone for an arbitrary host policy."""

    if expired or deadline < today:
        return ("expired", "critical")
    days_remaining = (deadline - today).days
    for days, severity in milestones:
        if days_remaining <= days:
            return (str(days), severity)
    return None


def assess_deadline(
    deadline: date,
    *,
    today: date | None = None,
    warning_days: int = DEFAULT_WARNING_DAYS,
    critical_days: int = DEFAULT_CRITICAL_DAYS,
) -> DeadlineAssessment:
    """Classify a renewable resource without doing I/O.

    Calendar days are deliberate: renewal instructions are acted on by people
    who think in dates.  A resource remains valid throughout its deadline date.
    """

    today = today or datetime.now(UTC).date()
    remaining = (deadline - today).days
    if remaining < 0:
        return DeadlineAssessment(Status.FAIL, remaining, "expired")
    if remaining <= critical_days:
        return DeadlineAssessment(Status.FAIL, remaining, f"d-{remaining}")
    if remaining <= warning_days:
        return DeadlineAssessment(Status.WARN, remaining, f"d-{remaining}")
    return DeadlineAssessment(Status.PASS, remaining, "healthy")


def _parse_deadline(value: str) -> date:
    raw = value.strip()
    if not raw:
        raise ValueError("empty deadline")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.date()


def _resource_payload(entry: Mapping[str, Any], *, today: date) -> tuple[dict[str, Any], Status]:
    resource_id = str(entry.get("id") or "").strip()
    label = str(entry.get("label") or resource_id).strip()
    env_name = str(entry.get("deadline_env") or entry.get("expires_at_env") or "").strip()
    if not resource_id or not env_name:
        raise ValueError("each renewable resource needs id and deadline_env")

    raw_deadline = os.environ.get(env_name, "").strip()
    common = {
        "id": resource_id,
        "label": label,
        "kind": str(entry.get("kind") or "credential"),
        "deadline_type": str(entry.get("deadline_type") or "expires"),
        "owner": str(entry.get("owner") or ""),
        "impact": str(entry.get("impact") or ""),
        "action": str(entry.get("action") or ""),
        "runbook": str(entry.get("runbook") or ""),
        "verification": str(entry.get("verification") or ""),
    }
    if not raw_deadline:
        return ({**common, "status": Status.UNKNOWN.value, "required_env": env_name}, Status.UNKNOWN)

    deadline = _parse_deadline(raw_deadline)
    assessment = assess_deadline(
        deadline,
        today=today,
        warning_days=int(entry.get("warning_days", DEFAULT_WARNING_DAYS)),
        critical_days=int(entry.get("critical_days", DEFAULT_CRITICAL_DAYS)),
    )
    return (
        {
            **common,
            "status": assessment.status.value,
            "deadline_on": deadline.isoformat(),
            "days_remaining": assessment.days_remaining,
            "milestone": assessment.milestone,
        },
        assessment.status,
    )


class ExpiryLifecycleCheck:
    """Evaluate the host's renewable-resource inventory from non-secret metadata."""

    id = "expiry_lifecycle"
    description = "Renewable credentials and certificates have actionable lifecycle metadata."
    scopes = frozenset({Scope.SECURITY, Scope.DIAGNOSTIC})
    timeout_seconds = 0.1

    def run(self, context: CheckContext) -> CheckResult:
        config = getattr(settings, "WATCHMAN", {}) or {}
        entries = config.get("EXPIRING_RESOURCES", ()) if isinstance(config, Mapping) else ()
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, bytearray)):
            return CheckResult(
                id=self.id,
                status=Status.FAIL,
                summary="renewable-resource inventory is invalid",
                remediation="Configure WATCHMAN['EXPIRING_RESOURCES'] as a sequence.",
            )

        today = datetime.now(UTC).date()
        resources: list[dict[str, Any]] = []
        statuses: list[Status] = []
        try:
            for entry in entries:
                if not isinstance(entry, Mapping):
                    raise ValueError("resource entry is not a mapping")
                payload, status = _resource_payload(entry, today=today)
                resources.append(payload)
                statuses.append(status)
        except (TypeError, ValueError) as exc:
            return CheckResult(
                id=self.id,
                status=Status.FAIL,
                summary="renewable-resource inventory is invalid",
                evidence={"error": exc.__class__.__name__},
                remediation="Repair the resource metadata; never put a secret value in this inventory.",
            )

        if not resources:
            return CheckResult(
                id=self.id,
                status=Status.UNKNOWN,
                summary="no renewable resources are inventoried",
                remediation="Inventory every credential or certificate that can stop a service when it expires.",
            )

        status = Status.PASS
        for candidate in (Status.FAIL, Status.UNKNOWN, Status.WARN):
            if candidate in statuses:
                status = candidate
                break
        attention = [item for item in resources if item["status"] != Status.PASS.value]
        summary = (
            f"{len(resources)} renewable resources healthy"
            if not attention
            else f"{len(attention)} of {len(resources)} renewable resources require action"
        )
        return CheckResult(
            id=self.id,
            status=status,
            summary=summary,
            evidence={"resources": resources, "attention_count": len(attention)},
            remediation=(
                "Follow each resource action and runbook, update its expiry metadata, then run the profile again."
                if attention
                else None
            ),
        )
