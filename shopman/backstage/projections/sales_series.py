"""Quanto a casa vendeu em cada dia — dono único da série diária.

Duas fontes contam o mesmo passado: os pedidos nativos e o histórico externo
importado. A regra que as concilia — **o dia nativo vence** — mora na camada
canônica (``bi/canonical.py``), num lugar só; aqui a venda conciliada vira a
série diária que a projeção, o painel de vendas e a previsão de troco leem.
Se duas telas discordassem sobre ontem, a confiança no B.I. inteiro iria junto.

Quantas vendas do dia foram em dinheiro mora aqui pelo mesmo motivo: é a mesma
conciliação, e a previsão de troco não pode ler o passado por um caminho que
discorde do painel. Cada fonte responde pela sua própria noção de "dinheiro
em espécie" e de "forma conhecida" (adaptadores em ``bi/sources``); a série só
soma. Zero conhecido é ausência, não zero.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DailySales:
    revenue_q: int
    orders: int
    source: str  # "shopman" | "yooga"
    # Quantas vendas do dia foram em dinheiro, e sobre quantas se sabe a forma de
    # pagamento. Os dois números andam juntos porque a resposta útil é a
    # PROPORÇÃO: o histórico externo às vezes vem sem forma de pagamento, e
    # dividir por `orders` nesse caso diria "nenhuma venda em dinheiro" quando o
    # certo é "não sabemos como pagaram". Zero conhecido é ausência, não zero.
    cash_orders: int
    payments_known: int


def daily_sales(since: date, until: date) -> dict[date, DailySales]:
    """{data: venda do dia} em ``[since, until]``.

    **Dia sem venda registrada não aparece no dicionário.** Ausência não é zero:
    um dia sobre o qual não há registro (a casa não abriu, ou o período é
    anterior ao sistema) não pode entrar numa média como um dia de faturamento
    zero. Quem lê decide o que fazer com a lacuna — e tem como saber que ela
    existe.

    A conciliação nativo × histórico ("o dia nativo vence") mora na camada
    canônica (``bi/canonical.py``); aqui só se dobra por dia.
    """
    from shopman.backstage.bi.canonical import read_sales

    revenue: dict[date, int] = defaultdict(int)
    orders: dict[date, int] = defaultdict(int)
    cash_orders: dict[date, int] = defaultdict(int)
    payments_known: dict[date, int] = defaultdict(int)
    source: dict[date, str] = {}
    for sale in read_sales(since, until).sales:
        revenue[sale.day] += sale.total_q
        orders[sale.day] += 1
        source.setdefault(sale.day, sale.source)
        if sale.payment_known:
            payments_known[sale.day] += 1
            if sale.is_cash:
                cash_orders[sale.day] += 1

    return {
        day: DailySales(
            revenue_q=revenue[day],
            orders=orders[day],
            source=source[day],
            cash_orders=cash_orders.get(day, 0),
            payments_known=payments_known.get(day, 0),
        )
        for day in orders
    }
