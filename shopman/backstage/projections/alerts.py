"""Typed operator-alert projections shared by Django and the operator UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
            actions=(
                ProductionActionProjection(
                    ref=f"acknowledge:{alert.pk}",
                    kind="acknowledge_alert",
                    label="Reconhecer",
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
                ),
            ),
        )
        for alert in alerts
    )
    return OperatorAlertsProjection(
        alerts=rows,
        counts=OperatorAlertCountsProjection(
            active=counts.active,
            critical=counts.critical,
        ),
    )
