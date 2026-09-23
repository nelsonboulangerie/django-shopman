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


def _catalog_sku_by_external() -> dict[str, str]:
    """SKU da origem → SKU do catálogo, pelo de-para confirmado.

    O histórico guarda o código como o Yooga o escreveu, e isso não se
    reescreve. Quem traduz é o ``ProductAlias``, pelo FK — então a tradução
    acompanha o catálogo mesmo quando ele troca de código.
    """
    try:
        from shopman.backstage.models import ProductAlias
    except Exception:  # pragma: no cover — backstage ausente do deployment
        return {}
    return dict(
        ProductAlias.objects.confirmed()
        .exclude(product__isnull=True)
        .exclude(external_sku="")
        .values_list("external_sku", "product__sku")
    )


def historical_sales(*, since: datetime) -> Iterator[Basket]:
    """Cestas do histórico externo importado (dois anos de Yooga).

    Linha sem SKU resolvido não entra: a afinidade fala de produto do catálogo,
    e um nome solto do sistema antigo não é um produto — é uma string.

    ⚠️ O código vem traduzido pelo de-para, e não cru. Sem isso, o par
    ``(CT, PC)`` do histórico e o par ``(CRO, PCHOC)`` de hoje seriam produtos
    diferentes na mesma tabela — e a vitrine, que pergunta pelo código do
    catálogo, perderia dois anos de cesta sem erro nenhum. Antes de 23/09/2026
    os dois códigos coincidiam, e a falta passava despercebida.
    """
    try:
        from shopman.backstage.models import HistoricalSale
    except Exception:  # pragma: no cover — backstage ausente do deployment
        logger.debug("baskets: histórico externo indisponível; seguindo sem ele.")
        return

    de_para = _catalog_sku_by_external()
    sales = (
        HistoricalSale.objects.filter(occurred_at__gte=since)
        .prefetch_related("items")
        .iterator(chunk_size=500)
    )
    for sale in sales:
        skus = frozenset(
            de_para.get(item.sku, item.sku) for item in sale.items.all() if item.sku
        )
        if len(skus) >= 2:
            yield Basket(skus=skus, occurred_at=sale.occurred_at)


#: Ordem em que as fontes são lidas. Trocável por settings
#: (``SHOPMAN_AFFINITY_BASKET_SOURCES``) para um deployment sem histórico.
DEFAULT_SOURCES = (
    "shopman.shop.adapters.baskets.native_orders",
    "shopman.shop.adapters.baskets.historical_sales",
)


def all_baskets(*, since: datetime, failures: list[str] | None = None) -> Iterator[Basket]:
    """Todas as cestas de todas as fontes configuradas.

    ``failures`` recebe o caminho de cada fonte que não entregou tudo. Quem
    chama decide o que fazer com isso — e o ``compute_product_affinity`` recusa
    gravar a tabela a partir de leitura parcial.

    ⚠️ **Uma fonte que morre NO MEIO não é uma fonte ausente.** A fonte que
    nem carrega deixa a afinidade menos precisa; a que quebra depois de já ter
    entregue metade deixa uma tabela que PARECE completa. Aconteceu em
    23/09/2026: o cursor de servidor cai contra o pool em modo transação
    (pgbouncer), e duas execuções seguidas leram 12.625 e 4.087 cestas das
    26.590 que existiam — as duas gravaram, as duas com aviso só no log, e os
    números passaram por medição. O remédio de operação é
    ``DATABASE_DISABLE_SERVER_SIDE_CURSORS=true`` (o alpha já a define); o
    remédio de código é esta lista.
    """
    from importlib import import_module

    from django.conf import settings

    paths = getattr(settings, "SHOPMAN_AFFINITY_BASKET_SOURCES", DEFAULT_SOURCES)
    for path in paths:
        module_path, _, name = path.rpartition(".")
        try:
            source = getattr(import_module(module_path), name)
        except (ImportError, AttributeError):
            logger.warning("baskets: fonte '%s' não carrega; seguindo sem ela.", path)
            if failures is not None:
                failures.append(path)
            continue
        try:
            yield from source(since=since)
        except Exception:
            # Uma fonte quebrada não pode derrubar o cálculo das outras: a
            # afinidade fica menos precisa, não ausente. Mas quem chama precisa
            # SABER, senão "menos precisa" vira "errada sem avisar".
            logger.warning("baskets: fonte '%s' falhou; seguindo sem ela.", path, exc_info=True)
            if failures is not None:
                failures.append(path)
