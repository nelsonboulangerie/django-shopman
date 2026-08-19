"""Lotação do salão, medida sem pedir gesto novo a ninguém.

Duas peças que a casa já tinha, juntadas:

- **a comanda mede o tempo.** "Sempre abrimos comanda. Ponto." (dono, 17/08) —
  então ``Session.opened_at`` → ``committed_at`` é duração medida, não estimada.
  ⚠️ A janela é a **comanda**, não o tempo sentado: abre no pedido e fecha no
  pagamento, então inclui o tempo em pé no balcão. A tela chama pelo nome.
- **o modo de consumo diz quem sentou.** A cesta classifica a venda
  (``services/consumption``), e só consumo local ocupa lugar. Comanda de quem
  levou também abre — e some sozinha da conta, sem filtro especial.

O denominador de tempo é o expediente CONGELADO do dia
(``DayContext.open_minutes``, rodada 6): dia sem carimbo não entra, porque sem
saber quando a casa esteve aberta, contar ocupação seria inventar a conta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.utils import timezone

EMPTY = "empty"
LIGHT = "light"
BUSY = "busy"
FULL = "full"

LOAD_LABELS: dict[str, str] = {
    EMPTY: "Vazio",
    LIGHT: "Até a metade",
    BUSY: "Cheio",
    FULL: "No teto",
}
LOAD_ORDER = (EMPTY, LIGHT, BUSY, FULL)


def load_band(groups: int, capacity: int) -> str:
    """Faixa grossa de lotação — nunca porcentagem com decimal.

    A capacidade oficial da casa não é limite duro (o sofá aperta, o bistrô e o
    bancão existem fora da conta). Numerador preciso sobre denominador elástico
    é falsa precisão: o que a faixa preserva é a leitura que decide — sobra
    lugar, está cheio, ou bateu no teto.
    """
    if groups <= 0:
        return EMPTY
    if capacity <= 0:
        return BUSY  # há gente sentada e nenhum lugar cadastrado: não é "vazio"
    if groups >= capacity:
        return FULL
    return LIGHT if groups * 2 <= capacity else BUSY


@dataclass(frozen=True)
class RoomDay:
    """O que se sabe do salão num dia."""

    day: date
    capacity: int
    open_minutes: int
    minutes_by_band_hour: dict[tuple[str, int], float]
    peak_by_hour: dict[int, int]
    peak_groups: int
    groups: int
    revenue_q: int
    tab_minutes: list[float]


def capacity_on(day: date, spots) -> int:
    """Quantos grupos a casa oficialmente comporta naquele dia."""
    return sum(1 for spot in spots if spot.counts_in_capacity and spot.existed_on(day))


def _clip(interval, opens_at: time, closes_at: time, day: date, tz):
    """Recorta um intervalo ao expediente do dia. Fora dele não custa mesa."""
    began, finished = interval
    open_dt = datetime.combine(day, opens_at, tzinfo=tz)
    close_dt = datetime.combine(day, closes_at, tzinfo=tz)
    start = max(began, open_dt)
    end = min(finished, close_dt)
    return (start, end) if end > start else None


def _spread_by_hour(start: datetime, end: datetime):
    """Um trecho de lotação constante, partido nas viradas de hora.

    Sem isso, "que horários sobra mesa" leria um trecho das 9h05 às 11h20 como
    se fosse tudo das 9h — e a faixa de pico apareceria na hora errada.
    """
    cursor = start
    while cursor < end:
        next_hour = (cursor + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        stop = min(next_hour, end)
        yield cursor.hour, (stop - cursor).total_seconds() / 60
        cursor = stop


def sweep_day(intervals, *, day: date, capacity: int, opens_at: time, closes_at: time) -> tuple:
    """(minutos por faixa e hora, pico por hora, pico do dia).

    Varredura por eventos, não minuto a minuto: entre duas mudanças a lotação é
    constante, então basta medir os trechos.
    """
    tz = timezone.get_current_timezone()
    clipped = [c for c in (_clip(i, opens_at, closes_at, day, tz) for i in intervals) if c]

    minutes: dict[tuple[str, int], float] = {}
    peak_by_hour: dict[int, int] = {}
    open_dt = datetime.combine(day, opens_at, tzinfo=tz)
    close_dt = datetime.combine(day, closes_at, tzinfo=tz)

    def record(start: datetime, end: datetime, active: int) -> None:
        band = load_band(active, capacity)
        for hour, span in _spread_by_hour(start, end):
            minutes[(band, hour)] = minutes.get((band, hour), 0.0) + span
            peak_by_hour[hour] = max(peak_by_hour.get(hour, 0), active)

    if not clipped:
        record(open_dt, close_dt, 0)
        return minutes, peak_by_hour, 0

    events: list[tuple] = []
    for start, end in clipped:
        events.append((start, 1))
        events.append((end, -1))
    events.sort()

    peak = 0
    active = 0
    cursor = open_dt
    for moment, delta in events:
        if moment > cursor:
            record(cursor, moment, active)
            cursor = moment
        active += delta
        peak = max(peak, active)
    if close_dt > cursor:
        record(cursor, close_dt, active)
    return minutes, peak_by_hour, peak


def room_days(date_from: date, date_to: date) -> dict[date, RoomDay]:
    """Um retrato do salão por dia, para as métricas do explorador lerem.

    Dia sem expediente carimbado **não aparece** no resultado: é ausência de
    denominador, e inventá-lo faria feriado fechado parecer um dia inteiro de
    salão vazio.
    """
    from shopman.orderman.models import Order, Session

    from shopman.backstage.bi.canonical import read_sales
    from shopman.backstage.models import DayContext, SeatingSpot
    from shopman.backstage.projections.bi_explore import _consumption_modes
    from shopman.backstage.services.consumption import DINE_IN, DINE_IN_TAKEAWAY

    tz = timezone.get_current_timezone()
    window = (
        datetime.combine(date_from, time.min, tzinfo=tz),
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz),
    )
    contexts = {
        context.date: context
        for context in DayContext.objects.filter(date__range=(date_from, date_to))
        if context.open_minutes and context.opens_at and context.closes_at
    }
    if not contexts:
        return {}

    spots = list(SeatingSpot.objects.all())
    # O salão é do pedido nativo (a comanda só existe no Shopman); a canônica
    # traz o modo já classificado pela mesma regra que o explorador usa.
    modes = _consumption_modes(read_sales(date_from, date_to))
    seated = {DINE_IN, DINE_IN_TAKEAWAY}

    # Comanda → pedido: o pedido é quem sabe o modo de consumo e o valor; a
    # sessão é quem sabe o tempo. Nenhum dos dois sozinho responde.
    orders = {
        session_key: (order_id, total_q)
        for session_key, order_id, total_q in Order.objects.filter(
            created_at__range=window, session_key__gt=""
        ).exclude(
            status__in=(Order.Status.CANCELLED, Order.Status.RETURNED)
        ).values_list("session_key", "id", "total_q")
    }

    by_day: dict[date, list] = {}
    revenue: dict[date, int] = {}
    counts: dict[date, int] = {}
    durations: dict[date, list] = {}
    for session_key, opened_at, committed_at in Session.objects.filter(
        handle_type="pos_tab", committed_at__range=window
    ).values_list("session_key", "opened_at", "committed_at"):
        found = orders.get(session_key)
        if found is None:
            continue
        order_id, total_q = found
        if modes.get(("shopman", order_id)) not in seated:
            continue
        began = timezone.localtime(opened_at)
        finished = timezone.localtime(committed_at)
        day = finished.date()
        if day not in contexts:
            continue
        by_day.setdefault(day, []).append((began, finished))
        revenue[day] = revenue.get(day, 0) + (total_q or 0)
        counts[day] = counts.get(day, 0) + 1
        durations.setdefault(day, []).append((finished - began).total_seconds() / 60)

    result: dict[date, RoomDay] = {}
    for day, context in contexts.items():
        capacity = capacity_on(day, spots)
        minutes, peak_by_hour, peak = sweep_day(
            by_day.get(day, []), day=day, capacity=capacity,
            opens_at=context.opens_at, closes_at=context.closes_at,
        )
        result[day] = RoomDay(
            day=day,
            capacity=capacity,
            open_minutes=context.open_minutes,
            minutes_by_band_hour=minutes,
            peak_by_hour=peak_by_hour,
            peak_groups=peak,
            groups=counts.get(day, 0),
            revenue_q=revenue.get(day, 0),
            tab_minutes=durations.get(day, []),
        )
    return result
