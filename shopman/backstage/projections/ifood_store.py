"""Projeção "a loja no iFood" para o Gestor de pedidos.

O que a tela precisa para o menu de mais opções: a casa está aberta? o iFood
está recebendo pedido (última conferência)? há pausa do gestor em curso, até
quando, por quê e de quem? que durações cabem agora?

Desligado (``IFOOD_MERCHANT_SYNC`` fora), a projeção diz só ``enabled=False`` e
a tela não mostra nada — o horário do iFood segue sendo o do Portal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone

from shopman.shop.services import business_calendar, ifood_merchant

PAUSE_PERMISSION = "shop.pause_ifood"

_PAUSE_LABELS = {
    "30m": "30 minutos",
    "1h": "1 hora",
    "2h": "2 horas",
}


@dataclass(frozen=True)
class IFoodPauseOptionProjection:
    key: str
    label: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True)
class IFoodPauseProjection:
    ref: int
    state: str
    state_label: str
    reason: str
    starts_at: str
    ends_at: str
    ends_at_display: str
    requested_by: str
    requested_at_display: str
    removed_by: str
    error: str


@dataclass(frozen=True)
class IFoodStoreProjection:
    enabled: bool
    governs: bool = False
    can_pause: bool = False
    shop_open: bool = False
    shop_message: str = ""
    ifood_available: bool | None = None
    ifood_status_label: str = ""
    ifood_checked_at_display: str = ""
    ifood_problems: tuple[str, ...] = ()
    diverges: bool = False
    pause: IFoodPauseProjection | None = None
    last_pause: IFoodPauseProjection | None = None
    options: tuple[IFoodPauseOptionProjection, ...] = field(default_factory=tuple)


def _hhmm(value: datetime | None, tz) -> str:
    return timezone.localtime(value, timezone=tz).strftime("%H:%M") if value else ""


def _who(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username() or "").strip()


def _pause(record, tz) -> IFoodPauseProjection:
    return IFoodPauseProjection(
        ref=record.pk,
        state=record.state,
        state_label=record.get_state_display(),
        reason=record.reason,
        starts_at=record.starts_at.isoformat(),
        ends_at=record.ends_at.isoformat(),
        ends_at_display=_hhmm(record.ends_at, tz),
        requested_by=_who(record.requested_by),
        requested_at_display=_hhmm(record.requested_at, tz),
        removed_by=_who(record.removed_by),
        error=record.last_error,
    )


def _options(state, now) -> tuple[IFoodPauseOptionProjection, ...]:
    closed_reason = "" if state.is_open else "A loja já está fechada."
    options = [
        IFoodPauseOptionProjection(key=key, label=label, enabled=state.is_open, reason=closed_reason)
        for key, label in _PAUSE_LABELS.items()
    ]
    until_close = ifood_merchant.pause_end_for(ifood_merchant.PAUSE_UNTIL_CLOSE, now=now, state=state)
    closes = state.closes_at.replace(":00", "h").replace(":", "h") if state.closes_at else ""
    options.append(
        IFoodPauseOptionProjection(
            key=ifood_merchant.PAUSE_UNTIL_CLOSE,
            label=f"Até o fim do expediente ({closes})" if closes else "Até o fim do expediente",
            enabled=until_close is not None,
            reason="" if until_close is not None else (closed_reason or "Hoje não há expediente declarado."),
        )
    )
    return tuple(options)


def build_ifood_store_projection(*, user=None, now: datetime | None = None) -> IFoodStoreProjection:
    if not ifood_merchant.enabled():
        return IFoodStoreProjection(enabled=False)

    from shopman.shop.models import IFoodInterruptionState, IFoodStoreStatus

    now = now or timezone.now()
    tz = business_calendar.shop_timezone()
    state = business_calendar.current_business_state(now=now)
    can_pause = bool(user is not None and user.has_perm(PAUSE_PERMISSION))

    status = IFoodStoreStatus.objects.filter(merchant_id=ifood_merchant.merchant_id()).first()
    checked = status is not None and status.checked_at is not None
    if not checked:
        status_label = "Ainda sem conferência com o iFood"
    elif status.available:
        status_label = "Recebendo pedidos"
    else:
        status_label = "Fechado para pedidos"

    live = ifood_merchant.live_manual_pause(now=now)
    last = None
    if live is None:
        candidate = ifood_merchant.last_manual_pause()
        # Só a recusa do iFood merece ficar na tela depois de acabada: é a pausa
        # que o gestor pediu e que não aconteceu.
        if candidate is not None and candidate.state == IFoodInterruptionState.FAILED:
            last = candidate

    return IFoodStoreProjection(
        enabled=True,
        governs=ifood_merchant.governs(),
        can_pause=can_pause,
        shop_open=state.is_open,
        shop_message=state.message or ("Aberta" if state.is_open else "Fechada"),
        ifood_available=status.available if checked else None,
        ifood_status_label=status_label,
        ifood_checked_at_display=_hhmm(status.checked_at, tz) if checked else "",
        ifood_problems=tuple(ifood_merchant.problem_copy(status.problems or [])) if checked else (),
        diverges=bool(checked and status.divergent_since is not None),
        pause=_pause(live, tz) if live is not None else None,
        last_pause=_pause(last, tz) if last is not None else None,
        options=_options(state, now) if can_pause else (),
    )


__all__ = [
    "IFoodPauseOptionProjection",
    "IFoodPauseProjection",
    "IFoodStoreProjection",
    "PAUSE_PERMISSION",
    "build_ifood_store_projection",
]
