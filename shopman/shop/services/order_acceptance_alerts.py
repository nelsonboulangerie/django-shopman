"""O pedido que espera aceite chega no bolso de quem atende (issue #2324).

Dois avisos pessoais, pela mesma via dos outros (``user_notifications``: sino,
SSE e Web Push quando a pessoa ligou os avisos no dispositivo), os dois
``critical``: o Web Push sai com ``Urgency: high``, toca de novo na mesma
notificação e chega também ao dispositivo do PDV, que só recebe o crítico.

* **Pedido novo com prazo de fora** — o canal tem ``external_sla_minutes`` (o
  iFood cancela sozinho em 8 min, contados da criação lá) e o aceite é
  ``manual``. Sem push, o pedido entrava mudo: o som do Gestor só toca com a
  aba aberta e o som ligado, e dois pedidos já caíram assim (DEV-2026-012).
* **Pedido parado** — o ``order.stale_new_alert`` (aos 5 min no iFood) além do
  ``OperatorAlert`` da tela. Substitui o aviso do pedido novo: no bolso fica um
  aviso só por pedido, o mais recente.

Quem recebe: quem tem ``shop.manage_orders`` (a régua do Gestor de pedidos).
Os dois somem quando o pedido sai de ``new`` (aceito, recusado, cancelado pelo
iFood): ``resolve`` é chamado pelo ``lifecycle.dispatch`` a cada fase, e o
``reconcile`` é a rede da leitura do sino. Push ainda na fila de um aviso já
resolvido não sai (``NotificationPushHandler`` lê o lifecycle antes de enviar).

Corpo fica vazio no Web Push (categoria ``order`` é sensível, ver
``handlers/notification_push._push_payload``): o TÍTULO precisa dizer tudo.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Order

logger = logging.getLogger(__name__)

ORDER_NEW_AWAITING_ACCEPTANCE = "order_new_awaiting_acceptance"
ORDER_STALE_AWAITING_ACCEPTANCE = "order_stale_awaiting_acceptance"
CONDITIONS = (ORDER_NEW_AWAITING_ACCEPTANCE, ORDER_STALE_AWAITING_ACCEPTANCE)
PERMISSION = "shop.manage_orders"
OWNER_ORDERS = "orders"


def source_ref(order_ref: str) -> str:
    return f"order:{order_ref}"


def order_ref_from_source(value: str) -> str:
    head, separator, raw = str(value or "").partition(":")
    return raw if head == "order" and separator and raw else ""


def deep_link(value: str) -> str:
    """O detalhe do pedido no Gestor (relativo à base do app)."""
    order_ref = order_ref_from_source(value)
    return f"/{order_ref}" if order_ref else ""


# ── Os dois avisos ─────────────────────────────────────────────────────


def notify_new_order(order, config) -> int:
    """Pedido novo cujo aceite tem prazo de fora: avisa quem atende. Devolve quantos avisos."""
    confirmation = config.confirmation
    if confirmation.mode != "manual" or int(confirmation.external_sla_minutes or 0) <= 0:
        return 0
    if order.status != Order.Status.NEW:
        return 0
    deadline = external_deadline(order)
    who = _order_label(order)
    if deadline is not None:
        clock = _clock(deadline)
        title = f"{who} novo: aceite até {clock}"
        message = (
            f"{who} chegou e espera aceite. Se ninguém aceitar até {clock}, "
            f"{_canceller(order)} cancela o pedido."
        )
    else:
        title = f"{who} novo: aceite no Gestor"
        message = f"{who} chegou e espera aceite no Gestor de pedidos."
    return _notify(
        order,
        condition=ORDER_NEW_AWAITING_ACCEPTANCE,
        title=title,
        message=message,
        deadline=deadline,
    )


def notify_stale_order(order, *, deadline: datetime | None = None) -> int:
    """O pedido continua em ``new`` na hora do aviso de pedido parado. Devolve quantos avisos.

    ``deadline`` é o prazo de aceite da casa (``auto_cancel``); sem ele, vale o do
    marketplace (``data.ifood.confirm_by``).
    """
    if order.status != Order.Status.NEW:
        return 0
    who = _order_label(order)
    own_deadline = deadline is not None
    deadline = deadline or external_deadline(order)
    if deadline is not None:
        clock = _clock(deadline)
        if own_deadline:
            title = f"{who} sem aceite: cancela sozinho às {clock}"
            message = (
                f"{who} espera aceite. Se ninguém aceitar até {clock}, ele é cancelado "
                "sozinho e o que o cliente pagou é devolvido."
            )
        else:
            canceller = _canceller(order)
            title = f"{who} sem aceite: {canceller} cancela às {clock}"
            message = (
                f"{who} espera aceite. Se ninguém aceitar até {clock}, {canceller} "
                "cancela o pedido."
            )
    else:
        minutes = max(1, int((timezone.now() - order.created_at).total_seconds() // 60))
        title = f"{who} espera aceite há {minutes} min"
        message = f"{who} espera aceite há {minutes} min. O cliente está esperando a resposta."
    created = _notify(
        order,
        condition=ORDER_STALE_AWAITING_ACCEPTANCE,
        title=title,
        message=message,
        deadline=deadline,
    )
    # No bolso fica um aviso só por pedido: o lembrete substitui o do pedido novo.
    _close(ORDER_NEW_AWAITING_ACCEPTANCE, order.ref, outcome_code="superseded_by_stale")
    return created


def resolve(order) -> int:
    """O pedido saiu de ``new``: os avisos de aceite somem. Barato quando não há nenhum."""
    if order.status == Order.Status.NEW:
        return 0
    outcome = f"order_{order.status}"
    return sum(_close(condition, order.ref, outcome_code=outcome) for condition in CONDITIONS)


def reconcile(source_condition: str, value: str) -> int:
    """Rede de recuperação na leitura do sino: fecha o aviso cuja causa acabou."""
    from shopman.shop.models import NotificationLifecycle
    from shopman.shop.services.user_notifications import reconcile_condition

    order_ref = order_ref_from_source(value)
    order = Order.objects.filter(ref=order_ref).first() if order_ref else None
    if order is None:
        return reconcile_condition(
            source_condition=source_condition,
            source_ref=value,
            state=NotificationLifecycle.EXPIRED,
            outcome_code="order_missing",
        )
    if order.status != Order.Status.NEW:
        return reconcile_condition(
            source_condition=source_condition,
            source_ref=value,
            state=NotificationLifecycle.RESOLVED,
            outcome_code=f"order_{order.status}",
        )
    return 0


def external_deadline(order) -> datetime | None:
    """Quando o marketplace cancela o pedido sozinho (``data.ifood.confirm_by``)."""
    raw = str(((order.data or {}).get("ifood") or {}).get("confirm_by") or "").strip()
    if not raw:
        return None
    moment = parse_datetime(raw)
    if moment is None:
        return None
    return moment if timezone.is_aware(moment) else timezone.make_aware(moment)


# ── Internos ───────────────────────────────────────────────────────────


def _notify(order, *, condition: str, title: str, message: str, deadline: datetime | None) -> int:
    from django.contrib.auth import get_user_model

    from shopman.shop.models import NotificationCategory, NotificationSeverity
    from shopman.shop.services.user_notifications import create_condition_alert

    managers = get_user_model().objects.with_perm(
        PERMISSION,
        is_active=True,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    created = 0
    for manager in managers.iterator():
        result = create_condition_alert(
            user=manager,
            category=NotificationCategory.ORDER,
            title=title,
            message=message,
            source_condition=condition,
            source_ref=source_ref(order.ref),
            source_version=1,
            action_data={"order_ref": order.ref},
            severity=NotificationSeverity.CRITICAL,
            owner_role=OWNER_ORDERS,
            expires_at=deadline,
        )
        created += int(result.created)
    return created


def _close(condition: str, order_ref: str, *, outcome_code: str) -> int:
    from shopman.shop.models import NotificationLifecycle
    from shopman.shop.services.user_notifications import reconcile_condition

    return reconcile_condition(
        source_condition=condition,
        source_ref=source_ref(order_ref),
        state=NotificationLifecycle.RESOLVED,
        outcome_code=outcome_code,
    )


def _order_label(order) -> str:
    """Como quem atende chama o pedido: o número do iFood, ou o ref da casa."""
    ifood = (order.data or {}).get("ifood") or {}
    display_id = str(ifood.get("display_id") or "").strip()
    if ifood:
        return f"Pedido iFood {display_id or order.ref}"
    return f"Pedido {order.ref}"


def _canceller(order) -> str:
    return "o iFood" if (order.data or {}).get("ifood") else "o marketplace"


def _clock(moment: datetime) -> str:
    return timezone.localtime(moment).strftime("%H:%M")


__all__ = [
    "CONDITIONS",
    "ORDER_NEW_AWAITING_ACCEPTANCE",
    "ORDER_STALE_AWAITING_ACCEPTANCE",
    "deep_link",
    "external_deadline",
    "notify_new_order",
    "notify_stale_order",
    "reconcile",
    "resolve",
    "source_ref",
]
