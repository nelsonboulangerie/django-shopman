"""Host-side Watchman adapters for django-shopman health primitives.

The reusable ``shopman.watchman`` kernel must not import the product host. These
adapters therefore live beside the checks they expose and implement Watchman's
small public protocol without creating a dependency in the opposite direction.
"""

from __future__ import annotations

from collections.abc import Callable

from shopman.watchman.contracts import CheckContext, CheckResult, Scope, Status

LegacyCheck = Callable[[], tuple[str, str | None]]


def _result(check_id: str, outcome: tuple[str, str | None], *, healthy: str, remediation: str) -> CheckResult:
    legacy_status, reason = outcome
    statuses = {
        "ok": Status.PASS,
        "fail": Status.FAIL,
        "skipped": Status.SKIPPED,
    }
    status = statuses.get(legacy_status, Status.UNKNOWN)
    summary = healthy if status is Status.PASS else f"{check_id} is {status.value}"
    return CheckResult(
        id=check_id,
        status=status,
        summary=summary,
        evidence={"reason": reason} if reason else {},
        remediation=remediation if status in {Status.FAIL, Status.UNKNOWN} else None,
    )


class PoolCheck:
    id = "pool"
    description = "The process pool is not stuck while PostgreSQL is reachable directly."
    scopes = frozenset({Scope.LIVENESS, Scope.DIAGNOSTIC})
    timeout_seconds = 4.0

    def run(self, context: CheckContext) -> CheckResult:
        from shopman.shop import pool_liveness

        return _result(
            self.id,
            pool_liveness.check_pool(),
            healthy="process pool is available",
            remediation="Restart this process if the database remains reachable outside its pool.",
        )


class DatabaseCheck:
    id = "database"
    description = "This process can round-trip through its Django database connection."
    scopes = frozenset({Scope.READINESS, Scope.DIAGNOSTIC})
    timeout_seconds = 12.0

    def run(self, context: CheckContext) -> CheckResult:
        from shopman.shop.views.health import _check_database

        return _result(
            self.id,
            _check_database(),
            healthy="database round-trip succeeded",
            remediation="Inspect PostgreSQL reachability and this process connection pool.",
        )


class CacheCheck:
    id = "cache"
    description = "Shared cache and session storage complete a write/read/delete round-trip."
    scopes = frozenset({Scope.READINESS, Scope.DIAGNOSTIC})
    timeout_seconds = 6.0

    def run(self, context: CheckContext) -> CheckResult:
        from shopman.shop.views.health import _check_cache

        return _result(
            self.id,
            _check_cache(),
            healthy="cache round-trip succeeded",
            remediation="Inspect the shared Redis cache configured for this process.",
        )


class MigrationsCheck:
    id = "migrations"
    description = "The deployed Django migration graph is applied."
    scopes = frozenset({Scope.READINESS, Scope.DIAGNOSTIC})
    timeout_seconds = 12.0

    def run(self, context: CheckContext) -> CheckResult:
        from shopman.shop.views.health import _check_migrations

        return _result(
            self.id,
            _check_migrations(),
            healthy="migration graph is current",
            remediation="Run the release migration step before routing traffic.",
        )


class QueueCheck:
    id = "queue"
    description = "Required workers are alive and durable work is not stale."
    scopes = frozenset({Scope.READINESS, Scope.DIAGNOSTIC})
    timeout_seconds = 6.0

    def run(self, context: CheckContext) -> CheckResult:
        from shopman.shop.views.health import _check_queue

        return _result(
            self.id,
            _check_queue(),
            healthy="workers and durable queue are current",
            remediation="Inspect worker heartbeats and the oldest queued directives.",
        )


class IfoodPollingCheck:
    id = "ifood_polling"
    description = "The iFood order poller answered within the last 2 minutes."
    scopes = frozenset({Scope.DIAGNOSTIC})
    timeout_seconds = 2.0

    def run(self, context: CheckContext) -> CheckResult:
        from shopman.shop.services import ifood_poll_health as health

        state = health.current()
        limit = int(health.STALE_AFTER.total_seconds())
        if state.state == health.DISABLED:
            return CheckResult(
                id=self.id,
                status=Status.SKIPPED,
                summary="iFood direct integration is not configured",
            )
        if state.state == health.UNKNOWN:
            return CheckResult(
                id=self.id,
                status=Status.UNKNOWN,
                summary="process-local cache cannot see the poller heartbeat",
            )
        if state.state == health.FRESH:
            return CheckResult(
                id=self.id,
                status=Status.PASS,
                summary="iFood poller is answering",
                evidence={"age_seconds": state.age_seconds, "limit_seconds": limit},
            )
        evidence = {"limit_seconds": limit}
        if state.state == health.STALE:
            evidence["age_seconds"] = state.age_seconds
            evidence["last_success"] = state.last_success.isoformat()
            summary = f"no successful iFood poll for {state.age_seconds}s"
        else:
            summary = "no successful iFood poll was ever recorded"
        return CheckResult(
            id=self.id,
            status=Status.FAIL,
            summary=summary,
            evidence=evidence,
            remediation=(
                "Inspect the ifood-poll-worker component (ifood_poll --watch) and iFood OAuth; "
                "iFood cancels orders not accepted within 8 minutes."
            ),
        )
