"""Quando o pedido na Cozinha deve ficar pronto (G10; página do entregador, #2647).

Uma leitura só para quem precisa da hora prevista de pronto: a Fila do Gestor
("Na Cozinha · próximo pronto em ~4 min", ``order_queue``) e a página do entregador
da casa ("Fica pronto às 12h48", ``own_fleet._stop_view``). O tempo é a mediana dos
preparos reais das últimas horas ou, sem amostra, a meta da estação do canal
(``fulfillment.stage_goal_minutes``, com os padrões do dono em ``STAGE_GOAL_DEFAULTS``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.config import STAGE_GOAL_DEFAULTS

#: Janela dos preparos reais que medem o tempo da Cozinha agora.
PREP_SAMPLE_HOURS = 3
#: Abaixo disto a mediana não diz nada: vale a meta da estação.
PREP_MIN_SAMPLES = 3


def stage_minutes(stage: str, channel_config=None) -> int:
    """A meta, em minutos, da etapa ``stage`` no canal; sem meta válida, o padrão do dono."""
    goals = channel_config.fulfillment.stage_goal_minutes if channel_config is not None else {}
    value = goals.get(stage) if isinstance(goals, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return STAGE_GOAL_DEFAULTS[stage]
    return value


@dataclass(frozen=True)
class PrepExpectation:
    """Quanto um preparo está levando agora: a mediana real ou, sem amostra, a meta."""

    #: Minutos medidos (mediana de ``preparing_at`` → ``ready_at``); ``None`` sem amostra.
    minutes: float | None
    samples: int

    @property
    def basis(self) -> str:
        if self.minutes is None:
            return "pela meta da estação (sem preparos suficientes nas últimas 3 horas)"
        return f"pela mediana de {self.samples} preparos nas últimas {PREP_SAMPLE_HOURS} horas"


def prep_expectation(*, now: datetime) -> PrepExpectation:
    """A mediana dos preparos que terminaram nas últimas horas (uma consulta)."""
    since = now - timedelta(hours=PREP_SAMPLE_HOURS)
    rows = Order.objects.filter(
        ready_at__gte=since, ready_at__lte=now, preparing_at__isnull=False,
    ).order_by("-ready_at").values_list("preparing_at", "ready_at")[:60]
    minutes = sorted((ready - start).total_seconds() / 60 for start, ready in rows if ready > start)
    if len(minutes) < PREP_MIN_SAMPLES:
        return PrepExpectation(minutes=None, samples=len(minutes))
    middle = len(minutes) // 2
    median = minutes[middle] if len(minutes) % 2 else (minutes[middle - 1] + minutes[middle]) / 2
    return PrepExpectation(minutes=median, samples=len(minutes))


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


def ready_eta(order: Order, expectation: PrepExpectation, channel_config=None, *, now: datetime) -> datetime | None:
    """Quando o pedido na Cozinha deve ficar pronto: o início real mais o tempo de agora.

    O início é o primeiro "Iniciar" do KDS (``Order.data["kds_started"]``) ou o
    ``preparing_at``; o tempo é a mediana real (``prep_expectation``) ou a meta da
    estação do canal. Pedido que ainda não começou não fica pronto antes de começar:
    conta a partir de agora.
    """
    if order.status not in (Order.Status.ACCEPTED, Order.Status.PREPARING):
        return None
    expected = expectation.minutes if expectation.minutes is not None else stage_minutes("station", channel_config)
    starts = []
    for record in ((order.data or {}).get("kds_started") or {}).values():
        at = _parse(record.get("at")) if isinstance(record, dict) else None
        if at is not None:
            starts.append(at)
    start = min(starts) if starts else order.preparing_at
    if start is None:
        # Ainda não começou e tem hora combinada: fica pronto na hora combinada,
        # não daqui a um preparo (a retirada das 18h não é "próximo pronto em ~4 min").
        from shopman.shop.services.fulfillment_window import promised_at

        promised = promised_at(order)
        ready = now + timedelta(minutes=expected)
        return max(ready, promised) if promised is not None else ready
    return start + timedelta(minutes=expected)
