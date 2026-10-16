"""Stable contracts shared by runtime probes, commands and provider adapters."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class Status(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"


class Scope(StrEnum):
    LIVENESS = "liveness"
    READINESS = "readiness"
    DIAGNOSTIC = "diagnostic"
    SECURITY = "security"
    PERFORMANCE = "performance"


@dataclass(frozen=True, slots=True)
class CheckContext:
    profile: str
    deadline: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def remaining_seconds(self) -> float:
        """Return the caller's remaining budget for bounded downstream I/O."""

        return max(0.0, self.deadline - time.monotonic())


@dataclass(frozen=True, slots=True)
class CheckResult:
    id: str
    status: Status
    summary: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    remediation: str | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: float = 0.0

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("check result id must not be empty")
        if not isinstance(self.status, Status):
            object.__setattr__(self, "status", Status(self.status))
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.duration_ms < 0:
            raise ValueError("duration_ms must not be negative")
        try:
            json.dumps(dict(self.evidence))
        except (TypeError, ValueError) as exc:
            raise ValueError("evidence must be JSON-serializable") from exc

    def with_duration(self, duration_ms: float) -> CheckResult:
        return CheckResult(
            id=self.id,
            status=self.status,
            summary=self.summary,
            evidence=dict(self.evidence),
            remediation=self.remediation,
            observed_at=self.observed_at,
            duration_ms=max(0.0, duration_ms),
        )

    def to_dict(self, *, include_evidence: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "status": self.status.value,
            "summary": self.summary,
            "observed_at": self.observed_at.isoformat(),
            "duration_ms": round(self.duration_ms, 3),
        }
        if include_evidence:
            payload["evidence"] = dict(self.evidence)
            payload["remediation"] = self.remediation
        return payload


@runtime_checkable
class Check(Protocol):
    id: str
    description: str
    scopes: frozenset[Scope]
    timeout_seconds: float

    def run(self, context: CheckContext) -> CheckResult: ...
