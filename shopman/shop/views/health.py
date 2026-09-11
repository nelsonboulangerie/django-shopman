"""Public liveness and readiness probes with deliberately small disclosures.

``/health/live/`` proves only that the Django process can serve a request. It
must remain healthy when a dependency is unavailable, otherwise an orchestrator
can turn a database incident into a restart loop.

``/health/ready/`` checks the local dependency chain used by the operator BFF:
database, shared cache/session storage, migrations and the durable queue. It
never calls a provider. Public responses contain only ``ok``, ``fail`` or
``skipped``; diagnostic reasons remain in protected logs.

The old ``/health/`` and ``/ready/`` routes remain compatibility aliases while
deployment probes move to the explicit paths.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

_LOCMEM_BACKEND = "django.core.cache.backends.locmem.LocMemCache"
_PROBE_RATE_LIMIT = 600
_PROBE_RATE_WINDOW_SECONDS = 60
_PROBE_RATE_MAX_CLIENTS = 2048
_QUEUE_STALE_SECONDS = 30


@dataclass(slots=True)
class _RateBucket:
    opened_at: float
    count: int


class ProbeRateLimiter:
    """Bounded process-local limiter that never depends on Redis to stay alive."""

    def __init__(
        self,
        *,
        limit: int = _PROBE_RATE_LIMIT,
        window_seconds: int = _PROBE_RATE_WINDOW_SECONDS,
        max_clients: int = _PROBE_RATE_MAX_CLIENTS,
        clock=time.monotonic,
    ) -> None:
        self.limit = max(1, int(limit))
        self.window_seconds = max(1, int(window_seconds))
        self.max_clients = max(1, int(max_clients))
        self.clock = clock
        self._buckets: OrderedDict[str, _RateBucket] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, client_key: str) -> bool:
        now = self.clock()
        with self._lock:
            bucket = self._buckets.get(client_key)
            if bucket is None or now - bucket.opened_at >= self.window_seconds:
                if bucket is None and len(self._buckets) >= self.max_clients:
                    self._buckets.popitem(last=False)
                self._buckets[client_key] = _RateBucket(opened_at=now, count=1)
                return True
            bucket.count += 1
            self._buckets.move_to_end(client_key)
            return bucket.count <= self.limit


_probe_rate_limiter = ProbeRateLimiter()


def _check_database() -> tuple[str, str | None]:
    try:
        conn = connections[DEFAULT_DB_ALIAS]
        conn.ensure_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 — a probe must never raise
        logger.debug("readiness database check failed", exc_info=True)
        return "fail", exc.__class__.__name__
    return "ok", None


def _check_cache() -> tuple[str, str | None]:
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if backend == _LOCMEM_BACKEND:
        return "skipped", None
    key = f"health:{uuid.uuid4().hex}"
    try:
        cache.set(key, "1", timeout=5)
        value = cache.get(key)
        cache.delete(key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("readiness cache check failed", exc_info=True)
        return "fail", exc.__class__.__name__
    if value != "1":
        return "fail", "roundtrip_mismatch"
    return "ok", None


def _check_migrations() -> tuple[str, str | None]:
    try:
        executor = MigrationExecutor(connections[DEFAULT_DB_ALIAS])
        targets = executor.loader.graph.leaf_nodes()
        pending = len(executor.migration_plan(targets))
    except Exception as exc:  # noqa: BLE001
        logger.debug("readiness migration check failed", exc_info=True)
        return "fail", exc.__class__.__name__
    if pending:
        return "fail", "pending_migrations"
    return "ok", None


def _check_queue() -> tuple[str, str | None]:
    """Check durable queue freshness without invoking an outbound adapter."""

    from shopman.orderman import worker_heartbeat
    from shopman.orderman.models import Directive

    from shopman.shop.models import MarketingOutbox

    now = timezone.now()
    cutoff = now - timedelta(seconds=_QUEUE_STALE_SECONDS)
    try:
        directive_stale = Directive.objects.filter(
            status="queued",
            available_at__lte=cutoff,
        ).exists()
        outbox_stale = MarketingOutbox.objects.filter(
            state=MarketingOutbox.State.PENDING,
            available_at__lte=cutoff,
        ).exists()
        if not directive_stale and not outbox_stale:
            return "ok", None
        last_beat = worker_heartbeat.last_beat(
            worker_heartbeat.PROCESS_DIRECTIVES_WORKER
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("readiness queue check failed", exc_info=True)
        return "fail", exc.__class__.__name__

    stale_minutes = int(
        getattr(settings, "SHOPMAN_WORKER_HEARTBEAT_STALE_MINUTES", 15)
    )
    if last_beat is None:
        return "fail", "worker_unknown_with_backlog"
    if now - last_beat > timedelta(minutes=max(1, stale_minutes)):
        return "fail", "worker_stale"
    return "fail", "queue_lag"


def _client_key(request) -> str:
    # REMOTE_ADDR is controlled by the server/proxy boundary. Never trust an
    # arbitrary X-Forwarded-For value for rate-limit identity.
    return str(request.META.get("REMOTE_ADDR") or "unknown")[:128]


def _probe_headers(response: JsonResponse) -> JsonResponse:
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _rate_limited_response() -> JsonResponse:
    response = JsonResponse(
        {"status": "error", "checks": {"rate_limit": "fail"}},
        status=429,
    )
    response["Retry-After"] = str(_PROBE_RATE_WINDOW_SECONDS)
    return _probe_headers(response)


def _build_response(
    checks: dict[str, tuple[str, str | None]],
    *,
    critical: set[str],
) -> JsonResponse:
    failed_critical = [
        name
        for name, (status, _) in checks.items()
        if status == "fail" and name in critical
    ]
    payload = {
        "status": "error" if failed_critical else "ok",
        "checks": {name: status for name, (status, _) in checks.items()},
    }
    if failed_critical:
        logger.warning("Readiness check failed: %s", ", ".join(failed_critical))
    return _probe_headers(
        JsonResponse(payload, status=503 if failed_critical else 200)
    )


class _RateLimitedProbeView(View):
    def dispatch(self, request, *args, **kwargs):
        if not _probe_rate_limiter.allow(_client_key(request)):
            return _rate_limited_response()
        return super().dispatch(request, *args, **kwargs)


@method_decorator(csrf_exempt, name="dispatch")
class HealthCheckView(_RateLimitedProbeView):
    """Liveness: prove only that this Django process serves requests."""

    def get(self, request):
        return _build_response({"process": ("ok", None)}, critical={"process"})


@method_decorator(csrf_exempt, name="dispatch")
class ReadyCheckView(_RateLimitedProbeView):
    """Readiness: local BFF dependencies, never provider reachability."""

    def get(self, request):
        checks = {
            "database": _check_database(),
            "cache": _check_cache(),
            "migrations": _check_migrations(),
            "queue": _check_queue(),
        }
        return _build_response(
            checks,
            critical={"database", "cache", "migrations", "queue"},
        )
