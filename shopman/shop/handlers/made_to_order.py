"""Handlers da baixa de insumo do item feito na hora (ADR-040).

Dois topics, um service (``services/made_to_order.py``):

- ``stock.consume_made_to_order``: a venda baixa o insumo da ficha;
- ``stock.settle_made_to_order_cancellation``: o cancelamento devolve o que não
  foi preparado e registra como perda o que foi.

Exceção sobe: a directive volta para a fila com retry, e cada efeito roda numa
transação só, então a nova tentativa não encontra meio efeito.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive

from shopman.shop.directives import (
    STOCK_CONSUME_MADE_TO_ORDER,
    STOCK_SETTLE_MADE_TO_ORDER_CANCELLATION,
)

logger = logging.getLogger(__name__)


def _order_for(message: Directive):
    from shopman.orderman.models import Order

    order_ref = (message.payload or {}).get("order_ref")
    if not order_ref:
        return None
    order = Order.objects.filter(ref=order_ref).first()
    if order is None:
        logger.info("%s: pedido %s não existe mais", message.topic, order_ref)
    return order


class MadeToOrderConsumeHandler:
    """Baixa o insumo da venda do item feito na hora. Topic: stock.consume_made_to_order"""

    topic = STOCK_CONSUME_MADE_TO_ORDER

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.services import made_to_order

        order = _order_for(message)
        if order is not None:
            made_to_order.consume(order)


class MadeToOrderCancellationHandler:
    """Acerta o insumo da venda cancelada. Topic: stock.settle_made_to_order_cancellation"""

    topic = STOCK_SETTLE_MADE_TO_ORDER_CANCELLATION

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.services import made_to_order

        order = _order_for(message)
        if order is not None:
            made_to_order.settle_cancellation(order)
