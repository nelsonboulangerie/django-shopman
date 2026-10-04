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

#: As bases do "Comparar com" das Vendas (prévia ``depois-bi-vendas``, pino 5): o
#: período de mesmo tamanho logo antes (padrão) e o mesmo período um ano antes.
COMPARE_PREVIOUS = "previous"
COMPARE_YEAR = "year"
COMPARE_BASES = (COMPARE_PREVIOUS, COMPARE_YEAR)


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
    #: O nome que o operador fala ("PDV", "Loja online"); o histórico vem com a
    #: fonte e o tipo ("Histórico Yooga · loja"). Nunca a chave crua.
    name: str
    #: O tipo do canal, para o ícone: ``counter`` · ``web`` · ``whatsapp`` ·
    #: ``marketplace`` · ``historical`` · ``other``.
    kind: str
    orders: int
    revenue_q: int


@dataclass(frozen=True)
class BISalesChannelOption:
    """Um chip de canal: todo canal com venda na janela, antes do recorte."""

    ref: str
    name: str
    kind: str


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
    #: O recorte de canal aplicado (vazio = todos) e os canais que o chip oferece.
    channel: str
    channels: tuple[BISalesChannelOption, ...]
    #: A base escolhida no "Comparar com" (``previous`` ou ``year``).
    compare: str
    #: Dias da semana sem expediente regular (0 = segunda): o gráfico diz "fechado".
    closed_weekdays: tuple[int, ...]


def build_bi_sales(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    channel: str = "",
    compare: str = "",
) -> BISalesReport:
    from shopman.backstage.bi.canonical import iter_days, read_sales

    date_from, date_to = _normalize_window(date_from, date_to)
    compare_key = compare if compare in COMPARE_BASES else COMPARE_PREVIOUS
    full = read_sales(date_from, date_to)
    names = _channel_names()
    options = _channel_options(full.sales, names)
    channel_key = channel if any(option.ref == channel for option in options) else ""
    window = _only_channel(full, channel_key)

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
            BISalesChannelRow(
                channel_ref=ref,
                name=_channel_label(ref, names),
                kind=_channel_kind(ref, names),
                orders=channel_orders[ref],
                revenue_q=channel_revenue[ref],
            )
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
        previous=_sales_previous(date_from, date_to, channel=channel_key, compare=compare_key),
        channel=channel_key,
        channels=options,
        compare=compare_key,
        closed_weekdays=_closed_weekdays(),
    )


def _compare_window(date_from: date, date_to: date, compare: str) -> tuple[date, date]:
    if compare == COMPARE_YEAR:
        return _year_before(date_from), _year_before(date_to)
    return _previous_window(date_from, date_to)


def _year_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29/02
        return day.replace(year=day.year - 1, day=28)


def _sales_previous(
    date_from: date, date_to: date, *, channel: str = "", compare: str = COMPARE_PREVIOUS
) -> BISalesPrevious:
    """Totais e série da base de comparação, pela MESMA leitura conciliada do
    principal (e com o mesmo recorte de canal): o teste de consistência compara os dois."""
    from shopman.backstage.bi.canonical import iter_days, read_sales

    prev_from, prev_to = _compare_window(date_from, date_to, compare)
    day_orders: dict[date, int] = defaultdict(int)
    day_revenue: dict[date, int] = defaultdict(int)
    for sale in _only_channel(read_sales(prev_from, prev_to), channel).sales:
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


# ── Canais ───────────────────────────────────────────────────────────────────


def _only_channel(window, channel: str):
    """A janela só com as vendas de um canal (vazio = todas). As linhas acompanham."""
    if not channel:
        return window
    from dataclasses import replace

    kept = tuple(sale for sale in window.sales if sale.channel_key == channel)
    keys = {(sale.source, sale.key) for sale in kept}
    narrowed = replace(window, sales=kept)
    original_lines = window.lines

    def lines():
        return [line for line in original_lines() if (line.source, line.sale_key) in keys]

    object.__setattr__(narrowed, "lines", lines)
    return narrowed


def _channel_names() -> dict[str, tuple[str, str]]:
    """ref → (nome, tipo) dos canais cadastrados. Falha de leitura = vazio."""
    try:
        from shopman.shop.models import Channel

        out = {}
        for channel in Channel.objects.all().only("ref", "name", "config"):
            out[channel.ref] = (channel.name or channel.ref, _kind_from_channel(channel))
        return out
    except Exception:
        return {}


def _kind_from_channel(channel) -> str:
    from django.conf import settings

    ref = channel.ref
    if ref == getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv"):
        return "counter"
    if ref == "ifood":
        return "marketplace"
    if ref == "whatsapp":
        return "whatsapp"
    if ref == getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web"):
        return "web"
    return "other"


def _channel_label(ref: str, names: dict[str, tuple[str, str]]) -> str:
    if ref in names:
        return names[ref][0]
    if " · " in ref:
        source, kind = ref.split(" · ", 1)
        return f"Histórico {source.capitalize()} · {kind}"
    return ref


def _channel_kind(ref: str, names: dict[str, tuple[str, str]]) -> str:
    if ref in names:
        return names[ref][1]
    if " · " in ref:
        return "historical"
    return "other"


def _channel_options(sales, names: dict[str, tuple[str, str]]) -> tuple[BISalesChannelOption, ...]:
    revenue: dict[str, int] = defaultdict(int)
    for sale in sales:
        revenue[sale.channel_key] += sale.total_q
    return tuple(
        BISalesChannelOption(ref=ref, name=_channel_label(ref, names), kind=_channel_kind(ref, names))
        for ref in sorted(revenue, key=lambda ref: -revenue[ref])
    )


def _closed_weekdays() -> tuple[int, ...]:
    try:
        from shopman.shop.services.business_calendar import closed_weekdays

        return tuple(closed_weekdays())
    except Exception:
        return ()
