"""Watchman adapters for the health checks owned by django-shopman.

This module is optional: the reusable package never imports it unless a project
registers these dotted paths in ``WATCHMAN``. Imports from ``shopman.shop`` stay
inside ``run()`` so installing Watchman in another Django project remains valid.
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
