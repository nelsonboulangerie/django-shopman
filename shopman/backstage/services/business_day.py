"""Carimba o expediente realmente praticado em cada dia.

O horário da loja é **configuração viva**: muda quando a casa decide mudar, e
feriados e férias coletivas entram e saem do calendário. Ler o horário de hoje
para interpretar um dia de três meses atrás reescreve o passado — a métrica de
ontem mudaria de valor porque alguém mexeu no cadastro hoje.

Por isso o expediente de cada dia é **congelado** no contexto do dia, e é ele
que serve de denominador para qualquer métrica de tempo ("quanto do expediente
o produto ficou sem poder ser vendido"). Dia sem carimbo fica **nulo**, não
zero: não sabemos, e uma proporção sem denominador conhecido não é calculada.

Carimbar é idempotente e só olha para trás: o dia de hoje ainda não terminou, e
carimbá-lo antes da hora congelaria um expediente que ainda vai acontecer.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def stamp_day(day: date) -> dict:
    """Congela o expediente de ``day`` no contexto do dia. Idempotente."""
    from shopman.backstage.models import DayContext
    from shopman.shop.services.business_calendar import (
        _closed_dates,
        _load_shop,
        closed_date_for,
        selling_hours_for,
    )

    shop = _load_shop(None)
    closed, label, _ = closed_date_for(day, _closed_dates(shop)) if shop else (False, "", "")
    window = None if closed else selling_hours_for(day, shop=shop)

    if window is None:
        values = {
            "open_minutes": 0,
            "opens_at": None,
            "closes_at": None,
            "closed_reason": label or ("feriado ou férias" if closed else "sem expediente"),
        }
    else:
        opens_at, closes_at = window
        values = {
            "open_minutes": _minutes_between(opens_at, closes_at),
            "opens_at": opens_at,
            "closes_at": closes_at,
            "closed_reason": "",
        }

    context, _ = DayContext.objects.get_or_create(date=day)
    for field, value in values.items():
        setattr(context, field, value)
    context.sources = {**(context.sources or {}), "business_day": "calendario"}
    context.save()
    return values


def stamp_recent_days(*, days: int = 7) -> int:
    """Carimba os últimos ``days`` dias fechados (nunca o de hoje).

    Roda no ciclo de manutenção: pega o dia que acabou e, de quebra, preenche
    lacunas recentes se o worker ficou parado.
    """
    today = timezone.localdate()
    stamped = 0
    for offset in range(1, days + 1):
        try:
            stamp_day(today - timedelta(days=offset))
            stamped += 1
        except Exception:
            logger.debug("stamp_day falhou", exc_info=True)
    return stamped


def open_minutes_for(day: date) -> int | None:
    """Minutos de expediente do dia, do carimbo. ``None`` = não sabemos."""
    from shopman.backstage.models import DayContext

    return (
        DayContext.objects.filter(date=day)
        .values_list("open_minutes", flat=True)
        .first()
    )


def _minutes_between(opens_at, closes_at) -> int:
    base = date(2000, 1, 1)
    delta = datetime.combine(base, closes_at) - datetime.combine(base, opens_at)
    return max(0, int(delta.total_seconds() // 60))
