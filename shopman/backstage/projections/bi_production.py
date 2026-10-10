"""B.I. de produção — leitura analítica (ADR-021, BI-PLAN §5/F3).

Responde perguntas de TENDÊNCIA (série diária de aproveitamento/perda/qualidade e
tempo real de forno), não perguntas do turno — essas seguem nas projections
operacionais (`build_production_reports`, `build_qc_kiosk`). Tudo calculado na
leitura (ADR-021 §3): nenhuma tabela de agregação; janela limitada por default.

Honestidade da métrica: o tempo de forno só existe onde o par armar→Concluir
foi declarado, e o relatório carrega a COBERTURA (fornadas medidas ÷ fornadas
fechadas) em vez de fingir completude.

Aproveitamento e perda seguem o vocabulário do lote (UX-PROD-AF): a base é o
PREVISTO (``started_qty``, o que entrou em produção), nunca o planejado.
Aproveitamento = realizado ÷ previsto; perda = previsto − realizado, por lote
(a mesma conta de ``WorkOrder.loss``/``WorkOrder.yield_rate`` do Craftsman).
Lote fechado sem abertura declarada tem o previsto assumido igual ao
planejado, e o relatório CONTA esses lotes (``batches_started_assumed``) em vez
de apresentá-los como declarados.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

from .production import _wo_started_assumed, _wo_started_qty

# Janela default e teto. O teto cobre o histórico inteiro da casa (Yooga
# começa em jul/2024) — a leitura segue on-the-fly; se a janela máxima um dia
# passar do p95 de 2s, é o gatilho de materialização da ADR-021 §3.
DEFAULT_WINDOW_DAYS = 28
MAX_WINDOW_DAYS = 1830


@dataclass(frozen=True)
class BIOvenTimeRow:
    """Tempo de forno agregado por receita ou por forno."""

    ref: str
    label: str
    runs: int
    avg_minutes: str
    p50_minutes: str
    p90_minutes: str
    avg_planned_minutes: str


@dataclass(frozen=True)
class BIProductionDay:
    """Um dia da série: produção fechada e o mix comercial da qualidade."""

    date: str
    planned: str
    #: Previsto: o que entrou em produção (``started_qty``), base do aproveitamento.
    started: str
    finished: str
    #: Perda = previsto − realizado, somada lote a lote.
    loss: str
    #: Aproveitamento = realizado ÷ previsto, em %.
    yield_percent: int | None
    full_price: str
    discounted: str


@dataclass(frozen=True)
class BIProductionPrevious:
    """O período de mesmo tamanho imediatamente anterior (F7 — comparação)."""

    date_from: str
    date_to: str
    batches_finished: int
    started_total: str
    finished_total: str
    loss_total: str
    finished_by_day: tuple[str, ...]  # alinhado posicionalmente com `days`


@dataclass(frozen=True)
class BIProductionReport:
    date_from: str
    date_to: str
    days: tuple[BIProductionDay, ...]
    oven_time_by_recipe: tuple[BIOvenTimeRow, ...]
    oven_time_by_oven: tuple[BIOvenTimeRow, ...]
    batches_finished: int
    #: Lotes fechados sem abertura declarada: previsto assumido igual ao planejado.
    batches_started_assumed: int
    batches_measured: int
    oven_coverage_percent: int
    previous: BIProductionPrevious


def build_bi_production(
    *, date_from: date | None = None, date_to: date | None = None
) -> BIProductionReport:
    from shopman.craftsman.models import WorkOrder

    from shopman.backstage.models import OvenRun

    date_from, date_to = _normalize_window(date_from, date_to)

    work_orders = list(
        _with_started_events(
            WorkOrder.objects.filter(
                target_date__range=(date_from, date_to),
                status=WorkOrder.Status.FINISHED,
            ).select_related("recipe")
        )
    )

    days = _daily_series(work_orders, date_from=date_from, date_to=date_to)

    runs = _measured_runs(date_from=date_from, date_to=date_to, oven_run_model=OvenRun)
    wo_by_ref = {wo.ref: wo for wo in work_orders}
    measured_refs = {run.work_order_ref for run in runs}
    batches_finished = len(work_orders)
    batches_measured = sum(1 for ref in wo_by_ref if ref in measured_refs)

    quality_by_day = _quality_mix_by_day(work_orders=work_orders)
    days = tuple(
        BIProductionDay(
            date=day.date,
            planned=day.planned,
            started=day.started,
            finished=day.finished,
            loss=day.loss,
            yield_percent=day.yield_percent,
            full_price=_qty(quality_by_day.get(day.date, {}).get("full_price", Decimal(0))),
            discounted=_qty(quality_by_day.get(day.date, {}).get("discounted", Decimal(0))),
        )
        for day in days
    )

    return BIProductionReport(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        days=days,
        oven_time_by_recipe=_oven_rows(runs, wo_by_ref, group="recipe"),
        oven_time_by_oven=_oven_rows(runs, wo_by_ref, group="oven"),
        batches_finished=batches_finished,
        batches_started_assumed=sum(1 for wo in work_orders if _wo_started_assumed(wo)),
        batches_measured=batches_measured,
        oven_coverage_percent=(
            round(batches_measured * 100 / batches_finished) if batches_finished else 0
        ),
        previous=_production_previous(date_from, date_to),
    )


def _production_previous(date_from: date, date_to: date) -> BIProductionPrevious:
    from shopman.craftsman.models import WorkOrder

    prev_from, prev_to = _previous_window(date_from, date_to)
    work_orders = list(
        _with_started_events(
            WorkOrder.objects.filter(
                target_date__range=(prev_from, prev_to),
                status=WorkOrder.Status.FINISHED,
            )
        )
    )
    finished_by_day: dict[date, Decimal] = defaultdict(Decimal)
    started_total = Decimal(0)
    finished_total = Decimal(0)
    loss_total = Decimal(0)
    for wo in work_orders:
        started, finished, loss = batch_outcome(wo)
        finished_by_day[wo.target_date] += finished
        started_total += started
        finished_total += finished
        loss_total += loss

    series = []
    day = prev_from
    while day <= prev_to:
        series.append(_qty(finished_by_day.get(day, Decimal(0))))
        day += timedelta(days=1)

    return BIProductionPrevious(
        date_from=prev_from.isoformat(),
        date_to=prev_to.isoformat(),
        batches_finished=len(work_orders),
        started_total=_qty(started_total),
        finished_total=_qty(finished_total),
        loss_total=_qty(loss_total),
        finished_by_day=tuple(series),
    )


# ── Janela ───────────────────────────────────────────────────────────────────


def _previous_window(date_from: date, date_to: date) -> tuple[date, date]:
    """O período de MESMO tamanho imediatamente anterior (F7 — comparação)."""
    length = (date_to - date_from).days + 1
    return date_from - timedelta(days=length), date_from - timedelta(days=1)


def _normalize_window(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = timezone.localdate()
    date_to = date_to or today
    date_from = date_from or date_to - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    if (date_to - date_from).days >= MAX_WINDOW_DAYS:
        date_from = date_to - timedelta(days=MAX_WINDOW_DAYS - 1)
    return date_from, date_to


# ── Série diária ─────────────────────────────────────────────────────────────


def _with_started_events(work_orders):
    """Prefetch dos eventos de abertura: o previsto sem uma consulta por lote."""
    from django.db.models import Prefetch
    from shopman.craftsman.models import WorkOrderEvent

    return work_orders.prefetch_related(
        Prefetch("events", queryset=WorkOrderEvent.objects.filter(kind=WorkOrderEvent.Kind.STARTED))
    )


def batch_outcome(wo) -> tuple[Decimal, Decimal, Decimal]:
    """``(previsto, realizado, perda)`` de um lote fechado.

    Mesma conta de ``WorkOrder.loss``/``WorkOrder.yield_rate`` (Craftsman):
    previsto = quantidade da abertura (ou o planejado, quando ninguém a
    declarou); perda = previsto − realizado, nunca negativa.
    """
    started = _wo_started_qty(wo) or wo.quantity or Decimal(0)
    finished = wo.finished or Decimal(0)
    return started, finished, max(Decimal(0), started - finished)


def _daily_series(work_orders, *, date_from: date, date_to: date) -> tuple[BIProductionDay, ...]:
    planned_by_day: dict[date, Decimal] = defaultdict(Decimal)
    started_by_day: dict[date, Decimal] = defaultdict(Decimal)
    finished_by_day: dict[date, Decimal] = defaultdict(Decimal)
    loss_by_day: dict[date, Decimal] = defaultdict(Decimal)
    for wo in work_orders:
        started, finished, loss = batch_outcome(wo)
        planned_by_day[wo.target_date] += wo.quantity
        started_by_day[wo.target_date] += started
        finished_by_day[wo.target_date] += finished
        loss_by_day[wo.target_date] += loss

    days = []
    day = date_from
    while day <= date_to:
        planned = planned_by_day.get(day, Decimal(0))
        started = started_by_day.get(day, Decimal(0))
        finished = finished_by_day.get(day, Decimal(0))
        days.append(
            BIProductionDay(
                date=day.isoformat(),
                planned=_qty(planned),
                started=_qty(started),
                finished=_qty(finished),
                loss=_qty(loss_by_day.get(day, Decimal(0))),
                yield_percent=round(finished * 100 / started) if started else None,
                full_price="0",
                discounted="0",
            )
        )
        day += timedelta(days=1)
    return tuple(days)


def _quality_mix_by_day(*, work_orders):
    """Effective OUTPUT by day, split by the lot's frozen commercial markdown."""
    from shopman.shop.services import quality as quality_service

    partitions = quality_service.effective_partitions(work_orders, include_loss=False)
    mix: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for work_order in work_orders:
        for group in partitions.get(work_order.pk, []):
            quantity = Decimal(str(group.get("quantity") or "0"))
            bucket = "discounted" if int(group.get("markdown_percent") or 0) else "full_price"
            mix[work_order.target_date.isoformat()][bucket] += quantity
    return mix


