"""Synchronous, deterministic runner for bounded Watchman checks."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shopman.watchman.contracts import CheckContext, CheckResult, Status
from shopman.watchman.registry import Registry, build_registry

logger = logging.getLogger(__name__)

@dataclass(frozen=True, slots=True)
class Report:
    profile: str
    results: tuple[CheckResult, ...]
    started_at: datetime
    duration_ms: float

    @property
    def status(self) -> Status:
        if not self.results:
            return Status.UNKNOWN
        statuses = {result.status for result in self.results}
        for status in (Status.FAIL, Status.UNKNOWN, Status.WARN, Status.PASS):
            if status in statuses:
                return status
        return Status.SKIPPED

    @property
    def probe_failed(self) -> bool:
        """Only an explicit check failure may make a public probe return 503."""

        return any(result.status is Status.FAIL for result in self.results)

    @property
    def exit_code(self) -> int:
        return 1 if any(result.status in {Status.FAIL, Status.UNKNOWN} for result in self.results) else 0

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "profile": self.profile,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "duration_ms": round(self.duration_ms, 3),
            "checks": [result.to_dict(include_evidence=include_evidence) for result in self.results],
        }


def run_profile(
    profile: str,
    *,
    registry: Registry | None = None,
    metadata: dict[str, Any] | None = None,
) -> Report:
    registry = registry or build_registry()
    checks = registry.for_profile(profile)
    report_started = datetime.now(UTC)
    report_clock = time.monotonic()
    results = tuple(_run_check(check, profile=profile, metadata=metadata or {}) for check in checks)
    return Report(
        profile=profile,
        results=results,
        started_at=report_started,
        duration_ms=(time.monotonic() - report_clock) * 1000,
    )


def _run_check(check, *, profile: str, metadata: dict[str, Any]) -> CheckResult:
    started = time.monotonic()
    timeout_seconds = float(check.timeout_seconds)
    context = CheckContext(
        profile=profile,
        deadline=started + timeout_seconds,
        metadata=metadata,
    )
    try:
        result = check.run(context)
        if not isinstance(result, CheckResult):
            raise TypeError("check did not return CheckResult")
        if result.id != check.id:
            raise ValueError(f"check returned id {result.id!r}, expected {check.id!r}")
    except Exception as exc:  # noqa: BLE001 - one broken observer never breaks the observed request
        logger.exception("watchman_check_error check=%s", check.id)
        result = CheckResult(
            id=check.id,
            status=Status.UNKNOWN,
            summary=f"check raised {exc.__class__.__name__}",
            remediation="Inspect the protected Watchman log for this check.",
        )
    duration_ms = (time.monotonic() - started) * 1000
    if duration_ms > timeout_seconds * 1000 and result.status not in {Status.FAIL, Status.UNKNOWN}:
        result = CheckResult(
            id=check.id,
            status=Status.UNKNOWN,
            summary="check exceeded its declared deadline",
            evidence={"timeout_ms": round(timeout_seconds * 1000, 3)},
            remediation="Make the check's own I/O deadline shorter than its Watchman timeout.",
        )
    return result.with_duration(duration_ms)
