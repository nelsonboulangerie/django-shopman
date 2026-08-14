"""B.I. de vendas — leitura analítica (ADR-021, BI-PLAN §5/F4).

Série diária de pedidos/faturamento/ticket, mix por canal, top SKUs e
distribuição por hora × dia-da-semana. Fonte: ``Order``/``OrderItem`` (os
donos do fato); tudo calculado na leitura, sem tabela de agregação.

Atribuição temporal: ``created_at`` em data local (quando a venda nasceu).
Pedidos cancelados/devolvidos ficam FORA do faturamento e são contados à
parte — número escondido é número que mente.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from .bi_production import _normalize_window, _qty


@dataclass(frozen=True)
class BISalesDay:
    date: str
    orders: int
    revenue_q: int
    average_ticket_q: int


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


def build_bi_sales(
    *, date_from: date | None = None, date_to: date | None = None
) -> BISalesReport:
    from shopman.orderman.models import Order, OrderItem

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
        top_skus=_top_skus(OrderItem, window=window, excluded=excluded),
        orders_by_hour=tuple(by_hour),
        orders_by_weekday=tuple(by_weekday),
        orders_total=orders_total,
        revenue_total_q=revenue_total,
        average_ticket_q=revenue_total // orders_total if orders_total else 0,
        cancelled_total=cancelled,
    )


def _top_skus(order_item_model, *, window, excluded, limit: int = 10) -> tuple[BITopSkuRow, ...]:
    qty_by_sku: dict[str, Decimal] = defaultdict(Decimal)
    revenue_by_sku: dict[str, int] = defaultdict(int)
    name_by_sku: dict[str, str] = {}
    rows = order_item_model.objects.filter(order__created_at__range=window).exclude(
        order__status__in=excluded
    ).values_list("sku", "name", "qty", "line_total_q")
    for sku, name, qty, line_total_q in rows:
        qty_by_sku[sku] += qty
        revenue_by_sku[sku] += line_total_q
        name_by_sku[sku] = name
    top = sorted(revenue_by_sku, key=lambda sku: -revenue_by_sku[sku])[:limit]
    return tuple(
        BITopSkuRow(
            sku=sku,
            name=name_by_sku[sku],
            qty=_qty(qty_by_sku[sku]),
            revenue_q=revenue_by_sku[sku],
        )
        for sku in top
    )


def _local_datetime_window(date_from: date, date_to: date):
    from datetime import datetime, time

    tz = timezone.get_current_timezone()
    return (
        datetime.combine(date_from, time.min, tzinfo=tz),
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=tz),
    )
