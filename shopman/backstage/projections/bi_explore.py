"""B.I. explorador — métrica × dimensões com gramática whitelist (F8).

O gestor escolhe a pergunta: uma métrica, cruzada por até duas dimensões,
numa janela. A gramática é ESTRITA (regra da casa: roda como configurada ou
não roda): métrica ou dimensão desconhecida, ou combinação fora da matriz de
compatibilidade, é rejeitada com a lista do que existe — nunca vira SQL à la
carte, nunca inventa fallback.

Valores saem NUMÉRICOS + `unit`; quem formata é a presentation (ADR-014).
Rankings são limitados e o corte é DECLARADO (`truncated`) — teto silencioso
lê como "cobri tudo" quando não cobriu. Perda sem defeito declarado vira o
balde "(sem motivo)" em vez de sumir.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from .bi_production import _normalize_window

MAX_ROWS = 60

WEEKDAY_LABELS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")

MONTH_LABELS = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)


class ExploreError(ValueError):
    """Configuração fora da gramática — a mensagem já diz o que existe."""


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    unit: str  # "q" (centavos) | "count" | "qty" | "percent" | "minutes"
    dimensions: tuple[str, ...]
    family: str  # sales | sales_items | production | oven | cash


METRICS: dict[str, MetricSpec] = {
    spec.key: spec
    for spec in (
        MetricSpec("revenue", "Faturamento", "q",
                   ("time", "channel", "hour", "weekday", "month_of_year",
                    "week_of_year", "source"), "sales"),
        MetricSpec("orders", "Pedidos", "count",
                   ("time", "channel", "hour", "weekday", "month_of_year",
                    "week_of_year", "source"), "sales"),
        MetricSpec("average_ticket", "Ticket médio", "q",
                   ("time", "channel", "hour", "weekday", "month_of_year",
                    "week_of_year", "source"), "sales"),
        MetricSpec("qty_sold", "Quantidade vendida", "qty",
                   ("time", "sku", "hour", "weekday", "month_of_year",
                    "week_of_year", "source"), "sales_items"),
        MetricSpec("qty_produced", "Quantidade produzida", "qty",
                   ("time", "recipe", "oven", "operator", "weekday", "grade"), "production"),
        MetricSpec("loss", "Perda de produção", "qty",
                   ("time", "recipe", "oven", "operator", "weekday", "defect"), "production"),
        MetricSpec("yield_percent", "Rendimento", "percent",
                   ("time", "recipe", "oven", "operator", "weekday"), "production"),
        MetricSpec("oven_minutes", "Tempo de forno", "minutes",
                   ("time", "recipe", "oven", "operator"), "oven"),
        MetricSpec("cash_difference", "Quebra de caixa", "q", ("time", "operator"), "cash"),
        # Abastecimento: as duas caras da mesma decisão de fornada.
        MetricSpec("soldout_days", "Dias que acabaram", "count",
                   ("sku", "time", "weekday", "month_of_year"), "shelf"),
        MetricSpec("hours_without_stock", "Horas sem produto na prateleira", "hours",
                   ("sku", "time", "weekday", "month_of_year"), "shelf"),
        # A pergunta que o dono chamou de mais sensível: não ter o que oferecer.
        # Fonte diferente da de cima — ver docstring de _outage_rows.
        MetricSpec("unavailable_hours", "Horas sem poder vender", "hours",
                   ("sku", "time", "weekday", "month_of_year", "channel",
                    "outage_reason"), "outage"),
        MetricSpec("paused_hours", "Horas pausado", "hours",
                   ("sku", "time", "weekday", "month_of_year", "channel"), "outage"),
        # Proporção do expediente: comparável entre um sábado de nove horas e
        # um feriado de quatro, o que a contagem em horas não permite.
        MetricSpec("unavailable_share", "% do expediente sem vender", "percent",
                   ("sku", "time", "weekday", "month_of_year", "channel",
                    "outage_reason"), "outage"),
        MetricSpec("leftover", "Sobra no fim do dia", "qty",
                   ("sku", "time", "weekday", "month_of_year"), "shelf"),
    )
}

DIMENSION_LABELS: dict[str, str] = {
    "time": "Tempo (dia)",
    "channel": "Canal",
    "hour": "Hora do dia",
    "weekday": "Dia da semana",
    # Cíclicas: juntam todos os anos no mesmo balde. É o eixo da sazonalidade —
    # diferente da série do tempo, que é cronológica e nunca repete um balde.
    "month_of_year": "Mês do ano",
    "week_of_year": "Semana do ano",
    "source": "Fonte (Shopman/Yooga)",
    "sku": "Produto",
    "recipe": "Receita",
    "oven": "Forno",
    "operator": "Operador",
    "grade": "Grau de qualidade",
    "defect": "Defeito",
    "outage_reason": "Motivo (esgotado/pausado)",
    "day_kind": "Tipo de dia (feriado)",
    "temperature": "Temperatura do dia",
    "rain": "Chuva",
}

DAY_KIND_LABELS = {
    "holiday": "Feriado",
    "holiday_eve": "Véspera de feriado",
    "post_holiday": "Volta de feriado",
    "regular": "Dia comum",
}

# Dimensões que têm ordem própria: saem na sequência natural, não em ranking.
ORDINAL_DIMENSIONS = frozenset(
    {"time", "hour", "weekday", "month_of_year", "week_of_year", "temperature"}
)

# Dimensões de CONTEXTO: dependem de dado que a suite não produz (calendário de
# feriados, clima). Só entram na gramática quando alguém injetou o dado — sem
# ele a opção nem aparece, em vez de aparecer e responder vazio. Não inventamos
# contexto: ou sabemos, ou a pergunta não está disponível.
CONTEXT_DIMENSIONS = ("day_kind", "temperature", "rain")

CONTEXT_METRIC_FAMILIES = ("sales", "sales_items", "shelf", "outage")


@dataclass(frozen=True)
class BIExploreRow:
    key: str
    label: str
    key2: str
    label2: str
    value: float


@dataclass(frozen=True)
class BIExploreMetricOption:
    key: str
    label: str
    unit: str
    dimensions: tuple[str, ...]


@dataclass(frozen=True)
class BIExploreReport:
    metric: str
    metric_label: str
    unit: str
    dimension: str
    dimension_label: str
    dimension2: str
    dimension2_label: str
    date_from: str
    date_to: str
    rows: tuple[BIExploreRow, ...]
    truncated: int  # linhas cortadas do ranking — corte declarado, nunca mudo
    metrics: tuple[BIExploreMetricOption, ...]  # a gramática, para a UI montar os selects


def available_context_dimensions() -> tuple[str, ...]:
    """Quais dimensões de contexto têm dado carregado AGORA.

    Feriado exige calendário injetado; temperatura e chuva exigem clima. Sem o
    dado, a dimensão não existe para ninguém — nem no select, nem na validação.
    """
    from shopman.backstage.models import DayContext

    available = []
    if DayContext.objects.filter(has_calendar=True).exists():
        available.append("day_kind")
    if DayContext.objects.filter(temp_max_c__isnull=False).exists():
        available.append("temperature")
    if DayContext.objects.filter(rain_mm__isnull=False).exists():
        available.append("rain")
    return tuple(available)


def _dimensions_for(spec: MetricSpec, context: tuple[str, ...]) -> tuple[str, ...]:
    if spec.family not in CONTEXT_METRIC_FAMILIES:
        return spec.dimensions
    return (*spec.dimensions, *(dim for dim in CONTEXT_DIMENSIONS if dim in context))


def metric_options() -> tuple[BIExploreMetricOption, ...]:
    context = available_context_dimensions()
    return tuple(
        BIExploreMetricOption(
            key=s.key, label=s.label, unit=s.unit,
            dimensions=_dimensions_for(s, context),
        )
        for s in METRICS.values()
    )


def validate_config(metric: str, by: str, by2: str) -> MetricSpec:
    """A gramática. Erros carregam o que EXISTE — o operador se corrige sozinho."""
    spec = METRICS.get(metric)
    if spec is None:
        raise ExploreError(f"Métrica desconhecida: {metric!r}. Existem: {', '.join(sorted(METRICS))}.")
    # O contexto só é consultado quando a pergunta o envolve: validar métrica e
    # dimensão comuns não precisa tocar o banco.
    if by in CONTEXT_DIMENSIONS or by2 in CONTEXT_DIMENSIONS:
        context = available_context_dimensions()
        for requested in (by, by2):
            if requested in CONTEXT_DIMENSIONS and requested not in context:
                raise ExploreError(
                    f"{DIMENSION_LABELS[requested]} exige dado carregado: rode "
                    f"{'import_holidays' if requested == 'day_kind' else 'import_weather'}. "
                    "Sem o dado, a suite não inventa o recorte."
                )
        spec = replace(spec, dimensions=_dimensions_for(spec, context))
    if by not in spec.dimensions:
        raise ExploreError(
            f"Dimensão {by!r} não vale para {spec.label}. Valem: {', '.join(spec.dimensions)}."
        )
    if by2:
        if by2 == by:
            raise ExploreError("As duas dimensões precisam ser diferentes.")
        if by2 == "time":
            raise ExploreError("Tempo só pode ser a dimensão principal.")
        if by2 not in spec.dimensions:
            raise ExploreError(
                f"Dimensão {by2!r} não vale para {spec.label}. Valem: {', '.join(spec.dimensions)}."
            )
    return spec


def build_bi_explore(
    *,
    metric: str,
    by: str = "time",
    by2: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
) -> BIExploreReport:
    spec = validate_config(metric, by, by2)
    date_from, date_to = _normalize_window(date_from, date_to)

    resolver = {
        "sales": _sales_rows,
        "sales_items": _sales_item_rows,
        "production": _production_rows,
        "oven": _oven_rows,
        "cash": _cash_rows,
        "shelf": _shelf_rows,
        "outage": _outage_rows,
    }[spec.family]
    rows = resolver(spec, by, by2, date_from, date_to)

    # Dimensão ordinal (tempo, hora, dia-da-semana, mês, semana) sai na ordem
    # natural: é curva, e curva ordenada por valor deixa de ser curva. As
    # demais são ranking — por valor, limitado e com o corte declarado.
    if by in ORDINAL_DIMENSIONS:
        rows.sort(key=lambda row: (row.key, row.key2))
        truncated = 0
    else:
        rows.sort(key=lambda row: -abs(row.value))
        truncated = max(0, len(rows) - MAX_ROWS)
        rows = rows[:MAX_ROWS]

    return BIExploreReport(
        metric=spec.key,
        metric_label=spec.label,
        unit=spec.unit,
        dimension=by,
        dimension_label=DIMENSION_LABELS[by],
        dimension2=by2,
        dimension2_label=DIMENSION_LABELS.get(by2, ""),
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        rows=tuple(rows),
        truncated=truncated,
        metrics=metric_options(),
    )


# ── Chaves de dimensão ───────────────────────────────────────────────────────


def _weekday(local) -> tuple[str, str]:
    index = local.weekday()
    return str(index), WEEKDAY_LABELS[index]


def _month_of_year(local) -> tuple[str, str]:
    return f"{local.month:02d}", MONTH_LABELS[local.month - 1]


def _week_of_year(local) -> tuple[str, str]:
    week = local.isocalendar().week
    return f"{week:02d}", f"sem {week}"


def _dim_key(dim: str, *, local=None, extra=None) -> tuple[str, str]:
    """(key, label) para dimensões derivadas de um instante local."""
    if dim == "time":
        iso = local.date().isoformat()
        return iso, iso
    if dim == "hour":
        return f"{local.hour:02d}", f"{local.hour}h"
    if dim == "weekday":
        return _weekday(local)
    if dim == "month_of_year":
        return _month_of_year(local)
    if dim == "week_of_year":
        return _week_of_year(local)
    return extra  # dimensões de valor direto: quem chama resolve


# ── Vendas (pedido a pedido, fusão nativo/histórico: dia nativo vence) ──────


def _sales_rows(spec, by, by2, date_from, date_to) -> list[BIExploreRow]:
    from shopman.orderman.models import Order

    from shopman.backstage.models import HistoricalSale

    from .bi_sales import _local_datetime_window

    window = _local_datetime_window(date_from, date_to)
    excluded = (Order.Status.CANCELLED, Order.Status.RETURNED)

    events: list[tuple] = []  # (local_dt, total_q, channel, source)
    native_days: set[date] = set()
    native = Order.objects.filter(created_at__range=window).values_list(
        "created_at", "total_q", "channel_ref", "status"
    )
    for created_at, total_q, channel_ref, status in native:
        if status in excluded:
            continue
        local = timezone.localtime(created_at)
        native_days.add(local.date())
        events.append((local, total_q, channel_ref, "shopman"))
    historical = HistoricalSale.objects.filter(occurred_at__range=window).values_list(
        "occurred_at", "total_q", "is_delivery"
    )
    for occurred_at, total_q, is_delivery in historical:
        local = timezone.localtime(occurred_at)
        if local.date() in native_days:
            continue
        events.append((local, total_q, "yooga · delivery" if is_delivery else "yooga · loja", "yooga"))

    contexts = _day_contexts(date_from, date_to) if _wants_context(by, by2) else {}

    revenue: dict[tuple, int] = defaultdict(int)
    orders: dict[tuple, int] = defaultdict(int)
    labels: dict[tuple, tuple[str, str]] = {}
    for local, total_q, channel, source in events:
        parts = []
        for dim in (by, by2):
            if not dim:
                parts.append(("", ""))
            elif dim == "channel":
                parts.append((channel, channel))
            elif dim == "source":
                parts.append((source, source))
            elif dim in CONTEXT_DIMENSIONS:
                parts.append(_context_part(dim, local.date(), contexts))
            else:
                parts.append(_dim_key(dim, local=local))
        if any(part is None for part in parts):
            continue  # dia sem o contexto pedido fica fora, em vez de virar balde
        key = (parts[0][0], parts[1][0])
        revenue[key] += total_q
        orders[key] += 1
        labels[key] = (parts[0][1], parts[1][1])

    def value(key) -> float:
        if spec.key == "revenue":
            return float(revenue[key])
        if spec.key == "orders":
            return float(orders[key])
        return float(revenue[key] // orders[key]) if orders[key] else 0.0

    return [
        BIExploreRow(key=k1, label=labels[(k1, k2)][0], key2=k2, label2=labels[(k1, k2)][1], value=value((k1, k2)))
        for (k1, k2) in revenue
    ]


def _sales_item_rows(spec, by, by2, date_from, date_to) -> list[BIExploreRow]:
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import HistoricalSaleItem

    from .bi_sales import _local_datetime_window

    window = _local_datetime_window(date_from, date_to)
    excluded = (Order.Status.CANCELLED, Order.Status.RETURNED)
    native_days = {
        timezone.localtime(dt).date()
        for dt in Order.objects.filter(created_at__range=window)
        .exclude(status__in=excluded)
        .values_list("created_at", flat=True)
    }

    contexts = _day_contexts(date_from, date_to) if _wants_context(by, by2) else {}

    qty: dict[tuple, Decimal] = defaultdict(Decimal)
    labels: dict[tuple, tuple[str, str]] = {}

    def fold(local, sku, name, quantity, source):
        parts = []
        for dim in (by, by2):
            if not dim:
                parts.append(("", ""))
            elif dim == "sku":
                key = sku or f"nome:{name}"
                parts.append((key, name))
            elif dim == "source":
                parts.append((source, source))
            elif dim in CONTEXT_DIMENSIONS:
                parts.append(_context_part(dim, local.date(), contexts))
            else:
                parts.append(_dim_key(dim, local=local))
        if any(part is None for part in parts):
            return  # sem contexto para o dia, a linha não entra
        key = (parts[0][0], parts[1][0])
        qty[key] += quantity
        labels[key] = (parts[0][1], parts[1][1])

    native_items = OrderItem.objects.filter(order__created_at__range=window).exclude(
        order__status__in=excluded
    ).values_list("order__created_at", "sku", "name", "qty")
    for created_at, sku, name, quantity in native_items:
        fold(timezone.localtime(created_at), sku, name, quantity, "shopman")

    historical_items = HistoricalSaleItem.objects.filter(
        sale__occurred_at__range=window
    ).values_list("sale__occurred_at", "sku", "product_name", "qty")
    for occurred_at, sku, name, quantity in historical_items:
        local = timezone.localtime(occurred_at)
        if local.date() in native_days:
            continue
        fold(local, sku, name, quantity, "yooga")

    return [
        BIExploreRow(key=k1, label=labels[(k1, k2)][0], key2=k2, label2=labels[(k1, k2)][1], value=float(qty[(k1, k2)]))
        for (k1, k2) in qty
    ]


# ── Produção (WOs fechadas; grau/defeito descem às linhas ADR-017) ──────────


def _production_rows(spec, by, by2, date_from, date_to) -> list[BIExploreRow]:
    from shopman.craftsman.models import WorkOrder, WorkOrderItem

    wos = list(
        WorkOrder.objects.filter(
            target_date__range=(date_from, date_to), status=WorkOrder.Status.FINISHED
        ).select_related("recipe")
    )
    wo_by_pk = {wo.pk: wo for wo in wos}

    needs_items = "grade" in (by, by2) or "defect" in (by, by2)
    catalog_labels = _quality_labels() if needs_items else {}

    def wo_part(dim: str, wo) -> tuple[str, str]:
        if dim == "time":
            iso = wo.target_date.isoformat()
            return iso, iso
        if dim == "recipe":
            return wo.recipe.ref, wo.recipe.name
        if dim == "oven":
            return (wo.position_ref or "(sem forno)",) * 2
        if dim == "operator":
            return (wo.operator_ref or "(sem operador)",) * 2
        if dim == "weekday":
            index = wo.target_date.weekday()
            return str(index), WEEKDAY_LABELS[index]
        return "", ""

    planned: dict[tuple, Decimal] = defaultdict(Decimal)
    finished: dict[tuple, Decimal] = defaultdict(Decimal)
    labels: dict[tuple, tuple[str, str]] = {}

    if needs_items:
        item_dim = "grade" if "grade" in (by, by2) else "defect"
        kind = WorkOrderItem.Kind.OUTPUT if item_dim == "grade" else WorkOrderItem.Kind.WASTE
        ref_field = "quality_grade_ref" if item_dim == "grade" else "quality_defect_ref"
        rows = WorkOrderItem.objects.filter(
            work_order_id__in=wo_by_pk, kind=kind
        ).values_list("work_order_id", ref_field, "quantity")
        qty: dict[tuple, Decimal] = defaultdict(Decimal)
        for wo_pk, ref, quantity in rows:
            wo = wo_by_pk[wo_pk]
            ref = ref or "(sem motivo)" if item_dim == "defect" else ref or "(sem grau)"
            item_part = (ref, catalog_labels.get(ref, ref))
            parts = []
            for dim in (by, by2):
                if not dim:
                    parts.append(("", ""))
                elif dim == item_dim:
                    parts.append(item_part)
                else:
                    parts.append(wo_part(dim, wo))
            key = (parts[0][0], parts[1][0])
            qty[key] += quantity
            labels[key] = (parts[0][1], parts[1][1])
        return [
            BIExploreRow(key=k1, label=labels[(k1, k2)][0], key2=k2, label2=labels[(k1, k2)][1], value=float(qty[(k1, k2)]))
            for (k1, k2) in qty
        ]

    for wo in wos:
        parts = [wo_part(by, wo), wo_part(by2, wo) if by2 else ("", "")]
        key = (parts[0][0], parts[1][0])
        planned[key] += wo.quantity
        finished[key] += wo.finished or Decimal(0)
        labels[key] = (parts[0][1], parts[1][1])

    def value(key) -> float:
        if spec.key == "qty_produced":
            return float(finished[key])
        if spec.key == "loss":
            return float(max(Decimal(0), planned[key] - finished[key]))
        return round(float(finished[key] * 100 / planned[key])) if planned[key] else 0.0

    return [
        BIExploreRow(key=k1, label=labels[(k1, k2)][0], key2=k2, label2=labels[(k1, k2)][1], value=value((k1, k2)))
        for (k1, k2) in planned
    ]


def _quality_labels() -> dict[str, str]:
    from shopman.shop.models import QualityDefect, QualityGrade

    labels = dict(QualityGrade.objects.values_list("ref", "label"))
    labels.update(dict(QualityDefect.objects.values_list("ref", "label")))
    return labels


# ── Forno (só o par armar→Concluir mede; média por chave) ───────────────────


def _oven_rows(spec, by, by2, date_from, date_to) -> list[BIExploreRow]:
    from shopman.craftsman.models import WorkOrder

    from shopman.backstage.models import OvenRun

    from .bi_production import _measured_runs

    runs = _measured_runs(date_from=date_from, date_to=date_to, oven_run_model=OvenRun)
    refs = {run.work_order_ref for run in runs}
    wo_by_ref = {
        wo.ref: wo
        for wo in WorkOrder.objects.filter(ref__in=refs).select_related("recipe")
    }

    total: dict[tuple, float] = defaultdict(float)
    count: dict[tuple, int] = defaultdict(int)
    labels: dict[tuple, tuple[str, str]] = {}
    for run in runs:
        wo = wo_by_ref.get(run.work_order_ref)
        parts = []
        for dim in (by, by2):
            if not dim:
                parts.append(("", ""))
            elif dim == "time":
                iso = timezone.localtime(run.armed_at).date().isoformat()
                parts.append((iso, iso))
            elif dim == "recipe":
                if wo is None:
                    parts.append(("(sem receita)", "(sem receita)"))
                else:
                    parts.append((wo.recipe.ref, wo.recipe.name))
            elif dim == "oven":
                parts.append(((run.oven_ref or "(sem forno)"),) * 2)
            elif dim == "operator":
                parts.append(((run.operator_ref or "(sem operador)"),) * 2)
        key = (parts[0][0], parts[1][0])
        total[key] += run.elapsed_seconds / 60
        count[key] += 1
        labels[key] = (parts[0][1], parts[1][1])

    return [
        BIExploreRow(
            key=k1, label=labels[(k1, k2)][0], key2=k2, label2=labels[(k1, k2)][1],
            value=round(total[(k1, k2)] / count[(k1, k2)], 1),
        )
        for (k1, k2) in total
    ]


# ── Caixa (turnos fechados) ─────────────────────────────────────────────────


def _cash_rows(spec, by, by2, date_from, date_to) -> list[BIExploreRow]:
    from shopman.backstage.models import CashShift

    shifts = CashShift.objects.filter(
        status=CashShift.Status.CLOSED,
        closed_at__date__range=(date_from, date_to),
    ).select_related("operator")

    total: dict[tuple, int] = defaultdict(int)
    labels: dict[tuple, tuple[str, str]] = {}
    for shift in shifts:
        local = timezone.localtime(shift.closed_at)
        parts = []
        for dim in (by, by2):
            if not dim:
                parts.append(("", ""))
            elif dim == "time":
                iso = local.date().isoformat()
                parts.append((iso, iso))
            elif dim == "operator":
                username = shift.operator.get_username()
                parts.append((username, username))
        key = (parts[0][0], parts[1][0])
        total[key] += shift.difference_q
        labels[key] = (parts[0][1], parts[1][1])

    return [
        BIExploreRow(key=k1, label=labels[(k1, k2)][0], key2=k2, label2=labels[(k1, k2)][1], value=float(total[(k1, k2)]))
        for (k1, k2) in total
    ]


# ── Prateleira (sobra e falta: as duas caras da decisão da fornada) ─────────


def _shelf_rows(spec, by, by2, date_from, date_to) -> list[BIExploreRow]:
    """Dias que acabaram, horas sem produto e sobra — por SKU e por período.

    Só entram SKUs com posição vendável no ledger: a pergunta é sobre o que o
    cliente encontrava na loja.

    ``hours_without_stock`` conta do esgotamento até o fim do expediente
    declarado; sem horário configurado a loja não tem "fim do dia" e a métrica
    fica zerada em vez de inventar um expediente.
    """
    from shopman.stockman.models import Quant
    from shopman.stockman.services.queries import StockQueries

    from shopman.shop.services.business_calendar import selling_hours_for

    skus = sorted(
        Quant.objects.filter(
            position__is_saleable=True, target_date__isnull=True
        ).values_list("sku", flat=True).distinct()
    )
    if not skus:
        return []

    history = StockQueries.shelf_history(skus, since=date_from, until=date_to)
    leftovers = _leftovers_by_day(date_from, date_to) if spec.key == "leftover" else {}
    contexts = _day_contexts(date_from, date_to) if _wants_context(by, by2) else {}

    totals: dict[tuple, float] = defaultdict(float)
    labels: dict[tuple, tuple[str, str]] = {}

    def part(dim: str, sku: str, day: date):
        if dim == "sku":
            return sku, sku
        if dim == "time":
            iso = day.isoformat()
            return iso, iso
        if dim == "weekday":
            return str(day.weekday()), WEEKDAY_LABELS[day.weekday()]
        if dim == "month_of_year":
            return f"{day.month:02d}", MONTH_LABELS[day.month - 1]
        if dim in CONTEXT_DIMENSIONS:
            return _context_part(dim, day, contexts)
        return "", ""

    for sku, days in history.items():
        for day, shelf in days.items():
            if not shelf.had_stock:
                continue  # dia sem produto não fala sobre sobra nem sobre falta
            value = _shelf_value(
                spec.key, shelf, sku=sku, day=day,
                leftovers=leftovers, selling_hours=selling_hours_for,
            )
            if value is None:
                continue
            parts = [part(by, sku, day), part(by2, sku, day) if by2 else ("", "")]
            if any(item is None for item in parts):
                continue  # dia sem o contexto pedido fica fora da leitura
            key = (parts[0][0], parts[1][0])
            totals[key] += value
            labels[key] = (parts[0][1], parts[1][1])

    # Num RANKING, o que não aconteceu não é linha: produto que nunca faltou não
    # pertence à lista de faltas, e sessenta zeros escondem os dois SKUs que
    # importam. Já numa SÉRIE (by=time), o zero é ponto de curva e fica — o dia
    # em que nada faltou faz parte do desenho.
    keep_zeros = by in ORDINAL_DIMENSIONS
    return [
        BIExploreRow(
            key=k1, label=labels[(k1, k2)][0], key2=k2, label2=labels[(k1, k2)][1],
            value=round(totals[(k1, k2)], 1),
        )
        for (k1, k2) in totals
        if keep_zeros or totals[(k1, k2)] != 0
    ]


def _shelf_value(metric: str, shelf, *, sku: str, day: date, leftovers, selling_hours):
    if metric == "soldout_days":
        return 1.0 if shelf.soldout_at is not None else 0.0
    if metric == "hours_without_stock":
        if shelf.soldout_at is None:
            return 0.0
        window = selling_hours(day)
        if window is None:
            return 0.0  # sem expediente declarado não há "resto do dia" a contar
        closes_at = window[1]
        soldout = timezone.localtime(shelf.soldout_at).time()
        if soldout >= closes_at:
            return 0.0  # acabou junto com o expediente: ninguém ficou sem
        missing = (
            closes_at.hour * 60 + closes_at.minute
            - soldout.hour * 60 - soldout.minute
        )
        return missing / 60
    # leftover: o que sobrou no fechamento, declarado pelo operador na contagem.
    # Dia sem fechamento não vira zero — vira ausência (a linha não entra).
    return leftovers.get((day, sku))


def _leftovers_by_day(date_from: date, date_to: date) -> dict:
    """Sobra por (dia, sku) a partir do fechamento — quem conta é o operador."""
    from shopman.backstage.models import DayClosing

    out: dict[tuple, float] = {}
    for closing in DayClosing.objects.filter(date__range=(date_from, date_to)):
        data = closing.data if isinstance(closing.data, dict) else {}
        for row in data.get("items") or []:
            sku = row.get("sku")
            if not sku:
                continue
            out[(closing.date, sku)] = float(row.get("qty_remaining") or 0)
    return out


# ── Contexto do dia (só existe quando alguém injetou o dado) ────────────────


def _wants_context(by: str, by2: str) -> bool:
    return by in CONTEXT_DIMENSIONS or by2 in CONTEXT_DIMENSIONS


def _day_contexts(date_from: date, date_to: date) -> dict:
    """{data: DayContext} da janela. Dia ausente = contexto desconhecido."""
    from shopman.backstage.models import DayContext

    return {
        row.date: row
        for row in DayContext.objects.filter(date__range=(date_from, date_to))
    }


def _context_part(dim: str, day: date, contexts: dict) -> tuple[str, str] | None:
    """(chave, rótulo) do contexto, ou None quando o dia não tem o dado.

    None faz a linha inteira sair da leitura: um dia sem temperatura medida não
    é um dia frio nem quente, e forçá-lo a um balde seria inventar o recorte.
    """
    context = contexts.get(day)
    if context is None:
        return None
    if dim == "day_kind":
        kind = context.day_kind
        return (kind, DAY_KIND_LABELS[kind]) if kind else None
    if dim == "temperature":
        if context.temp_max_c is None:
            return None
        floor = int(context.temp_max_c // 5 * 5)
        return f"{floor:03d}", f"{floor} a {floor + 4} °C"
    if dim == "rain":
        if context.rain_mm is None:
            return None
        wet = context.rain_mm > 0
        return ("1", "Com chuva") if wet else ("0", "Sem chuva")
    return None


# ── Sem poder vender (o que o cliente encontrava, não o que o estoque tinha) ──


def _outage_rows(spec, by, by2, date_from, date_to) -> list[BIExploreRow]:
    """Horas em que a casa não teve o produto para oferecer.

    Diferente de "horas sem produto na prateleira": o que o cliente encontra é
    o saldo MENOS o reservado, então o produto some do cardápio antes de acabar
    fisicamente e volta quando uma reserva expira. Esta métrica lê os períodos
    observados (``ShelfOutage``) e é a resposta fiel — mas só existe a partir do
    momento em que a casa começou a medir. Período anterior fica sem linha, em
    vez de aparecer como "nunca faltou".

    Conta só o que cai DENTRO do expediente daquele dia: o produto faltar de
    madrugada não custa venda. O expediente vem CONGELADO do contexto do dia
    (``business_day.stamp_day``) e não do horário de hoje — senão mexer no
    cadastro reescreveria o passado, e dia em que a casa nem abriu contaria
    como se tivesse aberto.

    ``unavailable_share`` responde a mesma coisa em PROPORÇÃO do expediente, que
    é o que permite comparar um sábado de nove horas com um feriado de quatro.
    """
    from shopman.backstage.models import ShelfOutage

    tz = timezone.get_current_timezone()
    window_start = datetime.combine(date_from, time.min, tzinfo=tz)
    window_end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz)

    from shopman.backstage.models import OutageReason

    outages = ShelfOutage.objects.filter(started_at__lt=window_end).filter(
        Q(ended_at__isnull=True) | Q(ended_at__gt=window_start)
    )
    if spec.key == "paused_hours":
        outages = outages.filter(reason=OutageReason.PAUSED)
    # O contexto do dia é sempre necessário aqui: é dele que sai o expediente.
    contexts = _day_contexts(date_from, date_to)
    open_minutes = {
        day: context.open_minutes
        for day, context in contexts.items()
        if context.open_minutes is not None
    }

    totals: dict[tuple, float] = defaultdict(float)
    denominators: dict[tuple, float] = defaultdict(float)
    labels: dict[tuple, tuple[str, str]] = {}
    seen_days: dict[tuple, set] = defaultdict(set)

    for outage in outages:
        for day, minutes in _outage_minutes_by_day(outage, date_from, date_to, open_minutes, contexts):
            parts = []
            for dim in (by, by2):
                if not dim:
                    parts.append(("", ""))
                elif dim == "sku":
                    parts.append((outage.sku, outage.sku))
                elif dim == "channel":
                    parts.append((outage.channel_ref, outage.channel_ref))
                elif dim == "outage_reason":
                    parts.append((outage.reason, outage.get_reason_display()))
                elif dim == "time":
                    iso = day.isoformat()
                    parts.append((iso, iso))
                elif dim == "weekday":
                    parts.append((str(day.weekday()), WEEKDAY_LABELS[day.weekday()]))
                elif dim == "month_of_year":
                    parts.append((f"{day.month:02d}", MONTH_LABELS[day.month - 1]))
                elif dim in CONTEXT_DIMENSIONS:
                    parts.append(_context_part(dim, day, contexts))
                else:
                    parts.append(("", ""))
            if any(part is None for part in parts):
                continue
            key = (parts[0][0], parts[1][0])
            totals[key] += minutes / 60
            labels[key] = (parts[0][1], parts[1][1])
            if day not in seen_days[key]:
                seen_days[key].add(day)
                denominators[key] += open_minutes.get(day, 0) / 60

    keep_zeros = by in ORDINAL_DIMENSIONS

    def value(key) -> float:
        if spec.key != "unavailable_share":
            return round(totals[key], 1)
        base = denominators[key]
        return round(totals[key] * 100 / base, 1) if base else 0.0

    return [
        BIExploreRow(
            key=k1, label=labels[(k1, k2)][0], key2=k2, label2=labels[(k1, k2)][1],
            value=value((k1, k2)),
        )
        for (k1, k2) in totals
        if keep_zeros or value((k1, k2)) != 0
    ]


def _outage_minutes_by_day(outage, date_from: date, date_to: date, open_minutes, contexts):
    """Minutos de bloqueio por dia, recortados pelo expediente CONGELADO do dia.

    Dia sem carimbo de expediente não entra: sem saber quando a casa esteve
    aberta, contar horas seria inventar o denominador.
    """
    tz = timezone.get_current_timezone()
    began = timezone.localtime(outage.started_at)
    finished = timezone.localtime(outage.ended_at or timezone.now())

    day = max(began.date(), date_from)
    last = min(finished.date(), date_to)
    while day <= last:
        context = contexts.get(day)
        window = (
            (context.opens_at, context.closes_at)
            if context is not None
            and open_minutes.get(day)
            and context.opens_at
            and context.closes_at
            else None
        )
        if window is not None:
            opens_at, closes_at = window
            open_dt = datetime.combine(day, opens_at, tzinfo=tz)
            close_dt = datetime.combine(day, closes_at, tzinfo=tz)
            start = max(began, open_dt)
            end = min(finished, close_dt)
            if end > start:
                yield day, (end - start).total_seconds() / 60
        day += timedelta(days=1)
