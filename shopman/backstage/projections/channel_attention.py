"""Canais que pedem atenção — o indicador da navegação e o aviso da fila de Pedidos.

Estado normal (todo canal ligado, iFood de acordo com a casa) não produz nada. Um
canal desligado sem prazo, pausado por um período ou (iFood) divergente da casa
entra aqui:

* ``count``/``label`` vão para o item "Canais" da navegação do Gestor — canal de
  venda E feed/TV;
* ``queue`` vai para a fila de Pedidos — só canal de VENDA, porque só ele muda o
  que entra na fila. Cada linha leva ao card do canal (``/feeds?focus=<ref>``).

O estado vem do relógio (``channel_switch.effective_active``), não do carimbo do
worker. Agendamento ainda por vir não pede atenção: ele está no card.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone


@dataclass(frozen=True)
class ChannelAttentionItem:
    ref: str
    name: str
    kind: str  # sale | display
    state: str  # off | paused | diverges
    line: str
    focus_path: str


@dataclass(frozen=True)
class ChannelAttentionProjection:
    count: int
    label: str  # "1 desligado", "2 desligados · 1 divergente"; vazio no estado normal
    items: tuple[ChannelAttentionItem, ...] = ()
    queue: tuple[ChannelAttentionItem, ...] = ()
    can_open_channels: bool = False


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _ifood_divergence_line() -> str:
    from shopman.shop.models import IFoodStoreStatus
    from shopman.shop.services import business_calendar, ifood_merchant

    if not ifood_merchant.enabled():
        return ""
    status = IFoodStoreStatus.objects.filter(merchant_id=ifood_merchant.merchant_id()).first()
    if status is None or status.checked_at is None or status.divergent_since is None:
        return ""
    shop_open = business_calendar.current_business_state().is_open
    if not status.available and shop_open:
        return "iFood fechado com a loja aberta: nenhum pedido do iFood entra"
    if status.available and not shop_open:
        return "iFood recebendo pedidos com a loja fechada"
    return "iFood diferente do esperado pela loja"


def build_channel_attention(*, user=None, now: datetime | None = None) -> ChannelAttentionProjection:
    from shopman.shop.models import Channel
    from shopman.shop.services import channel_switch as switches

    now = now or timezone.now()
    items: list[ChannelAttentionItem] = []
    for channel in Channel.objects.order_by("commerce_policy", "display_order", "name"):
        name = channel.name or channel.ref
        sale = channel.commerce_policy == Channel.CommercePolicy.ORDER
        focus = f"/feeds?focus={channel.ref}"
        if not switches.effective_active(channel, now=now):
            record = switches.activation(channel)
            timed = bool(record and not record.is_active and record.ends_at and record.starts_at <= now < record.ends_at)
            reason = f" — {record.reason}" if record and record.reason and not record.auto else ""
            if timed:
                line = f"{name}: pedidos pausados até {switches.moment(record.ends_at, now=now)}{reason}"
            else:
                line = f"{name}: pedidos desligados{reason}"
            items.append(ChannelAttentionItem(
                ref=channel.ref, name=name, kind="sale" if sale else "display",
                state="paused" if timed else "off", line=line, focus_path=focus,
            ))
            continue
        if channel.ref == switches.IFOOD_CHANNEL_REF:
            divergence = _ifood_divergence_line()
            if divergence:
                items.append(ChannelAttentionItem(
                    ref=channel.ref, name=name, kind="sale", state="diverges", line=divergence, focus_path=focus,
                ))

    switched = sum(1 for item in items if item.state in {"off", "paused"})
    diverging = sum(1 for item in items if item.state == "diverges")
    parts = []
    if switched:
        parts.append(_plural(switched, "desligado", "desligados"))
    if diverging:
        parts.append(_plural(diverging, "divergente", "divergentes"))
    return ChannelAttentionProjection(
        count=len(items),
        label=" · ".join(parts),
        items=tuple(items),
        queue=tuple(item for item in items if item.kind == "sale"),
        can_open_channels=bool(user is not None and user.has_perm("shop.manage_catalog")),
    )


__all__ = ["ChannelAttentionItem", "ChannelAttentionProjection", "build_channel_attention"]
