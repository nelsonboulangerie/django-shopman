"""Alert adapter — wraps OperatorAlert creation/query with lazy imports.

Keeps shop/ free of direct shopman.backstage imports.
"""

from __future__ import annotations

from typing import Any

#: Onde começa o comentário da cliente no aviso de nota baixa (``storefront.api.tracking``).
#: É texto livre da titular: a exclusão dela o corta daqui (``scrub_customer_comments``).
LOW_RATING_COMMENT_MARK = " Comentário: "


def scrub_customer_comments(order_refs) -> int:
    """Tira o comentário da cliente dos avisos de nota baixa destes pedidos (#2359).

    A exclusão do titular apaga o comentário do pedido (``customer_rating.comment``);
    o aviso ``low_rating`` levava uma cópia dele, que sobrevivia. A nota fica (é
    métrica da loja), o comentário sai. Devolve quantos avisos mudaram.
    """
    from shopman.backstage.models import OperatorAlert

    refs = [str(ref) for ref in order_refs if ref]
    if not refs:
        return 0
    changed = 0
    rows = OperatorAlert.objects.filter(
        type="low_rating", order_ref__in=refs, message__contains=LOW_RATING_COMMENT_MARK,
    ).values_list("pk", "message")
    for pk, message in rows:
        OperatorAlert.objects.filter(pk=pk).update(message=message.split(LOW_RATING_COMMENT_MARK, 1)[0])
        changed += 1
    return changed


def create(
    type: str,
    severity: str,
    message: str,
    *,
    order_ref: str = "",
    audience: str = "",
    respond_by=None,
) -> Any:
    """Create an OperatorAlert. Returns the created instance."""
    from shopman.backstage.models import OperatorAlert

    return OperatorAlert.objects.create(
        type=type,
        severity=severity,
        audience=audience or OperatorAlert.audience_for_type(type),
        message=message,
        order_ref=order_ref,
        respond_by=respond_by,
    )


def revise(
    pk: int, *, message: str | None = None, severity: str | None = None, respond_by=None, reopen: bool = False
) -> bool:
    """Atualiza um alerta ainda aberto (mensagem, severidade, prazo), com revisão nova.

    ``False`` quando o alerta já fechou. Campo ``None`` fica como está. ``reopen``: o
    acontecimento é novo, então o Visto de antes não vale mais (o aviso volta à tela).
    """
    from django.db import transaction

    from shopman.backstage.models import OperatorAlert

    with transaction.atomic():
        alert = OperatorAlert.objects.select_for_update().filter(pk=pk, resolved_at__isnull=True).first()
        if alert is None:
            return False
        fields = ["rev"]
        for name, value in (("message", message), ("severity", severity), ("respond_by", respond_by)):
            if value is not None:
                setattr(alert, name, value)
                fields.append(name)
        if reopen and alert.acknowledged:
            alert.acknowledged = False
            alert.acknowledged_at = None
            alert.acknowledged_by = ""
            fields += ["acknowledged", "acknowledged_at", "acknowledged_by"]
        alert.rev += 1
        alert.save(update_fields=fields)
        return True


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


def open_pk(type: str) -> int | None:
    """O ``pk`` do aviso aberto deste tipo (o mais novo), ou ``None``."""
    from shopman.backstage.models import OperatorAlert

    return (
        OperatorAlert.objects.filter(type=type, resolved_at__isnull=True)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
    )


def open_rows(type: str) -> list[tuple[int, str, str]]:
    """``(pk, order_ref, mensagem)`` dos avisos abertos deste tipo, do mais velho ao mais novo."""
    from shopman.backstage.models import OperatorAlert

    return list(
        OperatorAlert.objects.filter(type=type, resolved_at__isnull=True)
        .order_by("pk")
        .values_list("pk", "order_ref", "message")
    )


def open_rows_with_ref() -> list[tuple[int, str, str, str]]:
    """``(pk, tipo, order_ref, mensagem)`` de todo aviso aberto, do mais velho ao mais novo."""
    from shopman.backstage.models import OperatorAlert

    return list(
        OperatorAlert.objects.filter(resolved_at__isnull=True)
        .order_by("pk")
        .values_list("pk", "type", "order_ref", "message")
    )


def resolve(type: str, *, order_ref: str, actor: str) -> int:
    """Resolve active alert causes through the canonical audited service."""
    from shopman.backstage.services.alerts import resolve_alerts

    return resolve_alerts(type, order_ref=order_ref, actor=actor)


def oldest_open_created_at(type: str):
    """Quando nasceu o aviso aberto mais velho deste tipo, ou ``None`` sem aviso aberto."""
    from shopman.backstage.models import OperatorAlert

    return (
        OperatorAlert.objects.filter(type=type, resolved_at__isnull=True)
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )


def resolve_matching(type: str, *, message_contains: str, actor: str, order_ref: str = "") -> int:
    """Resolve causas abertas casando o marcador da mensagem; com ``order_ref``, só as daquele pedido."""
    from shopman.backstage.services.alerts import resolve_alerts_matching

    return resolve_alerts_matching(type, message_contains=message_contains, actor=actor, order_ref=order_ref)


def resolve_pk(pk: int, *, actor: str) -> int:
    """Resolve UM aviso aberto pelo ``pk``, com a mesma trilha (quem, quando, revisão)."""
    from shopman.backstage.services.alerts import resolve_alert_pk

    return resolve_alert_pk(pk, actor=actor)


def handled_since(pk: int, since) -> bool:
    """O aviso ``pk`` foi reconhecido ou resolvido por alguém em ``since`` ou depois (``None``: em qualquer hora)."""
    from shopman.backstage.models import OperatorAlert

    row = OperatorAlert.objects.filter(pk=pk).values("acknowledged", "acknowledged_at", "resolved_at").first()
    if row is None:
        return False
    moments = [row["acknowledged_at"] if row["acknowledged"] else None, row["resolved_at"]]
    return any(moment is not None and (since is None or moment >= since) for moment in moments)


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
