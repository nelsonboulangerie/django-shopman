"""B.I. de caixa — leitura analítica (ADR-021, BI-PLAN §5/F4).

Tendência de quebra de caixa (``difference_q``) por dia e por operador,
sangrias/suprimentos e o mix de meios de pagamento consolidado pelo
fechamento (``DayClosing.data.cash_shift_summary.payment_method_totals`` —
consumo registrado em docs/reference/data-schemas.md). Dias da janela sem
fechamento entram em ``closings_missing``: o buraco é declarado, nunca
silenciado.

O log de eventos do PDV (``POSEvent``) alimenta a parte de comportamento: quem
abre a gaveta sem venda, quantas vezes a trava foi liberada por gerente e
quantas vezes faltou troco, por operador e por hora do dia. É a pergunta que
motivou o log ("quem abre a gaveta 3× mais que os outros?"), e antes não tinha
onde ser feita.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone


@dataclass(frozen=True)
class BICashDay:
    date: str
    shifts: int
    difference_q: int
    sangria_q: int
    suprimento_q: int


@dataclass(frozen=True)
class BICashOperatorRow:
    operator: str
    shifts: int
    difference_q: int
    # Do log de eventos: contagens no período. Zero é zero, não "não sei".
    drawer_openings: int
    drawer_unlocks: int
    change_requests: int


@dataclass(frozen=True)
class BICashHourRow:
    """Uma hora do dia com atividade de gaveta. Só horas com algo aparecem."""

    hour: int
    drawer_openings: int
    drawer_unlocks: int


@dataclass(frozen=True)
class BICashMethodRow:
    method: str
    amount_q: int


@dataclass(frozen=True)
class BICashPrevious:
    """O período de mesmo tamanho imediatamente anterior (F7 — comparação)."""

    date_from: str
    date_to: str
    shifts_total: int
    difference_total_q: int
    difference_by_day: tuple[int, ...]  # alinhado posicionalmente com `days`


@dataclass(frozen=True)
class BICashReport:
    date_from: str
    date_to: str
    days: tuple[BICashDay, ...]
    by_operator: tuple[BICashOperatorRow, ...]
    payment_methods: tuple[BICashMethodRow, ...]
    shifts_total: int
    difference_total_q: int
    closings_missing: int
    previous: BICashPrevious
    drawer_by_hour: tuple[BICashHourRow, ...]


def build_bi_cash(
    *, date_from: date | None = None, date_to: date | None = None
) -> BICashReport:
    from shopman.backstage.models import CashMovement, CashShift, DayClosing, POSEvent

    from .bi_production import _normalize_window

    date_from, date_to = _normalize_window(date_from, date_to)

    shifts = list(
        CashShift.objects.filter(
            status=CashShift.Status.CLOSED,
            closed_at__date__range=(date_from, date_to),
        ).select_related("operator")
    )

    day_shifts: dict[date, int] = defaultdict(int)
    day_difference: dict[date, int] = defaultdict(int)
    operator_shifts: dict[str, int] = defaultdict(int)
    operator_difference: dict[str, int] = defaultdict(int)
    for shift in shifts:
        day = timezone.localtime(shift.closed_at).date()
        day_shifts[day] += 1
        day_difference[day] += shift.difference_q
        operator = shift.operator.get_username()
        operator_shifts[operator] += 1
        operator_difference[operator] += shift.difference_q

    day_movements: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    movements = CashMovement.objects.filter(
        created_at__date__range=(date_from, date_to)
    ).values_list("created_at", "movement_type", "amount_q")
    for created_at, movement_type, amount_q in movements:
        day_movements[timezone.localtime(created_at).date()][movement_type] += amount_q

    days = []
    day = date_from
    while day <= date_to:
        days.append(
            BICashDay(
                date=day.isoformat(),
                shifts=day_shifts.get(day, 0),
                difference_q=day_difference.get(day, 0),
                sangria_q=day_movements.get(day, {}).get("sangria", 0),
                suprimento_q=day_movements.get(day, {}).get("suprimento", 0),
            )
        )
        day += timedelta(days=1)

    method_totals: dict[str, int] = defaultdict(int)
    closings = DayClosing.objects.filter(date__range=(date_from, date_to))
    closed_dates = set()
    for closing in closings:
        closed_dates.add(closing.date)
        data = closing.data if isinstance(closing.data, dict) else {}
        totals = (data.get("cash_shift_summary") or {}).get("payment_method_totals") or {}
        for method, amount in totals.items():
            if method.endswith("_count") or not isinstance(amount, int):
                continue
            method_totals[method] += amount

    # Comportamento de gaveta, do log de eventos. Por operador E por hora, porque
    # "quem" e "quando" são as duas perguntas do gerente. Operador que só tem
    # evento (turno ainda aberto) também entra na tabela — a abertura de gaveta
    # não espera o fechamento para contar.
    Kind = POSEvent.Kind
    counted_kinds = (Kind.DRAWER_OPENED, Kind.DRAWER_UNLOCKED, Kind.CHANGE_REQUESTED)
    operator_events: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    hour_events: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    events = (
        POSEvent.objects.filter(kind__in=counted_kinds, at__date__range=(date_from, date_to))
        .select_related("operator")
        .values_list("at", "kind", "operator__username")
    )
    for at, kind, username in events:
        operator = username or "sistema"
        operator_events[operator][kind] += 1
        if kind != Kind.CHANGE_REQUESTED:
            hour_events[timezone.localtime(at).hour][kind] += 1

    operators = sorted(set(operator_shifts) | set(operator_events))
    window_days = (date_to - date_from).days + 1

    return BICashReport(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        days=tuple(days),
        by_operator=tuple(
            BICashOperatorRow(
                operator=operator,
                shifts=operator_shifts.get(operator, 0),
                difference_q=operator_difference.get(operator, 0),
                drawer_openings=operator_events[operator][Kind.DRAWER_OPENED],
                drawer_unlocks=operator_events[operator][Kind.DRAWER_UNLOCKED],
                change_requests=operator_events[operator][Kind.CHANGE_REQUESTED],
            )
            for operator in operators
        ),
        payment_methods=tuple(
            BICashMethodRow(method=method, amount_q=method_totals[method])
            for method in sorted(method_totals, key=lambda m: -method_totals[m])
        ),
        shifts_total=len(shifts),
        difference_total_q=sum(day_difference.values()),
        closings_missing=window_days - len(closed_dates),
        previous=_cash_previous(date_from, date_to),
        drawer_by_hour=tuple(
            BICashHourRow(
                hour=hour,
                drawer_openings=hour_events[hour][Kind.DRAWER_OPENED],
                drawer_unlocks=hour_events[hour][Kind.DRAWER_UNLOCKED],
            )
            for hour in sorted(hour_events)
        ),
    )


def _cash_previous(date_from: date, date_to: date) -> BICashPrevious:
    from shopman.backstage.models import CashShift

    from .bi_production import _previous_window

    prev_from, prev_to = _previous_window(date_from, date_to)
    day_difference: dict[date, int] = defaultdict(int)
    shifts_total = 0
    shifts = CashShift.objects.filter(
        status=CashShift.Status.CLOSED,
        closed_at__date__range=(prev_from, prev_to),
    ).values_list("closed_at", "difference_q")
    for closed_at, difference_q in shifts:
        day_difference[timezone.localtime(closed_at).date()] += difference_q
        shifts_total += 1

    series = []
    day = prev_from
    while day <= prev_to:
        series.append(day_difference.get(day, 0))
        day += timedelta(days=1)

    return BICashPrevious(
        date_from=prev_from.isoformat(),
        date_to=prev_to.isoformat(),
        shifts_total=shifts_total,
        difference_total_q=sum(day_difference.values()),
        difference_by_day=tuple(series),
    )
