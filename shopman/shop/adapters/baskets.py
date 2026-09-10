"""Fronteira do orquestrador com as cestas que ensinam afinidade.

Duas fontes, e elas moram em lugares diferentes: os pedidos nativos são do
Orderman (o orquestrador alcança), e o histórico externo é do backstage (só a
camada de adapter alcança — a regra de dependência abre exceção aqui, como já
acontece com o KDS e com os episódios).

Degrada para vazio: sem histórico legível, a afinidade se calcula só com os
pedidos nativos e o motor de sugestão segue funcionando com menos precisão.
Nunca o contrário.

⚠️ **Uma venda é uma cesta; a quantidade não conta.** Levar seis baguetes não
diz mais sobre o que combina com baguete do que levar uma — diz sobre o apetite,
que é outra pergunta. O que a afinidade lê é a companhia.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Basket:
    """Uma venda, reduzida ao que a afinidade precisa: quando, e com quem."""

    skus: frozenset[str]
    occurred_at: datetime


def native_orders(*, since: datetime) -> Iterator[Basket]:
    """Cestas dos pedidos do próprio sistema, desde ``since``.

    Cancelado e devolvido ficam de fora: o cliente desfez a companhia, e ela
    não devia ensinar nada.
    """
    from shopman.orderman.models import Order

    orders = (
        Order.objects.filter(created_at__gte=since)
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])
        .prefetch_related("items")
        .iterator(chunk_size=500)
    )
    for order in orders:
        skus = frozenset(item.sku for item in order.items.all() if item.sku)
        if len(skus) >= 2:
            yield Basket(skus=skus, occurred_at=order.created_at)


def historical_sales(*, since: datetime) -> Iterator[Basket]:
    """Cestas do histórico externo importado (dois anos de Yooga).

    Linha sem SKU resolvido não entra: a afinidade fala de produto do catálogo,
    e um nome solto do sistema antigo não é um produto — é uma string.
    """
    try:
        from shopman.backstage.models import HistoricalSale
    except Exception:  # pragma: no cover — backstage ausente do deployment
        logger.debug("baskets: histórico externo indisponível; seguindo sem ele.")
        return

    sales = (
        HistoricalSale.objects.filter(occurred_at__gte=since)
        .prefetch_related("items")
        .iterator(chunk_size=500)
    )
    for sale in sales:
        skus = frozenset(item.sku for item in sale.items.all() if item.sku)
        if len(skus) >= 2:
            yield Basket(skus=skus, occurred_at=sale.occurred_at)


#: Ordem em que as fontes são lidas. Trocável por settings
#: (``SHOPMAN_AFFINITY_BASKET_SOURCES``) para um deployment sem histórico.
DEFAULT_SOURCES = (
    "shopman.shop.adapters.baskets.native_orders",
    "shopman.shop.adapters.baskets.historical_sales",
)


def all_baskets(*, since: datetime) -> Iterator[Basket]:
    """Todas as cestas de todas as fontes configuradas."""
    from importlib import import_module

    from django.conf import settings

    paths = getattr(settings, "SHOPMAN_AFFINITY_BASKET_SOURCES", DEFAULT_SOURCES)
    for path in paths:
        module_path, _, name = path.rpartition(".")
        try:
            source = getattr(import_module(module_path), name)
        except (ImportError, AttributeError):
            logger.warning("baskets: fonte '%s' não carrega; seguindo sem ela.", path)
            continue
        try:
            yield from source(since=since)
        except Exception:
            # Uma fonte quebrada não pode derrubar o cálculo das outras: a
            # afinidade fica menos precisa, não ausente.
            logger.warning("baskets: fonte '%s' falhou; seguindo sem ela.", path, exc_info=True)
