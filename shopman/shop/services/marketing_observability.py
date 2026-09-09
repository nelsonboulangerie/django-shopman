"""Low-cardinality Marketing telemetry and actionable operational alerts.

The application emits a vendor-neutral structured metric envelope.  A log
collector can translate it to the configured metrics backend without teaching
business code about Prometheus, StatsD or a specific dashboard vendor.

Metric names and labels are closed here on purpose: recipient/content/resource
dimensions cannot accidentally become expensive labels or a parallel PII store.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import connection
from django.db.models import Count, Min
from django.utils import timezone

from shopman.shop.models import DeliveryAttempt, DeliveryTarget, MarketingOutbox
from shopman.shop.services.observability import create_operator_alert, operational_event

logger = logging.getLogger(__name__)
_TRACE_REF_RE = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")

PLATFORMS = frozenset({"instagram", "facebook", "google_business", "whatsapp", "other"})
COMMAND_KINDS = frozenset({
    "approve",
    "reject",
    "reschedule",
    "publish_now",
    "cancel",
    "fire",
    "expire",
    "retry_delivery",
    "reconcile_delivery",
    "configure_platform",
})
COMMAND_OUTCOMES = frozenset({"accepted", "completed", "rejected", "conflict", "unknown"})
TARGET_STATES = frozenset({
    "planned",
    "suppressed",
    "queued",
    "sending",
    "accepted",
    "confirmed",
    "failed_retryable",
    "failed_final",
    "unknown",
    "cancelled",
    "expired",
})
ATTEMPT_OUTCOMES = frozenset({
    "not_attempted",
    "accepted_unconfirmed",
    "confirmed",
    "failed_retryable",
    "failed_final",
    "unknown",
})
STAGES = frozenset({
    "approved_graph",
    "delivery_attempt",
    "outbox",
    "outbox_directive",
    "provider_reconciliation",
})


@dataclass(frozen=True, slots=True)
class MetricSpec:
    kind: str
    labels: dict[str, frozenset[str]]


METRIC_SPECS: dict[str, MetricSpec] = {
    "marketing_command_total": MetricSpec("counter", {"kind": COMMAND_KINDS, "outcome": COMMAND_OUTCOMES}),
    "marketing_command_seconds": MetricSpec("histogram", {"kind": COMMAND_KINDS}),
    "marketing_outbox_age_seconds": MetricSpec("gauge", {}),
    "marketing_stuck_total": MetricSpec("gauge", {"stage": STAGES}),
    "marketing_delivery_target_total": MetricSpec("gauge", {"platform": PLATFORMS, "state": TARGET_STATES}),
    "marketing_delivery_attempt_total": MetricSpec("counter", {"platform": PLATFORMS, "outcome": ATTEMPT_OUTCOMES}),
    "marketing_duplicate_prevented_total": MetricSpec("counter", {"effect": frozenset({"command_replay", "outbox_handoff", "provider_effect"})}),
    "marketing_unknown_age_seconds": MetricSpec("gauge", {"platform": PLATFORMS}),
    "marketing_suppressed_total": MetricSpec("counter", {"reason": frozenset({"consent", "expired", "frequency_cap", "quiet_hours", "policy", "other"}), "platform": PLATFORMS}),
    "marketing_consent_violation_total": MetricSpec("counter", {}),
    "marketing_audience_resolution_seconds": MetricSpec("histogram", {"source_state": frozenset({"fresh", "cached", "degraded"})}),
    "marketing_audience_size_bucket": MetricSpec("gauge", {"bucket": frozenset({"0", "1_99", "100_999", "1000_9999", "10000_99999", "100000_plus"})}),
    "marketing_projection_seconds": MetricSpec("histogram", {"projection": frozenset({"board", "detail", "history", "platforms", "templates"})}),
    "projection_bytes": MetricSpec("histogram", {"projection": frozenset({"board", "detail", "history", "platforms", "templates"})}),
    "projection_queries": MetricSpec("histogram", {"projection": frozenset({"board", "detail", "history", "platforms", "templates"})}),
    "marketing_readiness": MetricSpec("gauge", {"platform": PLATFORMS, "state": frozenset({"ready", "degraded", "blocked", "unknown"})}),
    "readiness_age_seconds": MetricSpec("gauge", {"platform": PLATFORMS}),
    "marketing_alert_total": MetricSpec("counter", {"type": frozenset({"consent_violation", "duplicate_confirmed", "outbox_stuck", "reconciliation_mismatch", "unknown_stale", "partial_without_action", "readiness_stale"}), "lifecycle": frozenset({"created", "debounced", "acknowledged", "resolved"})}),
    "marketing_alert_seconds": MetricSpec("histogram", {"type": frozenset({"consent_violation", "duplicate_confirmed", "outbox_stuck", "reconciliation_mismatch", "unknown_stale", "partial_without_action", "readiness_stale"}), "lifecycle": frozenset({"acknowledged", "resolved"})}),
    "marketing_sse_connection": MetricSpec("gauge", {"state": frozenset({"connected", "disconnected", "fallback"})}),
    "marketing_sse_invalidations_total": MetricSpec("counter", {"outcome": frozenset({"applied", "ignored", "failed"})}),
    "marketing_sse_refetch_total": MetricSpec("counter", {"outcome": frozenset({"completed", "failed", "cancelled", "poll_fallback"})}),
    "marketing_ai_total": MetricSpec("counter", {"outcome": frozenset({"suggested", "accepted", "discarded", "schema_failed", "claim_failed", "moderation_failed"})}),
    "marketing_frontend_vital": MetricSpec("histogram", {"name": frozenset({"LCP", "INP", "CLS"}), "rating": frozenset({"good", "needs_improvement", "poor"}), "route": frozenset({"board", "campaigns", "templates", "platforms", "history", "announcement_detail", "other"}), "theme": frozenset({"light", "dark"})}),
    "marketing_session_total": MetricSpec("counter", {"outcome": frozenset({"authenticated", "anonymous", "expired", "forbidden", "recovered", "recovery_failed"})}),
    "marketing_action_total": MetricSpec("counter", {"kind": COMMAND_KINDS, "outcome": frozenset({"started", "completed", "failed", "conflict", "cancelled"})}),
}

_ALERT_POLICY = {
    "consent_violation": ("marketing_consent_violation", "critical", "docs/runbooks/marketing-privacy-incident.md"),
    "duplicate_confirmed": ("marketing_duplicate_confirmed", "critical", "docs/runbooks/marketing-duplicate-effect.md"),
    "outbox_stuck": ("marketing_outbox_stuck", "error", "docs/runbooks/marketing-outbox-stuck.md"),
    "reconciliation_mismatch": ("marketing_reconciliation_mismatch", "error", "docs/runbooks/marketing-reconciliation-mismatch.md"),
    "unknown_stale": ("marketing_unknown_stale", "error", "docs/runbooks/marketing-unknown-provider-effect.md"),
    "partial_without_action": ("marketing_partial_without_action", "error", "docs/runbooks/marketing-partial-delivery.md"),
    "readiness_stale": ("marketing_readiness_stale", "error", "docs/runbooks/marketing-provider-outage.md"),
}


def emit_metric(name: str, value: int | float, /, **labels: str) -> None:
    """Emit one validated metric sample; reject arbitrary dimensions."""

    spec = METRIC_SPECS.get(str(name))
    if spec is None:
        raise ValueError(f"Unknown Marketing metric: {name}")
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value < 0:
        raise ValueError("Metric value must be a finite non-negative number.")
    if set(labels) != set(spec.labels):
        raise ValueError(f"Metric {name} requires labels {sorted(spec.labels)}.")
    normalized: dict[str, str] = {}
    for label, allowed_values in spec.labels.items():
        label_value = str(labels[label])
        if label_value not in allowed_values:
            raise ValueError(f"Invalid {name} label {label}={label_value}.")
        normalized[label] = label_value
    operational_event(
        "marketing.metric",
        metric_name=name,
        metric_kind=spec.kind,
        metric_value=value,
        metric_labels=normalized,
    )


def record_command(*, kind: str, outcome: str, seconds: float, replayed: bool) -> None:
    emit_metric("marketing_command_total", 1, kind=kind, outcome=outcome)
    emit_metric("marketing_command_seconds", max(0.0, seconds), kind=kind)
    if replayed:
        emit_metric("marketing_duplicate_prevented_total", 1, effect="command_replay")


def record_delivery_execution(
    *,
    platform: str,
    outcome: str,
    replayed: bool,
    target_ref: str,
    attempt_ref: str,
) -> None:
    if replayed:
        emit_metric(
            "marketing_duplicate_prevented_total",
            1,
            effect="provider_effect",
        )
    elif outcome:
        emit_metric(
            "marketing_delivery_attempt_total",
            1,
            platform=_platform(platform),
            outcome=outcome,
        )
    record_correlation(
        stage="attempt",
        target_ref=target_ref,
        attempt_ref=attempt_ref,
    )


def record_correlation(
    *,
    stage: str,
    request_id: str = "",
    receipt_ref: str = "",
    outbox_ref: str = "",
    target_ref: str = "",
    attempt_ref: str = "",
    target_count: int = 0,
) -> None:
    """Log only technical edges; metrics deliberately never carry these refs."""

    if stage not in {"receipt", "outbox", "target", "attempt"}:
        raise ValueError(f"Unknown Marketing correlation stage: {stage}")
    fields = {
        "request_id": request_id,
        "receipt_ref": receipt_ref,
        "outbox_ref": outbox_ref,
        "target_ref": target_ref,
        "attempt_ref": attempt_ref,
    }
    if any(value and not _TRACE_REF_RE.fullmatch(str(value)) for value in fields.values()):
        raise ValueError("Marketing correlation refs must be technical identifiers.")
    operational_event(
        "marketing.correlation",
        correlation_stage=stage,
        **{key: str(value) for key, value in fields.items() if value},
        **({"target_count": max(0, int(target_count))} if target_count else {}),
    )


def observe_projection(projection: str, build):
    """Measure the complete projection build, including its database queries."""

    queries = 0

    def count_query(execute, sql, params, many, context):
        nonlocal queries
        queries += 1
        return execute(sql, params, many, context)

    started_at = time.perf_counter()
    failure: Exception | None = None
    result = None
    with connection.execute_wrapper(count_query):
        try:
            result = build()
        except Exception as exc:  # leave Django's context manager normally
            # Frozen structured API exceptions reject contextlib's attempt to
            # assign ``__traceback__``.  Re-raise after the wrapper has exited.
            failure = exc
    if failure is not None:
        raise failure
    seconds = time.perf_counter() - started_at
    from shopman.backstage.api.projections import projection_data

    payload = projection_data(result)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    emit_metric("marketing_projection_seconds", seconds, projection=projection)
    emit_metric("projection_bytes", len(encoded), projection=projection)
    emit_metric("projection_queries", queries, projection=projection)
    return result


def record_audience_resolution(*, seconds: float, degraded: bool, size: int) -> None:
    state = "degraded" if degraded else "fresh"
    emit_metric(
        "marketing_audience_resolution_seconds",
        max(0.0, seconds),
        source_state=state,
    )
    emit_metric("marketing_audience_size_bucket", 1, bucket=_audience_bucket(size))


def record_readiness(states: Any, *, now: datetime | None = None) -> None:
    clock = now or timezone.now()
    for item in states:
        platform = _platform(item.platform)
        emit_metric(
            "marketing_readiness",
            1 if item.state == "ready" else 0,
            platform=platform,
            state=item.state,
        )
        facts_at = item.facts_as_of or item.checked_at
        age = max(0, (clock - facts_at).total_seconds())
        emit_metric("readiness_age_seconds", age, platform=platform)


def record_outbox_cycle(*, reconciliation: Any, process: Any) -> None:
    """Publish aggregate queue signals and escalate only actionable drift."""

    emit_metric("marketing_outbox_age_seconds", process.oldest_due_age_seconds)
    for stage, count in (
        ("outbox", process.failed + reconciliation.stale_failed),
        ("outbox_directive", reconciliation.dispatched_without_directive),
        ("approved_graph", reconciliation.approved_without_graph),
    ):
        emit_metric("marketing_stuck_total", count, stage=stage)

    if reconciliation.directive_mismatch:
        record_alert(
            "reconciliation_mismatch",
            count=reconciliation.directive_mismatch,
            platform="all",
            stage="outbox_directive",
        )
    if reconciliation.dispatched_without_directive:
        record_alert(
            "outbox_stuck",
            count=reconciliation.dispatched_without_directive,
            platform="all",
            stage="outbox_directive",
        )
    if reconciliation.approved_without_graph:
        record_alert(
            "outbox_stuck",
            count=reconciliation.approved_without_graph,
            platform="all",
            stage="approved_graph",
        )
    if reconciliation.stale_failed or process.failed:
        record_alert(
            "outbox_stuck",
            count=reconciliation.stale_failed + process.failed,
            platform="all",
            stage="outbox",
        )


def collect_reconciler_signals(*, now: datetime | None = None) -> None:
    """Read bounded aggregate health; never call a provider or expose a target."""

    clock = now or timezone.now()
    for row in DeliveryTarget.objects.values("platform", "state").annotate(total=Count("pk")):
        emit_metric(
            "marketing_delivery_target_total",
            row["total"],
            platform=_platform(row["platform"]),
            state=row["state"],
        )
    unknown_cutoff = clock - timedelta(minutes=15)
    for row in (
        DeliveryTarget.objects.filter(state=DeliveryTarget.State.UNKNOWN)
        .values("platform")
        .annotate(total=Count("pk"), oldest=Min("updated_at"))
    ):
        age = max(0, int((clock - row["oldest"]).total_seconds()))
        platform = _platform(row["platform"])
        emit_metric("marketing_unknown_age_seconds", age, platform=platform)
        if row["oldest"] <= unknown_cutoff:
            record_alert(
                "unknown_stale",
                count=row["total"],
                platform=platform,
                stage="provider_reconciliation",
            )

    due_cutoff = clock - timedelta(seconds=30)
    outbox_stuck = MarketingOutbox.objects.filter(
        state=MarketingOutbox.State.PENDING,
        available_at__lte=due_cutoff,
    ).count()
    attempt_stuck = DeliveryAttempt.objects.filter(
        state=DeliveryAttempt.State.CALLING,
        started_at__lte=clock - timedelta(seconds=60),
    ).count()
    emit_metric("marketing_stuck_total", outbox_stuck, stage="outbox")
    emit_metric("marketing_stuck_total", attempt_stuck, stage="delivery_attempt")
    if outbox_stuck:
        record_alert("outbox_stuck", count=outbox_stuck, platform="all", stage="outbox")
    if attempt_stuck:
        record_alert(
            "outbox_stuck",
            count=attempt_stuck,
            platform="all",
            stage="delivery_attempt",
        )


def record_alert(
    alert_type: str,
    *,
    count: int,
    platform: str,
    stage: str,
    lifecycle: str = "created",
) -> Any:
    """Create a debounced alert with a precise filter and stable runbook."""

    try:
        model_type, severity, runbook = _ALERT_POLICY[alert_type]
    except KeyError as exc:
        raise ValueError(f"Unknown Marketing alert: {alert_type}") from exc
    if lifecycle != "created":
        raise ValueError("Alert creation accepts only the created lifecycle.")
    safe_platform = platform if platform == "all" else _platform(platform)
    if stage not in STAGES:
        raise ValueError(f"Unknown Marketing alert stage: {stage}")
    safe_count = max(1, int(count))
    alert = create_operator_alert(
        type=model_type,
        severity=severity,
        message=(
            f"Marketing requer ação: type={alert_type}; count={safe_count}; "
            f"filter=platform:{safe_platform},stage:{stage}; runbook={runbook}"
        ),
        dedupe_key=f"{alert_type}:{safe_platform}:{stage}",
        alert_domain="marketing",
        platform=safe_platform,
        stage=stage,
        runbook=runbook,
    )
    emit_metric(
        "marketing_alert_total",
        1,
        type=alert_type,
        lifecycle="created" if alert is not None else "debounced",
    )
    return alert


def _platform(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in PLATFORMS else "other"


def _audience_bucket(size: int) -> str:
    value = max(0, int(size))
    if value == 0:
        return "0"
    if value < 100:
        return "1_99"
    if value < 1_000:
        return "100_999"
    if value < 10_000:
        return "1000_9999"
    if value < 100_000:
        return "10000_99999"
    return "100000_plus"


__all__ = [
    "METRIC_SPECS",
    "collect_reconciler_signals",
    "emit_metric",
    "observe_projection",
    "record_audience_resolution",
    "record_alert",
    "record_command",
    "record_correlation",
    "record_delivery_execution",
    "record_outbox_cycle",
    "record_readiness",
]
