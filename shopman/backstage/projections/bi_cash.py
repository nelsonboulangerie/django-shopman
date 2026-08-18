"""B.I. de caixa — leitura analítica (ADR-021, BI-PLAN §5/F4), sobre o livro.

Tendência de quebra de caixa por dia e por operador (a diferença de cada turno
fechado, provada pelo livro do ``cashman``: ``count`` + correções), sangrias e
suprimentos (linhas ``cash_out``/``cash_in``) e o mix de meios de pagamento
consolidado pelo fechamento (``DayClosing.data.cash_shift_summary.payment_method_totals``
— consumo registrado em docs/reference/data-schemas.md). Dias da janela sem
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


def build_bi_cash(
    *, date_from: date | None = None, date_to: date | None = None
) -> BICashReport:
    from shopman.cashman.models import Shift

    from shopman.backstage.models import DayClosing

    from .bi_production import _normalize_window

    date_from, date_to = _normalize_window(date_from, date_to)

    shifts = list(
        Shift.objects.filter(
            status=Shift.Status.CLOSED,
            closed_at__date__range=(date_from, date_to),
        ).select_related("operator")
    )
    difference_by_shift = _difference_by_shift([shift.pk for shift in shifts])

    day_shifts: dict[date, int] = defaultdict(int)
    day_difference: dict[date, int] = defaultdict(int)
    operator_shifts: dict[str, int] = defaultdict(int)
    operator_difference: dict[str, int] = defaultdict(int)
    for shift in shifts:
        day = timezone.localtime(shift.closed_at).date()
        difference_q = difference_by_shift.get(shift.pk, 0)
        day_shifts[day] += 1
        day_difference[day] += difference_q
        operator = shift.operator.get_username()
        operator_shifts[operator] += 1
        operator_difference[operator] += difference_q

    day_movements = _movements_by_day(date_from, date_to)

    days = []
    day = date_from
    while day <= date_to:
        days.append(
            BICashDay(
                date=day.isoformat(),
                shifts=day_shifts.get(day, 0),
                difference_q=day_difference.get(day, 0),
                sangria_q=day_movements.get(day, {}).get("cash_out", 0),
                suprimento_q=day_movements.get(day, {}).get("cash_in", 0),
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
        previous=_cash_previous(date_from, date_to),
    )


def _cash_previous(date_from: date, date_to: date) -> BICashPrevious:
    from shopman.cashman.models import Shift

    from .bi_production import _previous_window

    prev_from, prev_to = _previous_window(date_from, date_to)
    day_difference: dict[date, int] = defaultdict(int)
    shifts_total = 0
    shifts = list(
        Shift.objects.filter(
            status=Shift.Status.CLOSED,
            closed_at__date__range=(prev_from, prev_to),
        ).values_list("pk", "closed_at")
    )
    difference_by_shift = _difference_by_shift([pk for pk, _ in shifts])
    for pk, closed_at in shifts:
        day_difference[timezone.localtime(closed_at).date()] += difference_by_shift.get(pk, 0)
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


def _difference_by_shift(shift_ids: list[int]) -> dict[int, int]:
    """Diferença vigente de cada turno: ``Σ count + Σ count_correction``, do livro.

    Uma consulta agrupada em vez de ``cashman.services.difference`` por turno:
    a janela do B.I. pode ter centenas de turnos, e é a mesma soma que o
    pacote define — só que em lote.
    """
    from django.db.models import Sum
    from shopman.cashman.models import Entry

    if not shift_ids:
        return {}
    rows = (
        Entry.objects.filter(shift_id__in=shift_ids, kind__in=[Entry.Kind.COUNT, Entry.Kind.COUNT_CORRECTION])
        .values("shift_id")
        .annotate(total=Sum("amount_q"))
    )
    return {int(row["shift_id"]): int(row["total"] or 0) for row in rows}


def _movements_by_day(date_from: date, date_to: date) -> dict[date, dict[str, int]]:
    """Sangria e suprimento por dia, em valor absoluto (o sinal já é o tipo)."""
    from shopman.cashman.models import Entry

    day_movements: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    movements = Entry.objects.filter(
        kind__in=[Entry.Kind.CASH_OUT, Entry.Kind.CASH_IN],
        at__date__range=(date_from, date_to),
    ).values_list("at", "kind", "amount_q")
    for at, kind, amount_q in movements:
        day_movements[timezone.localtime(at).date()][kind] += abs(int(amount_q))
    return day_movements
