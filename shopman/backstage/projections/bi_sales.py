"""B.I. de vendas — leitura analítica (ADR-021, BI-PLAN §5/F4 + F6).

Série diária de pedidos/faturamento/ticket, mix por canal, top SKUs e
distribuição por hora × dia-da-semana. Fontes: ``Order``/``OrderItem`` (os
donos do fato nativo) e ``HistoricalSale``/``Item`` (histórico externo,
BI-PLAN §7) — a origem viaja no contrato (``BISalesDay.source``) e a UI
rotula o trecho histórico; nunca misturados sem rótulo.

Política de fusão: **o dia nativo vence** — um dia com pedido Shopman lê só
do Shopman; o histórico preenche os dias em que a suite não existia. Canais
históricos entram como "yooga · delivery" e "yooga · loja" (delivery é o
único rótulo confiável do sistema antigo; mesa/balcão nunca viram canal).

Atribuição temporal: ``created_at``/``occurred_at`` em data local. Pedidos
cancelados/devolvidos ficam FORA do faturamento e são contados à parte (o
export Yooga só traz vendas autorizadas — cancelado histórico não existe).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from .bi_production import _normalize_window, _previous_window, _qty


@dataclass(frozen=True)
class BISalesDay:
    date: str
    orders: int
    revenue_q: int
    average_ticket_q: int
    source: str  # "shopman" | "yooga" — a UI rotula o trecho histórico


@dataclass(frozen=True)
class BISalesChannelRow:
    channel_ref: str
    orders: int
    revenue_q: int


@dataclass(frozen=True)
class BITopSkuRow:
    sku: str
    name: str
    qty: str
    revenue_q: int


@dataclass(frozen=True)
class BISalesPrevious:
    """O período de MESMO tamanho imediatamente anterior (F7 — comparação)."""

    date_from: str
    date_to: str
    orders_total: int
    revenue_total_q: int
    average_ticket_q: int
    revenue_by_day: tuple[int, ...]  # alinhado posicionalmente com `days`


@dataclass(frozen=True)
class BISalesReport:
    date_from: str
    date_to: str
    days: tuple[BISalesDay, ...]
    by_channel: tuple[BISalesChannelRow, ...]
    top_skus: tuple[BITopSkuRow, ...]
    orders_by_hour: tuple[int, ...]  # 24 posições, hora local
    orders_by_weekday: tuple[int, ...]  # 7 posições, 0 = segunda
    orders_total: int
    revenue_total_q: int
    average_ticket_q: int
    cancelled_total: int
    historical_days: int  # dias da janela preenchidos pelo histórico (yooga)
    previous: BISalesPrevious


def build_bi_sales(
    *, date_from: date | None = None, date_to: date | None = None
) -> BISalesReport:
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import HistoricalSale, HistoricalSaleItem

    date_from, date_to = _normalize_window(date_from, date_to)
    window = _local_datetime_window(date_from, date_to)

    excluded = (Order.Status.CANCELLED, Order.Status.RETURNED)
    rows = list(
        Order.objects.filter(created_at__range=window).values_list(
            "created_at", "total_q", "channel_ref", "status"
        )
    )

    day_orders: dict[date, int] = defaultdict(int)
    day_revenue: dict[date, int] = defaultdict(int)
    channel_orders: dict[str, int] = defaultdict(int)
    channel_revenue: dict[str, int] = defaultdict(int)
    by_hour = [0] * 24
    by_weekday = [0] * 7
    cancelled = 0
    for created_at, total_q, channel_ref, status in rows:
        if status in excluded:
            cancelled += 1
            continue
        local = timezone.localtime(created_at)
        day_orders[local.date()] += 1
        day_revenue[local.date()] += total_q
        channel_orders[channel_ref] += 1
        channel_revenue[channel_ref] += total_q
        by_hour[local.hour] += 1
        by_weekday[local.weekday()] += 1

    # Histórico preenche só os dias em que o Shopman não vendeu (o dia nativo
    # vence — nunca somar as duas fontes num mesmo dia).
    native_days = set(day_orders)
    historical = HistoricalSale.objects.filter(occurred_at__range=window).values_list(
        "occurred_at", "total_q", "is_delivery"
    )
    hist_days: set[date] = set()
    for occurred_at, total_q, is_delivery in historical:
        local = timezone.localtime(occurred_at)
        if local.date() in native_days:
            continue
        hist_days.add(local.date())
        day_orders[local.date()] += 1
        day_revenue[local.date()] += total_q
        channel = "yooga · delivery" if is_delivery else "yooga · loja"
        channel_orders[channel] += 1
        channel_revenue[channel] += total_q
        by_hour[local.hour] += 1
        by_weekday[local.weekday()] += 1

    days = []
    day = date_from
    while day <= date_to:
        orders = day_orders.get(day, 0)
        revenue = day_revenue.get(day, 0)
        days.append(
            BISalesDay(
                date=day.isoformat(),
                orders=orders,
                revenue_q=revenue,
                average_ticket_q=revenue // orders if orders else 0,
                source="yooga" if day in hist_days else "shopman",
            )
        )
        day += timedelta(days=1)

    orders_total = sum(day_orders.values())
    revenue_total = sum(day_revenue.values())

    return BISalesReport(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        days=tuple(days),
        by_channel=tuple(
            BISalesChannelRow(channel_ref=ref, orders=channel_orders[ref], revenue_q=channel_revenue[ref])
            for ref in sorted(channel_orders, key=lambda ref: -channel_revenue[ref])
        ),
        top_skus=_top_skus(
            OrderItem,
            HistoricalSaleItem,
            window=window,
            excluded=excluded,
            native_days=native_days,
        ),
        orders_by_hour=tuple(by_hour),
        orders_by_weekday=tuple(by_weekday),
        orders_total=orders_total,
        revenue_total_q=revenue_total,
        average_ticket_q=revenue_total // orders_total if orders_total else 0,
        cancelled_total=cancelled,
        historical_days=len(hist_days),
        previous=_sales_previous(date_from, date_to),
    )


def _sales_previous(date_from: date, date_to: date) -> BISalesPrevious:
    """Totais e série do período anterior, com a MESMA regra de fusão do
    principal (dia nativo vence) — o teste de consistência compara os dois."""
    from shopman.orderman.models import Order

    from shopman.backstage.models import HistoricalSale

    prev_from, prev_to = _previous_window(date_from, date_to)
    window = _local_datetime_window(prev_from, prev_to)
    excluded = (Order.Status.CANCELLED, Order.Status.RETURNED)

    day_orders: dict[date, int] = defaultdict(int)
    day_revenue: dict[date, int] = defaultdict(int)
    native = Order.objects.filter(created_at__range=window).values_list(
        "created_at", "total_q", "status"
    )
    for created_at, total_q, status in native:
        if status in excluded:
            continue
        local_day = timezone.localtime(created_at).date()
        day_orders[local_day] += 1
        day_revenue[local_day] += total_q

    native_days = set(day_orders)
    historical = HistoricalSale.objects.filter(occurred_at__range=window).values_list(
        "occurred_at", "total_q"
    )
    for occurred_at, total_q in historical:
        local_day = timezone.localtime(occurred_at).date()
        if local_day in native_days:
            continue
        day_orders[local_day] += 1
        day_revenue[local_day] += total_q

    series = []
    day = prev_from
    while day <= prev_to:
        series.append(day_revenue.get(day, 0))
        day += timedelta(days=1)

    orders_total = sum(day_orders.values())
    revenue_total = sum(day_revenue.values())
    return BISalesPrevious(
        date_from=prev_from.isoformat(),
        date_to=prev_to.isoformat(),
        orders_total=orders_total,
        revenue_total_q=revenue_total,
        average_ticket_q=revenue_total // orders_total if orders_total else 0,
        revenue_by_day=tuple(series),
    )


def _top_skus(
    order_item_model,
    historical_item_model,
    *,
    window,
    excluded,
    native_days: set[date],
    limit: int = 10,
) -> tuple[BITopSkuRow, ...]:
    # Chave = sku quando existe; item histórico sem sku agrega pelo nome (7%
    # do export — produto fora do catálogo atual não pode sumir do ranking).
    qty_by_key: dict[str, Decimal] = defaultdict(Decimal)
    revenue_by_key: dict[str, int] = defaultdict(int)
    name_by_key: dict[str, str] = {}
    sku_by_key: dict[str, str] = {}

    def _fold(sku: str, name: str, qty, line_total_q: int) -> None:
        key = sku or f"nome:{name}"
        qty_by_key[key] += qty
        revenue_by_key[key] += line_total_q
        name_by_key[key] = name
        sku_by_key[key] = sku

    rows = order_item_model.objects.filter(order__created_at__range=window).exclude(
        order__status__in=excluded
    ).values_list("sku", "name", "qty", "line_total_q")
    for sku, name, qty, line_total_q in rows:
        _fold(sku, name, qty, line_total_q)

    historical = historical_item_model.objects.filter(
        sale__occurred_at__range=window
    ).values_list("sale__occurred_at", "sku", "product_name", "qty", "line_total_q")
    for occurred_at, sku, name, qty, line_total_q in historical:
        if timezone.localtime(occurred_at).date() in native_days:
            continue  # o dia nativo vence também no ranking
        _fold(sku, name, qty, line_total_q)

    top = sorted(revenue_by_key, key=lambda key: -revenue_by_key[key])[:limit]
    return tuple(
        BITopSkuRow(
            sku=sku_by_key[key],
            name=name_by_key[key],
            qty=_qty(qty_by_key[key]),
            revenue_q=revenue_by_key[key],
        )
        for key in top
    )


def _local_datetime_window(date_from: date, date_to: date):
    from datetime import datetime, time

    tz = timezone.get_current_timezone()
    return (
        datetime.combine(date_from, time.min, tzinfo=tz),
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz),
    )
