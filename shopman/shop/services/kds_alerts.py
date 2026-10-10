"""Avisos da Cozinha no bolso: pedido novo e ticket atrasado (SUITE-UX §10.3).

Dois avisos pessoais, pela mesma via dos outros (``user_notifications``: sino,
SSE e Web Push quando a pessoa ligou os avisos no dispositivo):

* **Pedido novo** — para quem leva a estação no bolso. O celular da estação
  pequena (barista, lanches) apaga a tela; sem push, o pedido entra mudo. Quem
  abre o quadro de uma estação no celular passa a segui-la por um turno
  (``follow``); o aviso some quando alguém dá "Visto" ou inicia o ticket.
* **Atrasado** — para quem cadastra as estações (``backstage.change_kdsinstance``,
  a gerente). Ela não vigia quadro: recebe quando o ticket passa da meta da
  estação (o mesmo número do relógio do card) e o aviso some sozinho quando o
  ticket sai da estação (prévia v4 ``cozinha-celular`` c).

Os seguidores ficam em ``KDSInstance.config["followers"]`` (``{user_id: iso}``,
ver ``docs/reference/data-schemas.md``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.utils import timezone

from shopman.shop.adapters import kds as kds_adapter

logger = logging.getLogger(__name__)

KDS_TICKET_NEW = "kds_ticket_new"
KDS_TICKET_LATE = "kds_ticket_late"
CONDITIONS = (KDS_TICKET_NEW, KDS_TICKET_LATE)
OWNER_KITCHEN = "kitchen"
#: Seguir a estação vale por um turno: o celular esquecido no armário não
#: continua recebendo pedido de amanhã.
FOLLOW_TTL = timedelta(hours=12)
#: Quem recebe o atraso: quem cadastra as estações da Cozinha.
LATE_PERMISSION = "backstage.change_kdsinstance"
OPEN_STATUSES = ("pending", "in_progress")


def source_ref(ticket_pk: int) -> str:
    return f"kds_ticket:{int(ticket_pk)}"


def ticket_pk_from_ref(value: str) -> int | None:
    head, separator, raw = str(value or "").partition(":")
    if head != "kds_ticket" or separator != ":" or not raw.isdigit():
        return None
    return int(raw) or None


# ── Seguir a estação ───────────────────────────────────────────────────


def follow(instance, user) -> None:
    """Este operador passa a receber o pedido novo desta estação (e só desta)."""
    if not getattr(user, "pk", None):
        return
    key = str(user.pk)
    now = timezone.now()
    for other in kds_adapter.instances_followed_by(user.pk):
        if other.pk == instance.pk:
            continue
        config = dict(other.config or {})
        followers = dict(config.get("followers") or {})
        followers.pop(key, None)
        config["followers"] = followers
        other.config = config
        other.save(update_fields=["config"])
    config = dict(instance.config or {})
    followers = {k: v for k, v in dict(config.get("followers") or {}).items() if _fresh(v, now=now)}
    followers[key] = now.isoformat()
    config["followers"] = followers
    instance.config = config
    instance.save(update_fields=["config"])


def followers(instance) -> list[int]:
    now = timezone.now()
    return [
        int(user_id)
        for user_id, since in dict((instance.config or {}).get("followers") or {}).items()
        if str(user_id).isdigit() and _fresh(since, now=now)
    ]


def _fresh(value, *, now: datetime) -> bool:
    try:
        since = datetime.fromisoformat(str(value))
    except ValueError:
        return False
    if timezone.is_naive(since):
        since = timezone.make_aware(since)
    return now - since <= FOLLOW_TTL


# ── Os dois avisos ─────────────────────────────────────────────────────


def notify_new_ticket(ticket) -> int:
    """Pedido novo na estação: avisa quem a leva no bolso. Devolve quantos avisos."""
    from django.contrib.auth import get_user_model

    from shopman.shop.models import NotificationCategory, NotificationSeverity
    from shopman.shop.services.user_notifications import create_condition_alert

    instance = ticket.kds_instance
    user_ids = followers(instance)
    if not user_ids:
        return 0
    users = get_user_model().objects.filter(pk__in=user_ids, is_active=True)
    code = _order_code(ticket)
    created = 0
    for user in users:
        if not user.has_perm("backstage.operate_kds"):
            continue
        result = create_condition_alert(
            user=user,
            category=NotificationCategory.KITCHEN,
            title=f"Pedido novo {code}",
            message=f"{_station_label(instance)}: {_items_line(ticket)}",
            source_condition=KDS_TICKET_NEW,
            source_ref=source_ref(ticket.pk),
            source_version=1,
            action_data={"station_ref": instance.ref, "ticket_pk": ticket.pk},
            severity=NotificationSeverity.ACTION_REQUIRED,
            owner_role=OWNER_KITCHEN,
        )
        created += int(result.created)
    return created


def notify_late_ticket(ticket) -> int:
    """O ticket passou da meta da estação e ainda está nela: avisa a gerente."""
    from django.contrib.auth import get_user_model

    from shopman.shop.models import NotificationCategory, NotificationSeverity
    from shopman.shop.services.user_notifications import create_condition_alert

    if ticket.status not in OPEN_STATUSES:
        return 0
    instance = ticket.kds_instance
    target = int(instance.target_time_minutes or 0)
    if target <= 0:
        return 0
    elapsed = max(0, int((timezone.now() - ticket.created_at).total_seconds() // 60))
    code = _order_code(ticket)
    managers = get_user_model().objects.with_perm(
        LATE_PERMISSION,
        is_active=True,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    created = 0
    for manager in managers.iterator():
        result = create_condition_alert(
            user=manager,
            category=NotificationCategory.KITCHEN,
            title=f"Atrasado: {code} passou de {target} min",
            message=f"{_station_label(instance)}, {elapsed} min (meta {target}). {_items_line(ticket)}",
            source_condition=KDS_TICKET_LATE,
            source_ref=source_ref(ticket.pk),
            source_version=1,
            action_data={"station_ref": instance.ref, "ticket_pk": ticket.pk},
            severity=NotificationSeverity.WARNING,
            owner_role=OWNER_KITCHEN,
        )
        created += int(result.created)
    return created


def resolve_new_ticket(ticket, *, outcome_code: str) -> int:
    return _resolve(KDS_TICKET_NEW, ticket.pk, outcome_code=outcome_code)


def resolve_ticket(ticket, *, outcome_code: str) -> int:
    """O ticket saiu da estação (pronto, cancelado): os dois avisos somem."""
    return sum(_resolve(condition, ticket.pk, outcome_code=outcome_code) for condition in CONDITIONS)


def reconcile(source_condition: str, value: str) -> int:
    """Rede de recuperação na leitura do sino: fecha o aviso cuja causa acabou."""
    from shopman.shop.models import NotificationLifecycle
    from shopman.shop.services.user_notifications import reconcile_condition

    ticket_pk = ticket_pk_from_ref(value)
    ticket = kds_adapter.get_ticket(ticket_pk) if ticket_pk else None
    if ticket is None:
        return reconcile_condition(
            source_condition=source_condition,
            source_ref=value,
            state=NotificationLifecycle.EXPIRED,
            outcome_code="kds_ticket_missing",
        )
    if ticket.status not in OPEN_STATUSES:
        return reconcile_condition(
            source_condition=source_condition,
            source_ref=value,
            state=NotificationLifecycle.RESOLVED,
            outcome_code=f"kds_ticket_{ticket.status}",
        )
    if source_condition == KDS_TICKET_NEW and (ticket.status != "pending" or ticket.seen_at is not None):
        return reconcile_condition(
            source_condition=source_condition,
            source_ref=value,
            state=NotificationLifecycle.RESOLVED,
            outcome_code="kds_ticket_seen",
        )
    return 0


def deep_link(value: str) -> str:
    """O quadro da estação do ticket, na Cozinha (relativo à base do app)."""
    ticket_pk = ticket_pk_from_ref(value)
    ticket = kds_adapter.get_ticket(ticket_pk) if ticket_pk else None
    return f"/{ticket.kds_instance.ref}" if ticket is not None else "/"


def late_check_at(ticket) -> datetime | None:
    """Quando o ticket estoura a meta da estação (``None`` sem meta)."""
    target = int(ticket.kds_instance.target_time_minutes or 0)
    if target <= 0:
        return None
    return ticket.created_at + timedelta(minutes=target)


def _resolve(condition: str, ticket_pk: int, *, outcome_code: str) -> int:
    from shopman.shop.models import NotificationLifecycle
    from shopman.shop.services.user_notifications import reconcile_condition

    return reconcile_condition(
        source_condition=condition,
        source_ref=source_ref(ticket_pk),
        state=NotificationLifecycle.RESOLVED,
        outcome_code=outcome_code,
    )


def _station_label(instance) -> str:
    name = str(instance.name or instance.ref)
    return name if name.lower().startswith("estação") else f"Estação {name}"


def _items_line(ticket) -> str:
    parts = []
    for item in ticket.items or []:
        qty = item.get("qty", 1)
        try:
            qty_text = f"{float(qty):g}"
        except (TypeError, ValueError):
            qty_text = str(qty)
        parts.append(f"{qty_text}× {item.get('name') or item.get('sku') or 'item'}")
    line = ", ".join(parts[:3])
    if len(parts) > 3:
        line += f" e mais {len(parts) - 3}"
    return line


def _order_code(ticket) -> str:
    """O código que a cozinha chama: o final do ref do pedido, ou a comanda."""
    from shopman.orderman.models import Order, Session

    from shopman.shop.services.operator_orders import short_ref

    ref = (
        Order.objects.filter(session_key=ticket.session_key)
        .order_by("-id")
        .values_list("ref", flat=True)
        .first()
    )
    if ref:
        return short_ref(ref)
    session = Session.objects.filter(session_key=ticket.session_key).order_by("-id").first()
    data = (getattr(session, "data", None) or {}) if session is not None else {}
    return str(data.get("tab_display") or getattr(session, "handle_ref", "") or f"#{ticket.pk}")
