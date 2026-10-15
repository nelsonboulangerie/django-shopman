"""Cheap, process-local route budgets for the request hot path.

The recorder deliberately performs one dictionary lookup and one deque append.
It never performs I/O and it does not acquire a global lock.  Alert delivery is
left to the logging stack (Sentry in the host application).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from shopman.watchman.contracts import CheckContext, CheckResult, Scope, Status
from shopman.watchman.exceptions import WatchmanConfigurationError


@dataclass(frozen=True, slots=True)
class RouteBudget:
    name: str
    method: str
    route: str
    max_duration_ms: float
    max_queries: int | None = None
    consecutive_failures: int = 3
    recovery_samples: int = 3
    max_alert_interval: int = 64
    heartbeat_samples: int = 1000


@dataclass(frozen=True, slots=True)
class BudgetEvent:
    kind: str
    budget: RouteBudget
    duration_ms: float
    query_count: int | None
    sample: int


@dataclass(slots=True)
class _BudgetState:
    durations: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    queries: deque[int] = field(default_factory=lambda: deque(maxlen=100))
    sample: int = 0
    failures: int = 0
    recoveries: int = 0
    alert_interval: int = 1
    next_alert: int = 0
    next_heartbeat: int = 1000
    incident_open: bool = False


class BudgetRecorder:
    """Record route observations and emit hysteretic incident transitions."""

    def __init__(self, budgets: tuple[RouteBudget, ...] = ()) -> None:
        self._budgets = {(budget.method, budget.route): budget for budget in budgets}
        self._states = {
            budget.name: _BudgetState(next_heartbeat=budget.heartbeat_samples) for budget in budgets
        }

    @classmethod
    def from_settings(cls) -> BudgetRecorder:
        raw = (getattr(settings, "WATCHMAN", {}) or {}).get("BUDGETS", {})
        if not isinstance(raw, dict):
            raise WatchmanConfigurationError("WATCHMAN['BUDGETS'] must be a mapping")
        try:
            default_heartbeat = int(
                (getattr(settings, "WATCHMAN", {}) or {}).get("BUDGET_HEARTBEAT_SAMPLES", 1000)
            )
        except (TypeError, ValueError) as exc:
            raise WatchmanConfigurationError("invalid Watchman budget heartbeat interval") from exc
        budgets: list[RouteBudget] = []
        for name, values in raw.items():
            if not isinstance(values, dict):
                raise WatchmanConfigurationError(f"Watchman budget {name!r} must be a mapping")
            try:
                budget = RouteBudget(
                    name=str(name),
                    method=str(values.get("method", "GET")).upper(),
                    route=str(values["route"]),
                    max_duration_ms=float(values["max_duration_ms"]),
                    max_queries=(int(values["max_queries"]) if values.get("max_queries") is not None else None),
                    consecutive_failures=int(values.get("consecutive_failures", 3)),
                    recovery_samples=int(values.get("recovery_samples", 3)),
                    max_alert_interval=int(values.get("max_alert_interval", 64)),
                    heartbeat_samples=int(values.get("heartbeat_samples", default_heartbeat)),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise WatchmanConfigurationError(f"invalid Watchman budget {name!r}") from exc
            if (
                budget.max_duration_ms <= 0
                or budget.consecutive_failures <= 0
                or budget.recovery_samples <= 0
                or budget.heartbeat_samples <= 0
            ):
                raise WatchmanConfigurationError(f"invalid Watchman budget {name!r}")
            budgets.append(budget)
        return cls(tuple(budgets))

    def record(
        self,
        *,
        method: str,
        route: str,
        duration_ms: float,
        query_count: int | None = None,
    ) -> BudgetEvent | None:
        budget = self._budgets.get((method, route))
        if budget is None:
            return None
        state = self._states[budget.name]
        state.sample += 1
        heartbeat_due = state.sample >= state.next_heartbeat
        if heartbeat_due:
            state.next_heartbeat = state.sample + budget.heartbeat_samples
        state.durations.append(duration_ms)
        if query_count is not None:
            state.queries.append(query_count)
        breached = duration_ms > budget.max_duration_ms or (
            budget.max_queries is not None and query_count is not None and query_count > budget.max_queries
        )
        if breached:
            state.failures += 1
            state.recoveries = 0
            if state.failures < budget.consecutive_failures:
                return None
            if not state.incident_open:
                state.incident_open = True
                state.alert_interval = 1
                state.next_alert = state.sample + state.alert_interval
                return BudgetEvent("opened", budget, duration_ms, query_count, state.sample)
            if state.sample >= state.next_alert:
                state.alert_interval = min(state.alert_interval * 2, budget.max_alert_interval)
                state.next_alert = state.sample + state.alert_interval
                return BudgetEvent("ongoing", budget, duration_ms, query_count, state.sample)
            return None

        state.failures = 0
        if not state.incident_open:
            return BudgetEvent("healthy", budget, duration_ms, query_count, state.sample) if heartbeat_due else None
        state.recoveries += 1
        if state.recoveries < budget.recovery_samples:
            return None
        state.incident_open = False
        state.recoveries = 0
        state.alert_interval = 1
        return BudgetEvent("resolved", budget, duration_ms, query_count, state.sample)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "samples": state.sample,
                "incident_open": state.incident_open,
                "last_duration_ms": state.durations[-1] if state.durations else None,
                "max_duration_ms": max(state.durations) if state.durations else None,
                "last_query_count": state.queries[-1] if state.queries else None,
                "max_query_count": max(state.queries) if state.queries else None,
            }
            for name, state in self._states.items()
        }


_recorder: BudgetRecorder | None = None


def get_recorder() -> BudgetRecorder:
    global _recorder
    if _recorder is None:
        _recorder = BudgetRecorder.from_settings()
    return _recorder


def reset_recorder() -> None:
    global _recorder
    _recorder = None


class PerformanceBudgetCheck:
    id = "performance_budgets"
    description = "Configured route budgets have no open local incident."
    scopes = frozenset({Scope.PERFORMANCE, Scope.DIAGNOSTIC})
    timeout_seconds = 0.05

    def run(self, context: CheckContext) -> CheckResult:
        snapshot = get_recorder().snapshot()
        open_incidents = sorted(name for name, state in snapshot.items() if state["incident_open"])
        observations = sum(state["samples"] for state in snapshot.values())
        status = Status.FAIL if open_incidents else Status.PASS
        return CheckResult(
            id=self.id,
            status=status,
            summary=(
                f"route budgets are within limits; {observations} observations"
                if not open_incidents
                else "route budget incident is open"
            ),
            evidence={"open": open_incidents, "observations": observations, "budgets": snapshot},
            remediation=("Inspect shopman.watchman.performance events." if open_incidents else None),
        )
