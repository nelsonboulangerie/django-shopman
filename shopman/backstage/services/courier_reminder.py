"""Lembrete de chamar o entregador — TEMPORÁRIO, até a chamada antecipada aprender.

X minutos depois do início do preparo de uma entrega da casa (nunca iFood) sem
corrida pedida, o Gestor cobra o operador: "Pedido 0042 em preparo há 10 min. Já
dá para chamar o entregador?", com o botão "Chamar entregador" e o "Dispensar".

É mecanismo independente do automático (WP-ENTREGADOR-CHAMADA-ANTECIPADA): quando
ele chegar, este módulo, a chave ``Shop.defaults["delivery"]["courier_reminder"]``
e o aviso do cartão saem inteiros.

Um aviso por pedido, por construção: o lembrete não é gravado, é LIDO do pedido a
cada leitura do quadro. Some sozinho quando a corrida é pedida
(``Order.data["courier"]["called_at"]`` ou qualquer corrida), quando o pedido sai
do preparo ou quando alguém dispensa (``Order.data["courier_reminder"]``, que vale
para todos os dispositivos).

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

#: Padrão do dono (13/10/2026): 10 minutos depois do início do preparo, ligado.
DEFAULT_MINUTES = 10
MAX_MINUTES = 240


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


def _ride_requested(order: Order) -> bool:
    block = (order.data or {}).get("courier")
    if not isinstance(block, dict):
        return False
    return any(block.get(key) for key in ("called_at", "id_mch", "attempts", "error"))


def courier_reminder(order: Order, *, config: tuple[bool, int] | None = None) -> CourierReminderProjection | None:
    """O lembrete deste pedido, ou ``None`` quando não cabe."""
    if order.status != Order.Status.PREPARING:
        return None
    enabled, minutes = config if config is not None else reminder_config()
    if not enabled:
        return None
    if isinstance((order.data or {}).get("courier_reminder"), dict) and order.data["courier_reminder"].get("dismissed_at"):
        return None
    if _ride_requested(order):
        return None
    from shopman.shop.services import courier

    # Entrega da casa com a central configurada: sem o botão, o lembrete não teria
    # gesto. iFood (``delivered_by=IFOOD`` ou não informado) fica de fora.
    if not courier.is_enabled_for(order):
        return None
    since, basis = prep_started_at(order)
    if since is None:
        return None
    from shopman.shop.services.operator_orders import short_ref

    return CourierReminderProjection(
        due_at_iso=(since + timedelta(minutes=minutes)).isoformat(),
        since_iso=since.isoformat(),
        since_basis=basis,
        short_ref=short_ref(order.ref),
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
    "DEFAULT_MINUTES",
    "CourierReminderProjection",
    "courier_reminder",
    "dismiss",
    "prep_started_at",
    "reminder_config",
]