# ── Tempo de forno ───────────────────────────────────────────────────────────


def _measured_runs(*, date_from: date, date_to: date, oven_run_model):
    tz = timezone.get_current_timezone()
    start = datetime.combine(date_from, time.min, tzinfo=tz)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)
    return list(
        oven_run_model.objects.filter(
            status="concluded", armed_at__gte=start, armed_at__lt=end
        )
    )


def _oven_rows(runs, wo_by_ref, *, group: str) -> tuple[BIOvenTimeRow, ...]:
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for run in runs:
        wo = wo_by_ref.get(run.work_order_ref)
        if group == "recipe":
            if wo is None:
                continue  # run de fornada fora da janela/estado; sem receita não agrega
            key = (wo.recipe.ref, wo.recipe.name)
        else:
            oven = run.oven_ref or ""
            if not oven:
                continue  # sem forno atribuído: a cobertura já declara o buraco
            key = (oven, oven)
        grouped[key].append(run)

    rows = []
    for (ref, label), group_runs in sorted(grouped.items()):
        elapsed = sorted(run.elapsed_seconds for run in group_runs)
        planned = [run.planned_seconds for run in group_runs]
        rows.append(
            BIOvenTimeRow(
                ref=ref,
                label=label,
                runs=len(group_runs),
                avg_minutes=_minutes(sum(elapsed) / len(elapsed)),
                p50_minutes=_minutes(_percentile(elapsed, 50)),
                p90_minutes=_minutes(_percentile(elapsed, 90)),
                avg_planned_minutes=_minutes(sum(planned) / len(planned)),
            )
        )
    return tuple(rows)


def _percentile(sorted_values, pct: int):
    """Percentil por vizinho mais próximo — honesto para amostras pequenas."""
    if not sorted_values:
        return 0
    index = min(len(sorted_values) - 1, max(0, round(pct / 100 * (len(sorted_values) - 1))))
    return sorted_values[index]


def _minutes(seconds) -> str:
    return format(Decimal(seconds) / 60, ".1f")


def _qty(value: Decimal) -> str:
    if not value:
        return "0"
    return format(Decimal(value).quantize(Decimal("0.001")).normalize(), "f")
