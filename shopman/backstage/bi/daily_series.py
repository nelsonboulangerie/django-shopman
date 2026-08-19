"""Materializa a série diária a partir da camada canônica (P3).

Dois verbos, um contrato:

- ``refresh(date_from, date_to)`` recomputa o intervalo pela canônica e
  regrava — **apaga o intervalo e escreve de novo**, um dia por linha,
  inclusive os dias sem venda (presença = cobertura). ``refresh_all()`` faz o
  mesmo do primeiro dia com venda até hoje, depois de zerar a tabela: é o
  botão de "recomputar do zero", e é barato (segundos).
- ``materialized(since, until)`` devolve a série lida da tabela **só se todos
  os dias do intervalo estiverem cobertos**; senão ``None`` — e quem lê cai
  para o cálculo ao vivo (o mesmo caminho de sempre). Assim, um ambiente onde
  ninguém rodou o refresh continua certo, só mais lento; nunca inventa zero.

Quem chama o refresh: o ``maintenance_worker`` (ciclo de 300 s, últimos dias),
o fim do ``ingest_yooga`` e o fim do ``seed`` (o passado mudou; o passado
materializado tem de mudar junto).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

#: O que o worker recomputa a cada ciclo: hoje, ontem e anteontem. Ontem porque
#: o dia fecha depois da meia-noite; anteontem por folga para pedido corrigido.
DEFAULT_RECENT_DAYS = 3


def refresh(date_from: date, date_to: date) -> int:
    """Recomputa ``[date_from, date_to]`` e regrava. Devolve quantos dias gravou."""
    from shopman.backstage.bi.canonical import iter_days, read_sales
    from shopman.backstage.models import DailySalesFact

    if date_to < date_from:
        return 0
    window = read_sales(date_from, date_to)

    revenue: dict[date, int] = {}
    orders: dict[date, int] = {}
    cash: dict[date, int] = {}
    known: dict[date, int] = {}
    source: dict[date, str] = {}
    for sale in window.sales:
        revenue[sale.day] = revenue.get(sale.day, 0) + sale.total_q
        orders[sale.day] = orders.get(sale.day, 0) + 1
        source.setdefault(sale.day, sale.source)
        if sale.payment_known:
            known[sale.day] = known.get(sale.day, 0) + 1
            if sale.is_cash:
                cash[sale.day] = cash.get(sale.day, 0) + 1

    rows = [
        DailySalesFact(
            date=day,
            source=source.get(day, ""),
            revenue_q=revenue.get(day, 0),
            orders=orders.get(day, 0),
            cash_orders=cash.get(day, 0),
            payments_known=known.get(day, 0),
            historical_dropped=window.historical_dropped.get(day, 0),
        )
        for day in iter_days(date_from, date_to)
    ]
    with transaction.atomic():
        DailySalesFact.objects.filter(date__range=(date_from, date_to)).delete()
        DailySalesFact.objects.bulk_create(rows, batch_size=1000)
    return len(rows)


def refresh_recent(days: int = DEFAULT_RECENT_DAYS) -> int:
    today = timezone.localdate()
    return refresh(today - timedelta(days=days - 1), today)


def refresh_all() -> int:
    """Zera e recomputa do primeiro dia com venda (qualquer fonte) até hoje."""
    from shopman.backstage.models import DailySalesFact

    first = earliest_sale_day()
    today = timezone.localdate()
    with transaction.atomic():
        DailySalesFact.objects.all().delete()
        if first is None:
            return 0
        return refresh(first, today)


def earliest_sale_day() -> date | None:
    """O primeiro dia com venda em qualquer fonte, em data local."""
    from shopman.orderman.models import Order

    from shopman.backstage.models import HistoricalSale

    candidates = [
        Order.objects.order_by("created_at").values_list("created_at", flat=True).first(),
        HistoricalSale.objects.order_by("occurred_at").values_list("occurred_at", flat=True).first(),
    ]
    stamps = [timezone.localtime(stamp).date() for stamp in candidates if stamp is not None]
    return min(stamps) if stamps else None


def materialized(since: date, until: date):
    """A série lida da tabela, ou ``None`` se algum dia do intervalo não foi coberto."""
    from shopman.backstage.models import DailySalesFact
    from shopman.backstage.projections.sales_series import DailySales

    if until < since:
        return {}
    expected = (until - since).days + 1
    rows = list(
        DailySalesFact.objects.filter(date__range=(since, until)).values_list(
            "date", "source", "revenue_q", "orders", "cash_orders", "payments_known"
        )
    )
    if len(rows) != expected:
        logger.info(
            "bi.daily_series: %s..%s não materializado por inteiro (%d de %d dias); calculando ao vivo",
            since, until, len(rows), expected,
        )
        return None
    return {
        day: DailySales(
            revenue_q=revenue_q,
            orders=orders,
            source=source,
            cash_orders=cash_orders,
            payments_known=payments_known,
        )
        for day, source, revenue_q, orders, cash_orders, payments_known in rows
        if orders  # dia sem venda não aparece: ausência não é zero
    }
