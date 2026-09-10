"""Operator alert mutation service."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from shopman.backstage.services.exceptions import AlertConflict, AlertError

ALERT_ACTION_CLAIM_SCOPE = "backstage:alert-action-claim"


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

    # Reconhecer registra ciência; somente resolver encerra a causa. Um alerta
    # ainda aberto não pode sumir do sino — sobretudo os críticos.
    qs = OperatorAlert.objects.filter(resolved_at__isnull=True).order_by("-created_at")
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


def has_committed_alert_ack(
    pk: int,
    *,
    user,
    idempotency_key: str,
    action_proof: str,
) -> bool:
    """Allow an expired response-loss retry only for its durable exact receipt."""
    if not idempotency_key or not action_proof:
        return False
    from shopman.orderman.models import IdempotencyKey

    actor = _actor_ref(user)
    proof_digest = hashlib.sha256(action_proof.encode("utf-8")).hexdigest()
    receipt = IdempotencyKey.objects.filter(
        scope=ALERT_ACTION_CLAIM_SCOPE,
        key=proof_digest,
        status="done",
    ).first()
    body = dict(receipt.response_body or {}) if receipt else {}
    return (
        body.get("idempotency_key") == str(idempotency_key).strip()
        and body.get("alert_pk") == pk
        and body.get("actor") == actor
    )


def ack_alert(
    pk: int,
    *,
    user,
    expected_rev: int,
    idempotency_key: str,
    action_proof: str,
) -> bool:
    from shopman.backstage.models import OperatorAlert

    resolved_actor = _actor_ref(user)
    client_key = str(idempotency_key or "").strip()
    if user is None or not resolved_actor or expected_rev is None or not client_key or not action_proof:
        raise AlertConflict("Reconhecimento exige operador, revisão, chave idempotente e comprovante projetado.")

    for _attempt in range(2):
        try:
            with transaction.atomic():
                alerts = OperatorAlert.objects.select_for_update().filter(pk=pk)
                alerts = alerts.filter(audience__in=visible_alert_audiences(user))
                alert = alerts.first()
                if alert is None:
                    return False

                receipt = None
                if client_key:
                    from shopman.orderman.models import IdempotencyKey

                    proof_digest = hashlib.sha256(action_proof.encode("utf-8")).hexdigest()
                    receipt = (
                        IdempotencyKey.objects.select_for_update()
                        .filter(scope=ALERT_ACTION_CLAIM_SCOPE, key=proof_digest)
                        .first()
                    )
                    if receipt is not None:
                        receipt_body = dict(receipt.response_body or {})
                        expected = {
                            "idempotency_key": client_key,
                            "alert_pk": pk,
                            "actor": resolved_actor,
                        }
                        if {key: receipt_body.get(key) for key in expected} != expected:
                            raise AlertConflict("Esta ação de alerta já pertence a outra tentativa.")
                        if receipt.status == "done":
                            return True

                if alert.rev != expected_rev:
                    raise AlertConflict(
                        "O alerta mudou desde que foi exibido. Atualize antes de reconhecer.",
                        code="stale_projection",
                        data={
                            "expected_rev": expected_rev,
                            "current_rev": alert.rev,
                        },
                    )

                if client_key and receipt is None:
                    with transaction.atomic():
                        receipt = IdempotencyKey.objects.create(
                            scope=ALERT_ACTION_CLAIM_SCOPE,
                            key=proof_digest,
                            status="in_progress",
                            response_body={
                                "idempotency_key": client_key,
                                "alert_pk": pk,
                                "actor": resolved_actor,
                            },
                        )

                if alert.acknowledged:
                    raise AlertConflict("Este alerta já foi reconhecido por outra tentativa.")

                acknowledged_at = timezone.now()
                alert.acknowledged = True
                alert.acknowledged_at = acknowledged_at
                alert.acknowledged_by = resolved_actor
                alert.rev += 1
                alert.save(
                    update_fields=[
                        "acknowledged",
                        "acknowledged_at",
                        "acknowledged_by",
                        "rev",
                    ]
                )
                if receipt is not None:
                    receipt.status = "done"
                    receipt.response_code = 200
                    receipt.response_body = {
                        **dict(receipt.response_body or {}),
                        "acknowledged_at": acknowledged_at.isoformat(),
                    }
                    receipt.save(update_fields=["status", "response_code", "response_body"])
                return True
        except IntegrityError:
            if _attempt == 0:
                continue
            raise
    return False


def _actor_ref(user) -> str:
    if user is None:
        return ""
    getter = getattr(user, "get_username", None)
    value = getter() if callable(getter) else getattr(user, "username", "")
    return str(value or "")[:100]


def escalate_alert(pk: int, *, severity: str = "critical", message: str | None = None):
    from shopman.backstage.models import OperatorAlert

    _validate_choice(severity, {choice for choice, _ in OperatorAlert.SEVERITY_CHOICES}, "severidade")
    with transaction.atomic():
        alert = OperatorAlert.objects.select_for_update().filter(pk=pk).first()
        if alert is None:
            raise AlertError("Alerta não encontrado.")
        alert.severity = severity
        update_fields = ["severity", "rev"]
        if message is not None:
            alert.message = message.strip()
            update_fields.append("message")
        alert.rev += 1
        alert.save(update_fields=update_fields)
        return alert


def resolve_alerts(
    type: str,
    *,
    order_ref: str,
    actor: str,
) -> int:
    """Resolve matching causes under lock, preserving who/when and revision."""
    from shopman.backstage.models import OperatorAlert

    resolved_actor = str(actor or "").strip()[:100]
    resolved_order_ref = str(order_ref or "").strip()
    if not resolved_actor:
        raise AlertError("Identidade da resolução do alerta é obrigatória.")
    if not resolved_order_ref:
        raise AlertError("Referência do pedido é obrigatória para resolver alertas.")
    with transaction.atomic():
        alerts = OperatorAlert.objects.select_for_update().filter(
            type=type,
            resolved_at__isnull=True,
        )
        alerts = alerts.filter(order_ref=resolved_order_ref)
        rows = list(alerts.order_by("pk"))
        resolved_at = timezone.now()
        for alert in rows:
            alert.acknowledged = True
            alert.resolved_at = resolved_at
            alert.resolved_by = resolved_actor
            alert.rev += 1
            alert.save(
                update_fields=[
                    "acknowledged",
                    "resolved_at",
                    "resolved_by",
                    "rev",
                ]
            )
        return len(rows)


def _validate_choice(value: str, allowed: set[str], label: str) -> None:
    if value not in allowed:
        raise AlertError(f"{label.capitalize()} inválida: {value}")
