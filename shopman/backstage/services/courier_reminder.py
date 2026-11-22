"""Lembrete de chamar o entregador — TEMPORÁRIO, até a chamada antecipada aprender.

X minutos depois do início do preparo de uma entrega da casa (nunca iFood) sem
corrida pedida, o Gestor cobra o operador: "Pedido 0042 em preparo há 10 min. Já
dá para chamar o entregador?", com o botão "Chamar entregador" e o "Dispensar".

É mecanismo independente do automático (WP-ENTREGADOR-CHAMADA-ANTECIPADA): quando
ele chegar, este módulo, a chave ``Shop.defaults["delivery"]["courier_reminder"]``
e o aviso do cartão saem inteiros.

Um aviso por pedido, por construção: o lembrete não é gravado, é LIDO do pedido a
cada leitura do quadro. Vale em preparo e em pronto enquanto o pedido não tem
corrida viva nem chamada em curso; some quando a corrida é pedida, quando o
pedido sai do balcão ou quando alguém dispensa (``Order.data["courier_reminder"]``,
que vale para todos os dispositivos). Antes ele morria na primeira chamada: a
corrida que ninguém aceitou (N) ou que a central cancelou (C) deixava o pedido
sem entregador e sem lembrete (revisão das Entregas, ENT-15). Agora ele volta
:data:`AFTER_FAILED_RIDE_MINUTES` depois do fim dela, mesmo dispensado antes.

O início do preparo é o primeiro marco disponível, nesta ordem: o primeiro
"Iniciar preparo" do KDS (``Order.data["kds_started"]``); o ``Order.preparing_at``
(a comanda ainda não paga não grava ``kds_started``, e é o caso que cai aqui); o
aceite; a criação.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.protocols import RideState
from shopman.shop.services import delivery_services

#: Padrão do dono (13/10/2026): 10 minutos depois do início do preparo, ligado.
DEFAULT_MINUTES = 10
MAX_MINUTES = 240

#: Depois de uma corrida que terminou sem entregar (ninguém atendeu ou cancelada), o lembrete volta em 2 min.
AFTER_FAILED_RIDE_MINUTES = 2

#: Onde o pedido ainda espera entregador: no preparo ou pronto no balcão.
REMINDER_STATUSES = (Order.Status.PREPARING, Order.Status.READY)


@dataclass(frozen=True)
class CourierReminderProjection:
    """O lembrete de um pedido. A tela mostra quando o relógio passa de ``due_at_iso``."""

    #: Quando o aviso passa a valer (início do preparo + X min).
    due_at_iso: str
    #: O início do preparo: o "há N min" da frase conta daqui.
    since_iso: str
    #: De qual marco veio o início: ``kds`` · ``preparing`` · ``accepted`` · ``created``.
    since_basis: str
    #: O código curto do pedido, como a casa fala ("0042").
    short_ref: str
    #: Onde o pedido está: ``preparing`` (em preparo), ``ready`` (pronto, no
    #: balcão) ou ``retry`` (a última corrida terminou sem entregador).
    stage: str = "preparing"


def reminder_config(shop=None) -> tuple[bool, int]:
    """(ligado, minutos) de ``Shop.defaults["delivery"]["courier_reminder"]``."""
    if shop is None:
        from shopman.shop.models import Shop

        shop = Shop.load()
    delivery = ((getattr(shop, "defaults", None) or {}) if shop else {}).get("delivery") or {}
    cfg = delivery.get("courier_reminder") if isinstance(delivery, dict) else None
    cfg = cfg if isinstance(cfg, dict) else {}
    enabled = cfg.get("enabled", True) is not False
    minutes = cfg.get("minutes")
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= MAX_MINUTES:
        minutes = DEFAULT_MINUTES
    return enabled, minutes


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def prep_started_at(order: Order) -> tuple[datetime | None, str]:
    """O início do preparo pelo primeiro marco disponível, e qual foi."""
    starts = [
        _parse(record.get("at"))
        for record in ((order.data or {}).get("kds_started") or {}).values()
        if isinstance(record, dict)
    ]
    starts = [moment for moment in starts if moment is not None]
    if starts:
        return min(starts), "kds"
    if order.preparing_at:
        return order.preparing_at, "preparing"
    if order.accepted_at:
        return order.accepted_at, "accepted"
    return order.created_at, "created"


def _call_in_flight(order: Order) -> bool:
    """O pedido tem corrida viva, ou uma chamada que ainda não respondeu."""
    from shopman.shop.directives import COURIER_DISPATCH
    from shopman.shop.services import courier

    block = (order.data or {}).get("courier")
    if not isinstance(block, dict) or not any(block.get(key) for key in ("called_at", "ride_ref", "attempts", "error")):
        # Nunca chamado: nada em voo, e o quadro não paga consulta por cartão.
        return False
    if courier.has_active_ride(order):
        return True
    if courier.unresolved_dispatch(order) is not None:
        return True
    from shopman.orderman.models import Directive

    return Directive.objects.filter(
        courier.dispatch_task_filter(order.ref), topic=COURIER_DISPATCH,
        status__in=(Directive.Status.QUEUED, Directive.Status.RUNNING),
    ).exists()


def _last_failed_ride_end(order: Order) -> datetime | None:
    """Quando terminou a última corrida que não entregou (ninguém atendeu ou cancelada), se houve."""
    block = (order.data or {}).get("courier")
    attempts = block.get("attempts") if isinstance(block, dict) else None
    ends = [
        _parse(attempt.get("ended_at"))
        for attempt in attempts or []
        if isinstance(attempt, dict)
        and delivery_services.ride_state(attempt) in (RideState.NOT_SERVED, RideState.CANCELLED)
    ]
    ends = [moment for moment in ends if moment is not None]
    return max(ends) if ends else None


def courier_reminder(order: Order, *, config: tuple[bool, int] | None = None) -> CourierReminderProjection | None:
    """O lembrete deste pedido, ou ``None`` quando não cabe."""
    if order.status not in REMINDER_STATUSES:
        return None
    enabled, minutes = config if config is not None else reminder_config()
    if not enabled:
        return None
    from shopman.shop.services import courier

    # Entrega da casa com a central configurada: sem o botão, o lembrete não teria
    # gesto. iFood (``delivered_by=IFOOD`` ou não informado) fica de fora.
    if not courier.is_enabled_for(order):
        return None
    if _call_in_flight(order):
        return None
    failed_end = _last_failed_ride_end(order)
    dismissed = (order.data or {}).get("courier_reminder")
    dismissed_at = _parse(dismissed.get("dismissed_at")) if isinstance(dismissed, dict) else None
    if dismissed_at is not None and (failed_end is None or dismissed_at >= failed_end):
        # Dispensado, e nenhuma corrida falhou depois disso.
        return None
    since, basis = prep_started_at(order)
    if since is None:
        return None
    from shopman.shop.services.operator_orders import short_ref

    due_at = since + timedelta(minutes=minutes)
    if failed_end is not None:
        due_at = max(due_at, failed_end + timedelta(minutes=AFTER_FAILED_RIDE_MINUTES))
    return CourierReminderProjection(
        due_at_iso=due_at.isoformat(),
        since_iso=since.isoformat(),
        since_basis=basis,
        short_ref=short_ref(order.ref),
        stage="retry" if failed_end is not None else "ready" if order.status == Order.Status.READY else "preparing",
    )


def dismiss(order: Order, *, actor: str) -> None:
    """Dispensa o lembrete deste pedido, para todos os dispositivos. Idempotente."""
    from shopman.shop.services.order_helpers import merge_order_data

    current = (order.data or {}).get("courier_reminder")
    if isinstance(current, dict) and current.get("dismissed_at"):
        return
    merge_order_data(order, {"dismissed_at": timezone.now().isoformat(), "dismissed_by": actor}, block="courier_reminder")
    order.emit_event(event_type="courier_reminder_dismissed", actor=actor)


__all__ = [
    "AFTER_FAILED_RIDE_MINUTES",
    "DEFAULT_MINUTES",
    "CourierReminderProjection",
    "courier_reminder",
    "dismiss",
    "prep_started_at",
    "reminder_config",
]
