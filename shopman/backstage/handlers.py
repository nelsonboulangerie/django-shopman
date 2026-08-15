"""Receivers do backstage.

Hoje um só assunto: observar quando um produto deixa (ou volta) de estar
disponível para oferecer. O que muda essa resposta é estoque ou reserva, então
é neles que se escuta — sempre **depois do commit**, para que a leitura enxergue
o estado já gravado e não o de meio de transação.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def on_move_for_shelf_outage(sender, instance, **kwargs) -> None:
    sku = getattr(getattr(instance, "quant", None), "sku", None)
    if sku:
        _observe_after_commit(sku)


def on_hold_for_shelf_outage(sender, instance, **kwargs) -> None:
    sku = getattr(instance, "sku", None)
    if sku:
        _observe_after_commit(sku)


def _observe_after_commit(sku: str) -> None:
    from django.db import transaction

    from shopman.backstage.services import shelf_outages

    transaction.on_commit(lambda: shelf_outages.observe(sku))
