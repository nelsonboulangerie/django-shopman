"""B.I. de caixa — leitura analítica (ADR-021, BI-PLAN §5/F4).

Tendência de quebra de caixa (``difference_q``) por dia e por operador,
sangrias/suprimentos e o mix de meios de pagamento consolidado pelo
fechamento (``DayClosing.data.cash_shift_summary.payment_method_totals`` —
consumo registrado em docs/reference/data-schemas.md). Dias da janela sem
fechamento entram em ``closings_missing``: o buraco é declarado, nunca
silenciado.
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


@dataclass(frozen=True)
class BICashMethodRow:
    method: str
    amount_q: int


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


def build_bi_cash(
    *, date_from: date | None = None, date_to: date | None = None
) -> BICashReport:
    from shopman.backstage.models import CashMovement, CashShift, DayClosing

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

    window_days = (date_to - date_from).days + 1

    return BICashReport(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        days=tuple(days),
        by_operator=tuple(
            BICashOperatorRow(
                operator=operator,
                shifts=operator_shifts[operator],
                difference_q=operator_difference[operator],
            )
            for operator in sorted(operator_shifts)
        ),
        payment_methods=tuple(
            BICashMethodRow(method=method, amount_q=method_totals[method])
            for method in sorted(method_totals, key=lambda m: -method_totals[m])
        ),
        shifts_total=len(shifts),
        difference_total_q=sum(day_difference.values()),
        closings_missing=window_days - len(closed_dates),
    )
