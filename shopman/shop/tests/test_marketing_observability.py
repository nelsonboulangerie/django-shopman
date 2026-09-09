"""MKT-042 — low-cardinality metrics, privacy boundary and actionable alerts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from django.utils import timezone

from shopman.backstage.models import OperatorAlert
from shopman.shop.services.marketing_observability import (
    METRIC_SPECS,
    emit_metric,
    observe_projection,
    record_alert,
    record_audience_resolution,
    record_command,
    record_correlation,
    record_delivery_execution,
    record_outbox_cycle,
    record_readiness,
)

FORBIDDEN_LABELS = {
    "announcement",
    "body",
    "campaign",
    "content",
    "customer",
    "error",
    "phone",
    "prompt",
    "provider_response",
    "recipient",
    "url",
}


def test_metric_registry_contains_section_17_contract_without_forbidden_labels():
    required = {
        "marketing_command_total",
        "marketing_command_seconds",
        "marketing_outbox_age_seconds",
        "marketing_stuck_total",
        "marketing_delivery_target_total",
        "marketing_delivery_attempt_total",
        "marketing_duplicate_prevented_total",
        "marketing_unknown_age_seconds",
        "marketing_suppressed_total",
        "marketing_consent_violation_total",
        "marketing_audience_resolution_seconds",
        "marketing_audience_size_bucket",
        "marketing_projection_seconds",
        "projection_bytes",
        "projection_queries",
        "marketing_readiness",
        "readiness_age_seconds",
        "marketing_alert_total",
        "marketing_alert_seconds",
        "marketing_sse_connection",
        "marketing_ai_total",
        "marketing_frontend_vital",
        "marketing_session_total",
        "marketing_action_total",
    }

    assert required <= set(METRIC_SPECS)
    for spec in METRIC_SPECS.values():
        assert not (set(spec.labels) & FORBIDDEN_LABELS)


def test_metric_envelope_is_strict_and_low_cardinality():
    with patch(
        "shopman.shop.services.marketing_observability.operational_event"
    ) as event:
        emit_metric(
            "marketing_command_total",
            1,
            kind="approve",
            outcome="completed",
        )

    event.assert_called_once_with(
        "marketing.metric",
        metric_name="marketing_command_total",
        metric_kind="counter",
        metric_value=1,
        metric_labels={"kind": "approve", "outcome": "completed"},
    )
    with pytest.raises(ValueError, match="requires labels"):
        emit_metric(
            "marketing_command_total",
            1,
            kind="approve",
            outcome="completed",
            recipient="+5543999998888",
        )
    with pytest.raises(ValueError, match="Invalid"):
        emit_metric(
            "marketing_command_total",
            1,
            kind="announcement:123",
            outcome="completed",
        )


def test_command_replay_counts_prevented_duplicate_without_resource_label():
    with patch("shopman.shop.services.marketing_observability.emit_metric") as metric:
        record_command(kind="approve", outcome="completed", seconds=0.125, replayed=True)

    assert metric.call_args_list == [
        call("marketing_command_total", 1, kind="approve", outcome="completed"),
        call("marketing_command_seconds", 0.125, kind="approve"),
        call("marketing_duplicate_prevented_total", 1, effect="command_replay"),
    ]


def test_projection_records_latency_bytes_and_query_budget():
    with patch("shopman.shop.services.marketing_observability.emit_metric") as metric:
        result = observe_projection("board", lambda: {"items": [1, 2, 3]})

    assert result == {"items": [1, 2, 3]}
    names = [item.args[0] for item in metric.call_args_list]
    assert names == [
        "marketing_projection_seconds",
        "projection_bytes",
        "projection_queries",
    ]
    assert metric.call_args_list[1].args[1] == len(b'{"items":[1,2,3]}')


def test_audience_and_readiness_emit_only_buckets_and_platform_state():
    clock = timezone.now()
    states = [
        SimpleNamespace(
            platform="whatsapp",
            state="ready",
            checked_at=clock,
            facts_as_of=clock,
        )
    ]
    with patch("shopman.shop.services.marketing_observability.emit_metric") as metric:
        record_audience_resolution(seconds=0.4, degraded=False, size=123_456)
        record_readiness(states, now=clock)

    assert call(
        "marketing_audience_size_bucket",
        1,
        bucket="100000_plus",
    ) in metric.call_args_list
    assert call(
        "marketing_readiness",
        1,
        platform="whatsapp",
        state="ready",
    ) in metric.call_args_list


def test_attempt_metrics_and_correlation_keep_refs_out_of_labels():
    with (
        patch("shopman.shop.services.marketing_observability.emit_metric") as metric,
        patch("shopman.shop.services.marketing_observability.operational_event") as event,
    ):
        record_delivery_execution(
            platform="instagram",
            outcome="confirmed",
            replayed=False,
            target_ref="target-safe-1",
            attempt_ref="attempt-safe-1",
        )

    metric.assert_called_once_with(
        "marketing_delivery_attempt_total",
        1,
        platform="instagram",
        outcome="confirmed",
    )
    event.assert_called_once_with(
        "marketing.correlation",
        correlation_stage="attempt",
        target_ref="target-safe-1",
        attempt_ref="attempt-safe-1",
    )


def test_correlation_ref_contract_rejects_content_or_contact_shapes():
    with pytest.raises(ValueError, match="technical identifiers"):
        record_correlation(
            stage="target",
            target_ref="phone:+55 43 99999-8888",
        )


def test_reconciler_drift_creates_filtered_runbook_alerts_and_metrics():
    reconciliation = SimpleNamespace(
        linked_existing=0,
        directive_mismatch=2,
        stale_requeued=0,
        stale_failed=1,
        dispatched_without_directive=3,
        approved_without_graph=4,
    )
    process = SimpleNamespace(
        claimed=0,
        dispatched=0,
        requeued=0,
        failed=1,
        oldest_due_age_seconds=47,
    )

    with (
        patch("shopman.shop.services.marketing_observability.emit_metric") as metric,
        patch("shopman.shop.services.marketing_observability.record_alert") as alert,
    ):
        record_outbox_cycle(reconciliation=reconciliation, process=process)

    assert call("marketing_outbox_age_seconds", 47) in metric.call_args_list
    assert call("marketing_stuck_total", 3, stage="outbox_directive") in metric.call_args_list
    assert call(
        "reconciliation_mismatch",
        count=2,
        platform="all",
        stage="outbox_directive",
    ) in alert.call_args_list
    assert call(
        "outbox_stuck",
        count=4,
        platform="all",
        stage="approved_graph",
    ) in alert.call_args_list


def test_alert_always_names_filter_and_runbook_and_tracks_debounce():
    with (
        patch(
            "shopman.shop.services.marketing_observability.create_operator_alert",
            return_value=None,
        ) as create,
        patch("shopman.shop.services.marketing_observability.emit_metric") as metric,
    ):
        record_alert(
            "unknown_stale",
            count=7,
            platform="whatsapp",
            stage="provider_reconciliation",
        )

    kwargs = create.call_args.kwargs
    assert "filter=platform:whatsapp,stage:provider_reconciliation" in kwargs["message"]
    assert "runbook=docs/runbooks/marketing-unknown-provider-effect.md" in kwargs["message"]
    assert "phone" not in kwargs and "recipient" not in kwargs
    metric.assert_called_once_with(
        "marketing_alert_total",
        1,
        type="unknown_stale",
        lifecycle="debounced",
    )


@pytest.mark.django_db
def test_marketing_alert_is_durable_and_debounced_with_no_individual_ref():
    with patch("shopman.shop.services.marketing_observability.emit_metric"):
        first = record_alert(
            "unknown_stale",
            count=7,
            platform="whatsapp",
            stage="provider_reconciliation",
        )
        second = record_alert(
            "unknown_stale",
            count=8,
            platform="whatsapp",
            stage="provider_reconciliation",
        )

    assert first is not None
    assert second is None
    alert = OperatorAlert.objects.get(type="marketing_unknown_stale")
    assert alert.severity == "error"
    assert alert.order_ref == ""
    assert "platform:whatsapp" in alert.message
    assert "marketing-unknown-provider-effect.md" in alert.message
