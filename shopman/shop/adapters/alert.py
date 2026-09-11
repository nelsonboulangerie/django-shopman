"""Alert adapter — wraps OperatorAlert creation/query with lazy imports.

Keeps shop/ free of direct shopman.backstage imports.
"""

from __future__ import annotations

from typing import Any


def create(
    type: str,
    severity: str,
    message: str,
    *,
    order_ref: str = "",
    audience: str = "",
) -> Any:
    """Create an OperatorAlert. Returns the created instance."""
    from shopman.backstage.models import OperatorAlert

    return OperatorAlert.objects.create(
        type=type,
        severity=severity,
        audience=audience or OperatorAlert.audience_for_type(type),
        message=message,
        order_ref=order_ref,
    )


def recent_exists(
    type: str,
    since,
    *,
    message_contains: str | None = None,
    order_ref: str | None = None,
    active_only: bool = True,
) -> bool:
    """Return True if an alert of this type was created at or after `since`.

    Used for debouncing: skip duplicate alerts within a time window.
    """
    from shopman.backstage.models import OperatorAlert

    qs = OperatorAlert.objects.filter(type=type)
    if active_only:
        # ``Visto`` registra ciência, mas não encerra a causa. O mesmo alerta
        # continua sendo a unidade de dedupe até uma resolução auditada — sem
        # expirar artificialmente depois da janela temporal do chamador.
        qs = qs.filter(resolved_at__isnull=True)
    else:
        qs = qs.filter(created_at__gte=since)
    if order_ref is not None:
        qs = qs.filter(order_ref=order_ref)
    if message_contains is not None:
        qs = qs.filter(message__contains=message_contains)
    return qs.exists()


def exists(
    type: str,
    *,
    message_contains: str | None = None,
    order_ref: str | None = None,
) -> bool:
    """Return whether the immutable alert fact was ever recorded."""
    from shopman.backstage.models import OperatorAlert

    qs = OperatorAlert.objects.filter(type=type)
    if order_ref is not None:
        qs = qs.filter(order_ref=order_ref)
    if message_contains is not None:
        qs = qs.filter(message__contains=message_contains)
    return qs.exists()


def open_counts(types) -> dict[str, int]:
    """Count unacknowledged alerts by type without exposing a surface model."""
    from django.db.models import Count

    from shopman.backstage.models import OperatorAlert

    rows = (
        OperatorAlert.objects.filter(type__in=tuple(types), acknowledged=False)
        .values("type")
        .annotate(total=Count("pk"))
        .order_by("type")
    )
    return {str(row["type"]): int(row["total"]) for row in rows}


def resolve(type: str, *, order_ref: str, actor: str) -> int:
    """Resolve active alert causes through the canonical audited service."""
    from shopman.backstage.services.alerts import resolve_alerts

    return resolve_alerts(type, order_ref=order_ref, actor=actor)


def connect_saved(receiver, *, dispatch_uid: str, weak: bool = False) -> None:
    """Connect a receiver to OperatorAlert post-save without leaking imports."""
    from django.db.models.signals import post_save

    from shopman.backstage.models import OperatorAlert

    post_save.connect(
        receiver,
        sender=OperatorAlert,
        dispatch_uid=dispatch_uid,
        weak=weak,
    )
