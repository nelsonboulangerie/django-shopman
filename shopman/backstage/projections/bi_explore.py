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
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone

from .bi_production import _normalize_window

MAX_ROWS = 60

WEEKDAY_LABELS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


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
                   ("time", "channel", "hour", "weekday", "source"), "sales"),
        MetricSpec("orders", "Pedidos", "count",
                   ("time", "channel", "hour", "weekday", "source"), "sales"),
        MetricSpec("average_ticket", "Ticket médio", "q",
                   ("time", "channel", "hour", "weekday", "source"), "sales"),
        MetricSpec("qty_sold", "Quantidade vendida", "qty", ("time", "sku", "source"), "sales_items"),
        MetricSpec("qty_produced", "Quantidade produzida", "qty",
                   ("time", "recipe", "oven", "operator", "weekday", "grade"), "production"),
        MetricSpec("loss", "Perda de produção", "qty",
                   ("time", "recipe", "oven", "operator", "weekday", "defect"), "production"),
        MetricSpec("yield_percent", "Rendimento", "percent",
                   ("time", "recipe", "oven", "operator", "weekday"), "production"),
        MetricSpec("oven_minutes", "Tempo de forno", "minutes",
                   ("time", "recipe", "oven", "operator"), "oven"),
        MetricSpec("cash_difference", "Quebra de caixa", "q", ("time", "operator"), "cash"),
    )
}

DIMENSION_LABELS: dict[str, str] = {
    "time": "Tempo (dia)",
    "channel": "Canal",
    "hour": "Hora do dia",
    "weekday": "Dia da semana",
    "source": "Fonte (Shopman/Yooga)",
    "sku": "Produto",
    "recipe": "Receita",
    "oven": "Forno",
    "operator": "Operador",
    "grade": "Grau de qualidade",
    "defect": "Defeito",
}


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


def metric_options() -> tuple[BIExploreMetricOption, ...]:
    return tuple(
        BIExploreMetricOption(key=s.key, label=s.label, unit=s.unit, dimensions=s.dimensions)
        for s in METRICS.values()
    )


def validate_config(metric: str, by: str, by2: str) -> MetricSpec:
    """A gramática. Erros carregam o que EXISTE — o operador se corrige sozinho."""
    spec = METRICS.get(metric)
    if spec is None:
        raise ExploreError(f"Métrica desconhecida: {metric!r}. Existem: {', '.join(sorted(METRICS))}.")
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
    }[spec.family]
    rows = resolver(spec, by, by2, date_from, date_to)

    # Série temporal sai em ordem cronológica completa; ranking sai por valor,
    # limitado e com o corte declarado.
    if by == "time":
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


def _dim_key(dim: str, *, local=None, extra=None) -> tuple[str, str]:
    """(key, label) para dimensões derivadas de um instante local."""
    if dim == "time":
        iso = local.date().isoformat()
        return iso, iso
    if dim == "hour":
        return f"{local.hour:02d}", f"{local.hour}h"
    if dim == "weekday":
        return _weekday(local)
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
            else:
                parts.append(_dim_key(dim, local=local))
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
            else:
                parts.append(_dim_key(dim, local=local))
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
