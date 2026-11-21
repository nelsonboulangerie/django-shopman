"""Releitura da vitrine no prazo de uma reserva (``stock.shelf_recheck``, #2785).

O agendamento e a regra moram em :mod:`shopman.shop.services.shelf_recheck`; aqui só a
hora de agir: cedo demais volta para a fila, e na hora publica o ``stock-update`` de cada
SKU que teve uma reserva de fato vencida na janela.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone
from shopman.orderman.models import Directive

from shopman.shop.directives import STOCK_SHELF_RECHECK


class ShelfRecheckHandler:
    """Topic: ``stock.shelf_recheck``."""

    topic = STOCK_SHELF_RECHECK

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.handlers._sse_emitters import _emit_for_sku
        from shopman.shop.services.shelf_recheck import BUCKET_SECONDS, lapsed_within

        at = datetime.fromisoformat(message.payload["at"])
        if timezone.is_naive(at):
            at = timezone.make_aware(at)
        now = timezone.now()
        if now < at:
            # Cedo demais (relógio do worker): volta para a fila na hora certa.
            message.status = "queued"
            message.available_at = at
            message.save(update_fields=["status", "available_at", "updated_at"])
            return
        start = at - timedelta(seconds=BUCKET_SECONDS)
        for sku in message.payload.get("skus") or []:
            if sku and lapsed_within(str(sku), start, now):
                _emit_for_sku(str(sku), event_type="stock-update")
