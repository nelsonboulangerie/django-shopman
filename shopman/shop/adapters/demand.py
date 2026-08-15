"""Backend de demanda que enxerga o esgotamento.

O backend do craftsman responde "quanto vendeu por dia" lendo os pedidos. Isso
basta enquanto houve produto o dia inteiro — e mente no dia em que acabou:
vender 20 pães e fechar às 10h da manhã não significa que a procura era 20.

A fórmula de sugestão já sabia lidar com isso (``DailyDemand.soldout_at`` e a
extrapolação por taxa de venda), mas ninguém preenchia o campo. Quem sabe a
hora em que a prateleira zerou é o ledger de estoque, e quem pode ler pedidos e
estoque na mesma frase é o orquestrador. Por isso esta composição mora aqui, e
não dentro de um core.

Sem isso o efeito é cumulativo e perverso: o produto que esgota toda quinta
ensina que quinta vende pouco, a sugestão manda produzir pouco, e a falta se
perpetua sozinha.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, timedelta

from django.utils import timezone
from shopman.craftsman import OrderingDemandBackend
from shopman.craftsman.protocols.demand import DailyDemand

logger = logging.getLogger(__name__)


class LedgerAwareDemandBackend(OrderingDemandBackend):
    """``OrderingDemandBackend`` + a hora de esgotamento vinda do ledger."""

    def history(
        self,
        product_ref: str,
        days: int = 28,
        same_weekday: bool = True,
        *,
        target_date: date,
        exclude_dates: frozenset[date] = frozenset(),
    ) -> list[DailyDemand]:
        rows = super().history(
            product_ref,
            days=days,
            same_weekday=same_weekday,
            target_date=target_date,
            exclude_dates=exclude_dates,
        )
        if not rows:
            return rows

        soldout = _soldout_times(product_ref, days=days)
        if not soldout:
            return rows
        return [
            replace(row, soldout_at=soldout[row.date])
            if row.date in soldout
            else row
            for row in rows
        ]


def _soldout_times(sku: str, *, days: int) -> dict[date, object]:
    """Hora em que cada dia da janela terminou sem produto na prateleira.

    Degrada para vazio em qualquer falha: sem a hora, a sugestão volta a contar
    só o que vendeu — perde precisão, nunca inventa demanda.
    """
    from shopman.stockman.services.queries import StockQueries

    today = timezone.localdate()
    try:
        history = StockQueries.shelf_history(
            [sku], since=today - timedelta(days=days), until=today - timedelta(days=1)
        )
    except Exception:
        logger.debug("shelf_history indisponível para %s", sku, exc_info=True)
        return {}

    # .time() e não .timetz(): o instante já vem em hora local, e a fórmula
    # compara com o horário da loja, que é naive. Misturar aware e naive ali
    # levantaria no meio do cálculo.
    return {
        day: shelf.soldout_at.time()
        for day, shelf in history.get(sku, {}).items()
        if shelf.soldout_at is not None
    }
