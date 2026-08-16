"""Quanto a casa vendeu em cada dia — dono único da série diária.

Duas fontes contam o mesmo passado: os pedidos nativos e o histórico externo
importado. A regra que as concilia é **o dia nativo vence** — num dia em que o
Shopman registrou venda, o histórico não entra, nunca se somam. Um pedido de
teste num dia antigo apaga o histórico daquele dia, e é assim de propósito: a
alternativa (somar) contaria a mesma venda duas vezes.

Esta regra estava inline em cada leitura que precisava dela. Uma cópia a mais
seria o suficiente para o mesmo dia aparecer com dois números em duas telas — e
o painel de vendas e a tela de "o que esperar" discordarem sobre ontem é
exatamente o tipo de erro que destrói a confiança no B.I. inteiro.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from django.utils import timezone


@dataclass(frozen=True)
class DailySales:
    revenue_q: int
    orders: int
    source: str  # "shopman" | "yooga"


def daily_sales(since: date, until: date) -> dict[date, DailySales]:
    """{data: venda do dia} em ``[since, until]``.

    **Dia sem venda registrada não aparece no dicionário.** Ausência não é zero:
    um dia sobre o qual não há registro (a casa não abriu, ou o período é
    anterior ao sistema) não pode entrar numa média como um dia de faturamento
    zero. Quem lê decide o que fazer com a lacuna — e tem como saber que ela
    existe.
    """
    from shopman.orderman.models import Order

    from shopman.backstage.models import HistoricalSale

    from .bi_sales import _local_datetime_window

    window = _local_datetime_window(since, until)
    excluded = (Order.Status.CANCELLED, Order.Status.RETURNED)

    revenue: dict[date, int] = defaultdict(int)
    orders: dict[date, int] = defaultdict(int)

    for created_at, total_q, status in Order.objects.filter(
        created_at__range=window
    ).values_list("created_at", "total_q", "status"):
        if status in excluded:
            continue
        day = timezone.localtime(created_at).date()
        revenue[day] += total_q
        orders[day] += 1

    native_days = set(orders)
    # A origem vem do campo, não de um literal: dado de demonstração carimbado
    # como "seed" não pode aparecer na tela com o nome de um export real.
    historical_source: dict[date, str] = {}
    for occurred_at, total_q, source in HistoricalSale.objects.filter(
        occurred_at__range=window
    ).values_list("occurred_at", "total_q", "source"):
        day = timezone.localtime(occurred_at).date()
        if day in native_days:
            continue
        historical_source.setdefault(day, source)
        revenue[day] += total_q
        orders[day] += 1

    return {
        day: DailySales(
            revenue_q=revenue[day],
            orders=orders[day],
            source=historical_source.get(day, "shopman"),
        )
        for day in orders
    }
