"""Operator alert mutation service."""

from __future__ import annotations

from dataclasses import dataclass

from shopman.backstage.services.exceptions import AlertError


@dataclass(frozen=True)
class AlertCounts:
    active: int
    critical: int


def visible_alert_audiences(user) -> frozenset[str]:
    """Audience partitions the current actor may read and mutate."""
    if user is None or getattr(user, "is_superuser", False):
        return frozenset({"production", "orders", "finance", "operations"})

    from shopman.backstage import permissions

    audiences = set()
    if permissions.can_access_production(user):
        audiences.add("production")
    if permissions.can_manage_orders(user) or permissions.can_operate_kds(user):
        audiences.add("orders")
    if permissions.can_audit_cash(user):
        audiences.add("finance")
    if permissions.can_manage_orders(user):
        audiences.add("operations")
    return frozenset(audiences)


def _active_for(user=None):
    from shopman.backstage.models import OperatorAlert

    qs = OperatorAlert.objects.filter(acknowledged=False).order_by("-created_at")
    if user is not None:
        qs = qs.filter(audience__in=visible_alert_audiences(user))
    return qs


def list_active_alerts(*, user=None, limit: int | None = None):
    qs = _active_for(user)
    if limit is None:
        return list(qs)
    return list(qs[:limit])


def active_counts(*, user=None) -> AlertCounts:
    active = _active_for(user)
    return AlertCounts(active=active.count(), critical=active.filter(severity="critical").count())


def create_alert(
    *,
    type: str,
    severity: str = "warning",
    message: str,
    order_ref: str = "",
    audience: str = "",
):
    from shopman.backstage.models import OperatorAlert

    _validate_choice(type, {choice for choice, _ in OperatorAlert.TYPE_CHOICES}, "tipo")
    _validate_choice(severity, {choice for choice, _ in OperatorAlert.SEVERITY_CHOICES}, "severidade")
    resolved_audience = audience or OperatorAlert.audience_for_type(type)
    _validate_choice(
        resolved_audience,
        {choice for choice, _ in OperatorAlert.AUDIENCE_CHOICES},
        "público",
    )
    if not message.strip():
        raise AlertError("Mensagem do alerta é obrigatória.")

    return OperatorAlert.objects.create(
        type=type,
        severity=severity,
        audience=resolved_audience,
        message=message.strip(),
        order_ref=order_ref,
    )


def ack_alert(pk: int, *, user=None) -> bool:
    from shopman.backstage.models import OperatorAlert

    alerts = OperatorAlert.objects.filter(pk=pk)
    if user is not None:
        alerts = alerts.filter(audience__in=visible_alert_audiences(user))
    alert = alerts.first()
    if alert is None:
        return False
    if alert.acknowledged:
        return True
    alert.acknowledged = True
    alert.save(update_fields=["acknowledged"])
    return True


def escalate_alert(pk: int, *, severity: str = "critical", message: str | None = None):
    from shopman.backstage.models import OperatorAlert

    _validate_choice(severity, {choice for choice, _ in OperatorAlert.SEVERITY_CHOICES}, "severidade")
    alert = OperatorAlert.objects.filter(pk=pk).first()
    if alert is None:
        raise AlertError("Alerta não encontrado.")
    alert.severity = severity
    if message is not None:
        alert.message = message.strip()
    alert.save(update_fields=["severity", "message"] if message is not None else ["severity"])
    return alert


def _validate_choice(value: str, allowed: set[str], label: str) -> None:
    if value not in allowed:
        raise AlertError(f"{label.capitalize()} inválida: {value}")
