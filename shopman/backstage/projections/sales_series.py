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

Quantas vendas do dia foram em dinheiro mora aqui pelo mesmo motivo: é a mesma
conciliação, e a previsão de troco não pode ler o passado por um caminho que
discorde do painel.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from django.utils import timezone


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
    """
    from shopman.orderman.models import Order

    from shopman.backstage.models import HistoricalSale

    from .bi_sales import _local_datetime_window

    window = _local_datetime_window(since, until)
    excluded = (Order.Status.CANCELLED, Order.Status.RETURNED)

    revenue: dict[date, int] = defaultdict(int)
    orders: dict[date, int] = defaultdict(int)
    cash_orders: dict[date, int] = defaultdict(int)
    payments_known: dict[date, int] = defaultdict(int)

    # As chaves do pagamento saem por transform de JSON e não pelo blob inteiro:
    # dois anos de pedidos nativos com o `data` completo na memória seria caro
    # sem necessidade — o que se quer aqui são dois escalares por venda.
    for created_at, total_q, status, method, cash_received_q in Order.objects.filter(
        created_at__range=window
    ).values_list(
        "created_at",
        "total_q",
        "status",
        "data__payment__method",
        "data__payment__cash_received_q",
    ):
        if status in excluded:
            continue
        day = timezone.localtime(created_at).date()
        revenue[day] += total_q
        orders[day] += 1
        if method:
            payments_known[day] += 1
            if _is_cash(method, cash_received_q):
                cash_orders[day] += 1

    native_days = set(orders)
    # A origem vem do campo, não de um literal: dado de demonstração carimbado
    # como "seed" não pode aparecer na tela com o nome de um export real.
    historical_source: dict[date, str] = {}
    for occurred_at, total_q, source, payment in HistoricalSale.objects.filter(
        occurred_at__range=window
    ).values_list("occurred_at", "total_q", "source", "payment"):
        day = timezone.localtime(occurred_at).date()
        if day in native_days:
            continue
        historical_source.setdefault(day, source)
        revenue[day] += total_q
        orders[day] += 1
        if payment:
            payments_known[day] += 1
            if _historical_is_cash(payment):
                cash_orders[day] += 1

    return {
        day: DailySales(
            revenue_q=revenue[day],
            orders=orders[day],
            source=historical_source.get(day, "shopman"),
            cash_orders=cash_orders.get(day, 0),
            payments_known=payments_known.get(day, 0),
        )
        for day in orders
    }


def _is_cash(method, cash_received_q) -> bool:
    """A venda nativa teve dinheiro em espécie?

    Duas assinaturas, porque há dois jeitos de o dinheiro entrar. ``method``
    responde pela venda simples e pelo dinheiro na entrega (que o balcão nem
    chega a receber, mas cujo troco sai da mesma gaveta). ``cash_received_q``
    responde pelo pagamento misto, em que o método vira ``"mixed"`` e a parcela
    em espécie só aparece na soma das linhas.
    """
    return str(method or "").strip().lower() == "cash" or int(cash_received_q or 0) > 0


def _historical_is_cash(payment: str) -> bool:
    """A venda do export externo foi em dinheiro.

    O campo é texto cru do sistema de origem e pode listar mais de uma forma
    ("DINHEIRO, CARTÃO"). Basta haver dinheiro na linha: uma venda parcialmente
    em espécie ainda é uma venda que pode ter pedido troco.
    """
    text = unicodedata.normalize("NFKD", payment).encode("ascii", "ignore").decode()
    return "DINHEIRO" in text.upper()
