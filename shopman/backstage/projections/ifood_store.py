"""Projeção "a loja no iFood" para o Gestor de pedidos.

O que o card do canal iFood (aba Canais) e o sinal da fila precisam: a casa está
aberta? o iFood está recebendo pedido (última conferência)? ele diverge da casa,
e por quê? O controle (ligar/desligar, com período) é o toggle "Ativo" do card,
comum a todos os canais — ver ``shopman.shop.services.channel_switch``.

Desligado (``IFOOD_MERCHANT_SYNC`` fora), a projeção diz só ``enabled=False`` e
a tela não mostra nada — o horário do iFood segue sendo o do Portal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from shopman.shop.services import business_calendar, ifood_merchant


@dataclass(frozen=True)
class IFoodStoreProjection:
    enabled: bool
    governs: bool = False
    # Canal iFood desligado no Gestor (toggle "Ativo" do card): fechado pelo período.
    channel_off: bool = False
    shop_open: bool = False
    shop_message: str = ""
    ifood_available: bool | None = None
    ifood_status_label: str = ""
    ifood_checked_at_display: str = ""
    ifood_problems: tuple[str, ...] = ()
    diverges: bool = False


def _hhmm(value: datetime | None, tz) -> str:
    return timezone.localtime(value, timezone=tz).strftime("%H:%M") if value else ""


def build_ifood_store_projection(*, user=None, now: datetime | None = None) -> IFoodStoreProjection:
    if not ifood_merchant.enabled():
        return IFoodStoreProjection(enabled=False)

    from shopman.shop.models import IFoodStoreStatus

    now = now or timezone.now()
    tz = business_calendar.shop_timezone()
    state = business_calendar.current_business_state(now=now)

    status = IFoodStoreStatus.objects.filter(merchant_id=ifood_merchant.merchant_id()).first()
    checked = status is not None and status.checked_at is not None
    if not checked:
        status_label = "Ainda sem conferência com o iFood"
    elif status.available:
        status_label = "Recebendo pedidos"
    else:
        status_label = "Fechado para pedidos"

    return IFoodStoreProjection(
        enabled=True,
        governs=ifood_merchant.governs(),
        channel_off=ifood_merchant.channel_off(now=now),
        shop_open=state.is_open,
        shop_message=state.message or ("Aberta" if state.is_open else "Fechada"),
        ifood_available=status.available if checked else None,
        ifood_status_label=status_label,
        ifood_checked_at_display=_hhmm(status.checked_at, tz) if checked else "",
        ifood_problems=tuple(ifood_merchant.problem_copy(status.problems or [])) if checked else (),
        diverges=bool(checked and status.divergent_since is not None),
    )


__all__ = [
    "IFoodStoreProjection",
    "build_ifood_store_projection",
]
