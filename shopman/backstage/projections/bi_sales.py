"""B.I. de vendas — leitura analítica (ADR-021, BI-PLAN §5/F4 + F6).

Série diária de pedidos/faturamento/ticket, mix por canal, top produtos e
distribuição por hora × dia-da-semana. Lê a **camada canônica**
(``bi/canonical.py``): o pedido nativo e o histórico externo já chegam aqui
como a mesma coisa, conciliados pela regra "o dia nativo vence", e a origem
viaja no contrato (``BISalesDay.source``, ``sources``, ``source_conflicts``)
para a UI rotular o trecho histórico — nunca misturados sem rótulo.

Canais históricos entram como "yooga · delivery" e "yooga · loja" (delivery é
o único rótulo confiável do sistema antigo; mesa/balcão nunca viram canal).
Pedidos cancelados/devolvidos ficam FORA do faturamento e são contados à
parte (o export Yooga só traz vendas autorizadas — cancelado histórico não
existe).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

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
class BISourceConflict:
    """Dia em que o nativo venceu e apagou histórico relevante — declarado, não mudo.

    Um pedido de teste num dia antigo apaga ~110 vendas do Yooga daquele dia.
    A regra é essa de propósito (somar contaria a mesma venda duas vezes); o
    que não pode é acontecer sem ninguém ver.
    """

    date: str
    native_orders: int
    historical_dropped: int
    source: str


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
    sources: tuple[str, ...]  # fontes que entraram na janela — hora e dia da semana as somam
    source_conflicts: tuple[BISourceConflict, ...]
    previous: BISalesPrevious


def build_bi_sales(
    *, date_from: date | None = None, date_to: date | None = None
) -> BISalesReport:
    from shopman.backstage.bi.canonical import iter_days, read_sales

    date_from, date_to = _normalize_window(date_from, date_to)
    window = read_sales(date_from, date_to)

    day_orders: dict[date, int] = defaultdict(int)
    day_revenue: dict[date, int] = defaultdict(int)
    channel_orders: dict[str, int] = defaultdict(int)
    channel_revenue: dict[str, int] = defaultdict(int)
    by_hour = [0] * 24
    by_weekday = [0] * 7
    for sale in window.sales:
        day_orders[sale.day] += 1
        day_revenue[sale.day] += sale.total_q
        channel_orders[sale.channel_key] += 1
        channel_revenue[sale.channel_key] += sale.total_q
        by_hour[sale.occurred_at.hour] += 1
        by_weekday[sale.occurred_at.weekday()] += 1

    days = []
    for day in iter_days(date_from, date_to):
        orders = day_orders.get(day, 0)
        revenue = day_revenue.get(day, 0)
        days.append(
            BISalesDay(
                date=day.isoformat(),
                orders=orders,
                revenue_q=revenue,
                average_ticket_q=revenue // orders if orders else 0,
                source=window.historical_days.get(day, "shopman"),
            )
        )

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
        top_skus=_top_skus(window),
        orders_by_hour=tuple(by_hour),
        orders_by_weekday=tuple(by_weekday),
        orders_total=orders_total,
        revenue_total_q=revenue_total,
        average_ticket_q=revenue_total // orders_total if orders_total else 0,
        cancelled_total=window.cancelled_native,
        historical_days=len(window.historical_days),
        sources=window.sources,
        source_conflicts=tuple(
            BISourceConflict(
                date=conflict.day.isoformat(),
                native_orders=conflict.native_orders,
                historical_dropped=conflict.historical_dropped,
                source=conflict.source,
            )
            for conflict in window.source_conflicts
        ),
        previous=_sales_previous(date_from, date_to),
    )


def _sales_previous(date_from: date, date_to: date) -> BISalesPrevious:
    """Totais e série do período anterior, pela MESMA leitura conciliada do
    principal — o teste de consistência compara os dois."""
    from shopman.backstage.bi.canonical import iter_days, read_sales

    prev_from, prev_to = _previous_window(date_from, date_to)
    day_orders: dict[date, int] = defaultdict(int)
    day_revenue: dict[date, int] = defaultdict(int)
    for sale in read_sales(prev_from, prev_to).sales:
        day_orders[sale.day] += 1
        day_revenue[sale.day] += sale.total_q

    orders_total = sum(day_orders.values())
    revenue_total = sum(day_revenue.values())
    return BISalesPrevious(
        date_from=prev_from.isoformat(),
        date_to=prev_to.isoformat(),
        orders_total=orders_total,
        revenue_total_q=revenue_total,
        average_ticket_q=revenue_total // orders_total if orders_total else 0,
        revenue_by_day=tuple(day_revenue.get(day, 0) for day in iter_days(prev_from, prev_to)),
    )


def _top_skus(window, *, limit: int = 10) -> tuple[BITopSkuRow, ...]:
    # A chave é a do produto canônico: catálogo (junta Yooga e nativo quando o
    # de-para existe), SKU da fonte, ou o nome — 7% do export não tem SKU e
    # produto fora do catálogo atual não pode sumir do ranking.
    qty_by_key: dict[str, Decimal] = defaultdict(Decimal)
    revenue_by_key: dict[str, int] = defaultdict(int)
    name_by_key: dict[str, str] = {}
    sku_by_key: dict[str, str] = {}
    for line in window.lines():
        key = line.product_key
        qty_by_key[key] += line.qty
        revenue_by_key[key] += line.line_total_q
        name_by_key[key] = line.name
        sku_by_key[key] = line.product_ref or line.external_sku

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
