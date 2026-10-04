"""B.I. "Sobrou ou faltou?" — a leitura do dia, produto a produto (V4-BI).

A pergunta nº 1 do dono sobre a produção (prévia ``bi-sobra4``): no dia que
passou, o que a casa fez e o que vendeu de cada produto, onde faltou (acabou
cedo), onde sobrou e onde ficou na medida, contra o mesmo dia da semana nas
últimas semanas. Tudo calculado na leitura (ADR-021 §3), sem tabela nova.

Fontes, todas já existentes:

- **fez**: o realizado dos lotes fechados do dia (``WorkOrder.finished`` por
  ``output_sku`` e ``target_date``), a mesma base do aproveitamento;
- **vendeu**: as linhas de venda conciliadas do B.I. (``canonical.read_sales``:
  nativo, e o histórico onde o nativo não vendeu), com a hora de cada venda;
- **acabou às**: a hora da venda em que o vendido acumulado alcançou o feito.
  Não existe registro de "esgotou" no sistema; esta é a leitura honesta que os
  dois fatos permitem, e só existe quando o vendido alcança o feito;
- **vendas perdidas (est.)**: a extrapolação da fórmula de sugestão do
  Craftsman (``_estimate_demand``): o ritmo até acabar, estendido até o
  fechamento, com teto de 2× o vendido. Sem horário declarado da loja, não há
  estimativa (a casa não finge dado);
- **custo da sobra**: ``Product.reference_cost_q`` (CostBackend). Sem custo
  conhecido o valor fica vazio e o resumo diz que está incompleto.

Veredito por produto (as três palavras da prévia, nada além):

- ``short`` (faltou): acabou antes da última hora do expediente;
- ``right`` (na medida): acabou na última hora, ou sobrou até ``NEAR_LEFTOVER``
  (inclui o dia em que vendeu mais do que fez: havia estoque de antes, então o
  feito não "acabou");
- ``over`` (sobrou): sobrou mais que isso.

Nenhum número de fechamento de caixa passa por aqui (SUITE-UX §15, fechamento
às cegas): sobra é estoque de produto, não diferença de gaveta.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Quantos dias do mesmo dia da semana formam o "típico".
COMPARE_DAYS = 4
#: Até quantas semanas para trás procurar esses dias (feriado e episódio pulam).
COMPARE_LOOKBACK_WEEKS = 12
#: Sobrou até isto, em unidades: na medida.
NEAR_LEFTOVER = Decimal(2)
#: Acabou dentro da última hora do expediente: na medida.
LATE_SOLDOUT_MINUTES = 60
#: Teto da extrapolação (o mesmo da fórmula do Craftsman).
LOST_CAP_FACTOR = Decimal(2)
#: Até quantos dias para trás procurar o último dia aberto (o padrão "ontem").
DEFAULT_LOOKBACK_DAYS = 14

VERDICT_SHORT = "short"
VERDICT_OVER = "over"
VERDICT_RIGHT = "right"

WEEKDAY_LABELS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


@dataclass(frozen=True)
class BIOverShortLot:
    """Um lote fechado do produto no dia: o registro de onde o "fez" saiu."""

    ref: str
    #: Hora local em que o lote foi fechado ("06:30"); vazio sem registro.
    finished_at: str
    qty: str


@dataclass(frozen=True)
class BIOverShortHour:
    hour: int
    sold: str
    #: Vendas perdidas estimadas naquela hora (depois que acabou); "0" fora disso.
    estimated_lost: str


@dataclass(frozen=True)
class BIOverShortRow:
    sku: str
    name: str
    collection_ref: str
    collection: str
    verdict: str
    made: str
    sold: str
    leftover: str
    #: Hora local em que o vendido alcançou o feito ("10:40"); vazio se não acabou.
    soldout_at: str
    #: Vendas perdidas estimadas; vazio quando não faltou ou não há como estimar.
    lost_estimate: str
    #: Vendido médio no mesmo dia da semana; vazio sem amostra.
    typical_sold: str
    typical_made: str
    #: Veredito nos dias de comparação em que o produto foi feito (mais recente primeiro).
    history: tuple[str, ...]
    #: Custo da sobra em centavos; None sem custo conhecido (ou sem sobra).
    leftover_cost_q: int | None
    lots: tuple[BIOverShortLot, ...]
    sales_by_hour: tuple[BIOverShortHour, ...]


@dataclass(frozen=True)
class BIOverShortSummary:
    short: int
    over: int
    right: int
    lost_estimate: str
    leftover_units: str
    leftover_cost_q: int
    #: False quando algum produto que sobrou não tem custo conhecido.
    cost_complete: bool


@dataclass(frozen=True)
class BIOverShortTypical:
    """O mesmo resumo, em média, nos dias de comparação."""

    days: int
    short: str
    over: str
    leftover_units: str
    leftover_cost_q: int


@dataclass(frozen=True)
class BIOverShortReport:
    day: str
    weekday_label: str
    #: Expediente declarado do dia ("07:00"/"18:00"); vazio sem horário.
    opens_at: str
    closes_at: str
    #: Dias do mesmo dia da semana usados como típico (mais recente primeiro).
    compare_days: tuple[str, ...]
    #: Dia aberto anterior e seguinte (vazio quando não há: o seguinte nunca é hoje).
    previous_day: str
    next_day: str
    #: O próximo dia aberto com o mesmo dia da semana, a partir de hoje: o plano a levar.
    plan_day: str
    rows: tuple[BIOverShortRow, ...]
    summary: BIOverShortSummary
    typical: BIOverShortTypical


@dataclass(frozen=True)
class _DayRead:
    """Feito, vendido e veredito de um dia, por SKU (interno)."""

    made: dict[str, Decimal]
    sold: dict[str, Decimal]
    soldout: dict[str, time]
    verdict: dict[str, str]
    lost: dict[str, Decimal]
    leftover: dict[str, Decimal]
    sales_by_hour: dict[str, dict[int, Decimal]]
    work_orders: dict[str, list]


def build_bi_over_short(*, day: date | None = None) -> BIOverShortReport:
    from shopman.shop.services.business_calendar import is_open_on, selling_hours_for

    today = timezone.localdate()
    day = _default_day(today) if day is None else min(day, today)
    window = selling_hours_for(day)
    current = _read_day(day, window)
    compare = _compare_days(day)
    compare_reads = [(d, _read_day(d, selling_hours_for(d))) for d in compare]

    skus = sorted(current.made, key=lambda sku: _row_order(current, sku))
    every_sku = set(skus).union(*(read.made for _d, read in compare_reads))
    names, collections, costs = _catalog(sorted(every_sku))
    rows = tuple(_row(sku, current, compare_reads, window, names, collections, costs) for sku in skus)

    leftover_cost = 0
    cost_complete = True
    for row in rows:
        if Decimal(row.leftover) <= 0:
            continue
        if row.leftover_cost_q is None:
            cost_complete = False
        else:
            leftover_cost += row.leftover_cost_q

    return BIOverShortReport(
        day=day.isoformat(),
        weekday_label=WEEKDAY_LABELS[day.weekday()],
        opens_at=_hhmm(window[0]) if window else "",
        closes_at=_hhmm(window[1]) if window else "",
        compare_days=tuple(d.isoformat() for d in compare),
        previous_day=_neighbour(day, -1, is_open_on, today),
        next_day=_neighbour(day, +1, is_open_on, today),
        plan_day=_plan_day(day, today, is_open_on),
        rows=rows,
        summary=BIOverShortSummary(
            short=sum(1 for row in rows if row.verdict == VERDICT_SHORT),
            over=sum(1 for row in rows if row.verdict == VERDICT_OVER),
            right=sum(1 for row in rows if row.verdict == VERDICT_RIGHT),
            lost_estimate=_qty(sum((Decimal(row.lost_estimate or 0) for row in rows), Decimal(0))),
            leftover_units=_qty(sum((Decimal(row.leftover) for row in rows), Decimal(0))),
            leftover_cost_q=leftover_cost,
            cost_complete=cost_complete,
        ),
        typical=_typical(compare_reads, costs),
    )


# ── Dias ─────────────────────────────────────────────────────────────────────


def _default_day(today: date) -> date:
    """O último dia aberto antes de hoje (o "ontem" da casa)."""
    from shopman.shop.services.business_calendar import is_open_on

    for offset in range(1, DEFAULT_LOOKBACK_DAYS + 1):
        candidate = today - timedelta(days=offset)
        if is_open_on(candidate):
            return candidate
    return today - timedelta(days=1)


def _compare_days(day: date) -> list[date]:
    """Os últimos ``COMPARE_DAYS`` dias do mesmo dia da semana que ensinam algo.

    Mesma régua da sugestão de produção (``untrustworthy_days``): dia fechado e
    dia atrapalhado por episódio não entram no típico.
    """
    from shopman.shop.services.production import untrustworthy_days

    skip = untrustworthy_days(days=7 * COMPARE_LOOKBACK_WEEKS, until=day)
    found: list[date] = []
    for week in range(1, COMPARE_LOOKBACK_WEEKS + 1):
        candidate = day - timedelta(days=7 * week)
        if candidate in skip:
            continue
        found.append(candidate)
        if len(found) == COMPARE_DAYS:
            break
    return found


def _neighbour(day: date, step: int, is_open_on, today: date) -> str:
    candidate = day
    for _ in range(DEFAULT_LOOKBACK_DAYS):
        candidate += timedelta(days=step)
        if candidate >= today:
            return ""
        if is_open_on(candidate):
            return candidate.isoformat()
    return ""


def _plan_day(day: date, today: date, is_open_on) -> str:
    """O próximo dia com o mesmo dia da semana, de hoje em diante, em que a casa abre."""
    candidate = day + timedelta(days=7)
    while candidate < today:
        candidate += timedelta(days=7)
    for _ in range(COMPARE_LOOKBACK_WEEKS):
        if is_open_on(candidate):
            return candidate.isoformat()
        candidate += timedelta(days=7)
    return ""


# ── Leitura de um dia ────────────────────────────────────────────────────────


def _read_day(day: date, window: tuple[time, time] | None) -> _DayRead:
    from shopman.craftsman.models import WorkOrder

    from shopman.backstage.bi.canonical import read_sales

    made: dict[str, Decimal] = defaultdict(Decimal)
    work_orders: dict[str, list] = defaultdict(list)
    for wo in (
        WorkOrder.objects.filter(target_date=day, status=WorkOrder.Status.FINISHED)
        .only("ref", "output_sku", "finished", "finished_at")
        .order_by("finished_at", "pk")
    ):
        if not wo.output_sku or not wo.finished:
            continue
        made[wo.output_sku] += wo.finished or Decimal(0)
        work_orders[wo.output_sku].append(wo)

    sales = read_sales(day, day)
    by_key = sales.sales_by_key()
    timeline: dict[str, list[tuple[datetime, Decimal]]] = defaultdict(list)
    for line in sales.lines():
        sku = line.product_ref
        if not sku or sku not in made:
            continue
        sale = by_key.get((line.source, line.sale_key))
        if sale is None:
            continue
        timeline[sku].append((sale.occurred_at, Decimal(line.qty)))

    sold: dict[str, Decimal] = {}
    soldout: dict[str, time] = {}
    verdict: dict[str, str] = {}
    lost: dict[str, Decimal] = {}
    leftover: dict[str, Decimal] = {}
    sales_by_hour: dict[str, dict[int, Decimal]] = {}
    for sku, made_qty in made.items():
        events = sorted(timeline.get(sku, []), key=lambda item: item[0])
        total = Decimal(0)
        hours: dict[int, Decimal] = defaultdict(Decimal)
        reached: time | None = None
        for at, qty in events:
            total += qty
            hours[at.hour] += qty
            if reached is None and made_qty > 0 and total >= made_qty:
                reached = at.time().replace(second=0, microsecond=0)
        if reached is not None and total > made_qty + NEAR_LEFTOVER:
            # Vendeu bem mais do que o dia fez: havia estoque de antes (sobra de
            # ontem, compra). O produto não acabou quando o feito acabou.
            reached = None
        sold[sku] = total
        sales_by_hour[sku] = dict(hours)
        leftover[sku] = max(Decimal(0), made_qty - total)
        if reached is not None:
            soldout[sku] = reached
        verdict[sku] = _verdict(reached, leftover[sku], window)
        if verdict[sku] == VERDICT_SHORT and reached is not None:
            estimate = _lost_estimate(total, reached, window)
            if estimate is not None:
                lost[sku] = estimate
    return _DayRead(
        made=dict(made),
        sold=sold,
        soldout=soldout,
        verdict=verdict,
        lost=lost,
        leftover=leftover,
        sales_by_hour=sales_by_hour,
        work_orders=dict(work_orders),
    )


def _verdict(soldout: time | None, leftover: Decimal, window: tuple[time, time] | None) -> str:
    if soldout is not None:
        if window is None:
            return VERDICT_SHORT
        late = _minutes(window[1]) - LATE_SOLDOUT_MINUTES
        return VERDICT_RIGHT if _minutes(soldout) >= late else VERDICT_SHORT
    return VERDICT_RIGHT if leftover <= NEAR_LEFTOVER else VERDICT_OVER


def _lost_estimate(sold: Decimal, soldout: time, window: tuple[time, time] | None) -> Decimal | None:
    """O ritmo até acabar, estendido até o fechamento, com teto de 2× o vendido.

    A mesma conta de ``craftsman.services.queries._estimate_demand``, que a
    sugestão usa para não ensinar que o dia que esgotou vende pouco.
    """
    if window is None or sold <= 0:
        return None
    selling = _minutes(soldout) - _minutes(window[0])
    full = _minutes(window[1]) - _minutes(window[0])
    if selling <= 0 or full <= 0:
        return None
    estimated = min(sold * Decimal(full) / Decimal(selling), sold * LOST_CAP_FACTOR)
    return max(Decimal(0), estimated - sold)


def _hours(read: _DayRead, sku: str, window: tuple[time, time] | None) -> tuple[BIOverShortHour, ...]:
    """Vendas por hora no expediente, e a perda estimada distribuída depois que acabou."""
    hours = read.sales_by_hour.get(sku, {})
    if window is not None:
        first = window[0].hour
        last = window[1].hour - (1 if window[1].minute == 0 else 0)
    elif hours:
        first, last = min(hours), max(hours)
    else:
        return ()
    if hours:
        first, last = min(first, min(hours)), max(last, max(hours))

    lost = read.lost.get(sku, Decimal(0))
    soldout = read.soldout.get(sku)
    estimated: dict[int, Decimal] = {}
    if lost > 0 and soldout is not None and window is not None:
        start, end = _minutes(soldout), _minutes(window[1])
        span = end - start
        if span > 0:
            for hour in range(first, last + 1):
                overlap = min(end, (hour + 1) * 60) - max(start, hour * 60)
                if overlap > 0:
                    estimated[hour] = lost * Decimal(overlap) / Decimal(span)
    return tuple(
        BIOverShortHour(
            hour=hour,
            sold=_qty(hours.get(hour, Decimal(0))),
            estimated_lost=_qty(_round_units(estimated.get(hour, Decimal(0)))),
        )
        for hour in range(first, last + 1)
    )


# ── Linhas ───────────────────────────────────────────────────────────────────


def _row_order(read: _DayRead, sku: str) -> tuple:
    """Faltou primeiro (a maior perda estimada antes; empate, o que acabou mais cedo),
    depois sobrou (a maior sobra antes), depois na medida (o maior feito antes)."""
    rank = {VERDICT_SHORT: 0, VERDICT_OVER: 1, VERDICT_RIGHT: 2}[read.verdict[sku]]
    soldout = read.soldout.get(sku)
    if rank == 0:
        return (rank, -read.lost.get(sku, Decimal(0)), _minutes(soldout) if soldout else 0, sku)
    if rank == 1:
        return (rank, -read.leftover[sku], sku)
    return (rank, -read.made[sku], sku)


def _row(sku, current: _DayRead, compare_reads, window, names, collections, costs) -> BIOverShortRow:
    made = current.made[sku]
    sold = current.sold.get(sku, Decimal(0))
    leftover = current.leftover[sku]
    sample = [read for _day, read in compare_reads if read.made.get(sku)]
    typical_sold = (
        sum((read.sold.get(sku, Decimal(0)) for read in sample), Decimal(0)) / len(sample) if sample else None
    )
    typical_made = sum((read.made[sku] for read in sample), Decimal(0)) / len(sample) if sample else None
    cost = costs.get(sku)
    collection_ref, collection = collections.get(sku, ("", ""))
    soldout = current.soldout.get(sku)
    lost = current.lost.get(sku)
    return BIOverShortRow(
        sku=sku,
        name=names.get(sku) or sku,
        collection_ref=collection_ref,
        collection=collection,
        verdict=current.verdict[sku],
        made=_qty(made),
        sold=_qty(sold),
        leftover=_qty(leftover),
        soldout_at=_hhmm(soldout) if soldout else "",
        lost_estimate=_qty(_round_units(lost)) if lost is not None else "",
        typical_sold=_qty(_round_units(typical_sold)) if typical_sold is not None else "",
        typical_made=_qty(_round_units(typical_made)) if typical_made is not None else "",
        history=tuple(read.verdict[sku] for read in sample),
        leftover_cost_q=(
            int((leftover * Decimal(cost)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
            if cost is not None and leftover > 0
            else None
        ),
        lots=tuple(
            BIOverShortLot(
                ref=wo.ref,
                finished_at=_hhmm(timezone.localtime(wo.finished_at).time()) if wo.finished_at else "",
                qty=_qty(wo.finished or Decimal(0)),
            )
            for wo in current.work_orders.get(sku, [])
        ),
        sales_by_hour=_hours(current, sku, window),
    )


def _typical(compare_reads, costs: dict[str, int]) -> BIOverShortTypical:
    if not compare_reads:
        return BIOverShortTypical(days=0, short="", over="", leftover_units="", leftover_cost_q=0)
    count = len(compare_reads)
    short = sum(sum(1 for v in read.verdict.values() if v == VERDICT_SHORT) for _d, read in compare_reads)
    over = sum(sum(1 for v in read.verdict.values() if v == VERDICT_OVER) for _d, read in compare_reads)
    units = sum((sum(read.leftover.values(), Decimal(0)) for _d, read in compare_reads), Decimal(0))
    cost_total = Decimal(0)
    for _d, read in compare_reads:
        for sku, leftover in read.leftover.items():
            if leftover > 0 and costs.get(sku) is not None:
                cost_total += leftover * Decimal(costs[sku])
    return BIOverShortTypical(
        days=count,
        short=_qty(_round_units(Decimal(short) / count)),
        over=_qty(_round_units(Decimal(over) / count)),
        leftover_units=_qty(_round_units(units / count)),
        leftover_cost_q=int((cost_total / count).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
    )


def _catalog(skus: list[str]) -> tuple[dict[str, str], dict[str, tuple[str, str]], dict[str, int]]:
    """Nome, coleção principal e custo de referência de cada SKU (só leitura)."""
    if not skus:
        return {}, {}, {}
    from shopman.offerman.models import CollectionItem, Product

    names: dict[str, str] = {}
    costs: dict[str, int] = {}
    for product in Product.objects.filter(sku__in=skus):
        names[product.sku] = product.name
        try:
            cost = product.reference_cost_q
        except Exception:
            # Custo é opcional (sem CostBackend a propriedade já devolve None). Um
            # backend configurado que falha não derruba a leitura: a sobra fica sem
            # R$, o resumo diz "custo parcial", e a falha fica no log.
            logger.warning("bi_over_short: custo de referência indisponível para %s", product.sku, exc_info=True)
            cost = None
        if cost:
            costs[product.sku] = int(cost)
    collections: dict[str, tuple[str, str]] = {}
    for item in (
        CollectionItem.objects.filter(product__sku__in=skus)
        .select_related("collection", "product")
        .order_by("-is_primary", "pk")
    ):
        collections.setdefault(item.product.sku, (item.collection.ref, item.collection.name))
    return names, collections, costs


# ── Formatos ─────────────────────────────────────────────────────────────────


def _minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _hhmm(value: time) -> str:
    return f"{value.hour:02d}:{value.minute:02d}"


def _round_units(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal(0)
    return Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP)


def _qty(value: Decimal) -> str:
    if not value:
        return "0"
    return format(Decimal(value).quantize(Decimal("0.001")).normalize(), "f")
