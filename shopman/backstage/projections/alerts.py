"""Typed operator-alert projections shared by Django and the operator UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlencode

from django.utils import timezone

from shopman.backstage.projections.production import (
    ProductionActionConfirmationProjection,
    ProductionActionIdempotencyProjection,
    ProductionActionProjection,
)


@dataclass(frozen=True)
class OperatorAlertCountsProjection:
    active: int
    critical: int


@dataclass(frozen=True)
class OperatorAlertProjection:
    pk: int
    rev: int
    type: str
    type_label: str
    severity: Literal["warning", "error", "critical"]
    severity_label: str
    audience: str
    message: str
    order_ref: str
    created_at_display: str
    actions: tuple[ProductionActionProjection, ...]


@dataclass(frozen=True)
class OperatorAlertsProjection:
    alerts: tuple[OperatorAlertProjection, ...]
    counts: OperatorAlertCountsProjection
    generated_at: str = ""
    source_revision: str = ""
    fresh_until: str = ""
    contract_version: int = 1


def build_operator_alerts_projection(*, alerts, counts) -> OperatorAlertsProjection:
    alert_rows = tuple(alerts)
    production_refs = {alert.order_ref for alert in alert_rows if alert.order_ref and alert.audience == "production"}
    target_dates: dict[str, str] = {}
    if production_refs:
        from shopman.craftsman.models import WorkOrder

        target_dates = {
            ref: target_date.isoformat()
            for ref, target_date in WorkOrder.objects.filter(
                ref__in=production_refs,
            ).values_list("ref", "target_date")
            if target_date is not None
        }
    rows = tuple(
        OperatorAlertProjection(
            pk=alert.pk,
            rev=alert.rev,
            type=alert.type,
            type_label=alert.get_type_display(),
            severity=alert.severity,
            severity_label=alert.get_severity_display(),
            audience=alert.audience,
            message=alert.message,
            order_ref=alert.order_ref,
            created_at_display=timezone.localtime(alert.created_at).strftime("%d/%m às %H:%M"),
            actions=_alert_actions(
                alert,
                target_date=target_dates.get(alert.order_ref, ""),
            ),
        )
        for alert in alert_rows
    )
    return OperatorAlertsProjection(
        alerts=rows,
        counts=OperatorAlertCountsProjection(
            active=counts.active,
            critical=counts.critical,
        ),
    )


_PRODUCTION_CONTEXT_PATHS = {
    "production_late": "/",
    "production_low_yield": "/expedite",
    "production_stock_short": "/expedite",
    "production_stock_shortfall": "/plan",
    "production_forgotten": "/plan",
    "production_unfinished": "/expedite",
    "production_batch_traceability": "/expedite",
    "production_quality_communication": "/expedite",
    "production_quality_hold_risk": "/expedite",
    "stock_discrepancy": "/plan",
    "stock_low": "/plan",
}

_ORDER_CONTEXT_PATHS = {
    "order_production_quality_risk": "/",
    "customer_cancellation_requested": "/",
}


def _alert_actions(alert, *, target_date: str = "") -> tuple[ProductionActionProjection, ...]:
    actions = []
    path = _PRODUCTION_CONTEXT_PATHS.get(alert.type) or _ORDER_CONTEXT_PATHS.get(alert.type)
    if path is not None:
        exact_order_path = alert.type == "customer_cancellation_requested" and bool(alert.order_ref)
        if exact_order_path:
            path = f"/{quote(alert.order_ref, safe='')}"
        query_params = {}
        if alert.order_ref and not exact_order_path:
            query_params["q"] = alert.order_ref
        if target_date:
            query_params["date"] = target_date
        query = urlencode(query_params)
        href = f"{path}?{query}" if query else path
        actions.append(
            ProductionActionProjection(
                ref=f"open-context:{alert.pk}",
                kind="open_alert_context",
                label="Resolver no contexto",
                priority=10,
                enabled=True,
                reason="",
                method="GET",
                href=href,
                payload_schema="",
                expected_rev=None,
                idempotency=ProductionActionIdempotencyProjection(
                    required=False,
                    key_scope="",
                ),
                confirmation=ProductionActionConfirmationProjection(
                    required=False,
                    reason_required=False,
                    title="",
                    confirm_label="Abrir",
                ),
                approval_requirement=None,
                source_alert_ref=str(alert.pk),
                source_alert_effect="keeps_open",
                proof="",
            )
        )
    if not alert.acknowledged:
        actions.append(
            ProductionActionProjection(
                ref=f"acknowledge:{alert.pk}",
                kind="acknowledge_alert",
                label="Visto",
                priority=20,
                enabled=True,
                reason="",
                method="POST",
                href=f"/api/v1/backstage/alerts/{alert.pk}/ack/",
                payload_schema="AlertAckMutationRequest",
                expected_rev=alert.rev,
                idempotency=ProductionActionIdempotencyProjection(
                    required=True,
                    key_scope=f"backstage.alert-ack:{alert.pk}",
                ),
                confirmation=ProductionActionConfirmationProjection(
                    required=False,
                    reason_required=False,
                    title="",
                    confirm_label="Confirmar",
                ),
                approval_requirement=None,
                source_alert_ref=str(alert.pk),
                source_alert_effect="acknowledges",
                proof="",
            )
        )
    return tuple(actions)
