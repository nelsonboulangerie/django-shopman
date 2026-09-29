"""Directives do iFood Merchant e o gatilho de "a loja mudou o horário".

Mesmo padrão durável do ``ifood.status_callback`` e da projeção de catálogo
(ADR-003): o gesto grava local e enfileira; o handler atravessa a rede com retry.

* ``ifood.merchant_sync`` — grava horário semanal + interrupções do calendário.
  Uma viva por vez (dedupe fixo): dez saves seguidos da loja viram uma gravação.
* ``ifood.merchant_interruption`` — cria ou retira a pausa do gestor.

Só são registrados com ``SHOPMAN_IFOOD["merchant_sync_enabled"]`` ligado.
"""

from __future__ import annotations

import logging

from django.db import transaction
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import IFOOD_MERCHANT_INTERRUPTION, IFOOD_MERCHANT_SYNC
from shopman.shop.services import ifood_merchant

logger = logging.getLogger(__name__)


class IFoodMerchantSyncHandler:
    topic = IFOOD_MERCHANT_SYNC

    def handle(self, *, message: Directive, ctx: dict) -> None:
        try:
            result = ifood_merchant.sync_store()
        except ifood_merchant.MerchantAPIError as exc:
            error = DirectiveTransientError if exc.retryable else DirectiveTerminalError
            raise error(str(exc)) from exc
        logger.info(
            "ifood_merchant.sync: skipped=%s hours_written=%s created=%s removed=%s failed=%s",
            result.skipped or "-",
            result.hours_written,
            result.created,
            result.removed,
            result.failed,
        )


class IFoodMerchantInterruptionHandler:
    topic = IFOOD_MERCHANT_INTERRUPTION

    def handle(self, *, message: Directive, ctx: dict) -> None:
        pk = (message.payload or {}).get("interruption_pk")
        if not pk:
            logger.warning("ifood_merchant.interruption: directive sem interruption_pk: %s", message.payload)
            return
        try:
            ifood_merchant.apply_interruption(int(pk))
        except ifood_merchant.MerchantAPIError as exc:
            error = DirectiveTransientError if exc.retryable else DirectiveTerminalError
            raise error(str(exc)) from exc


def on_shop_saved(sender, instance, **kwargs) -> None:
    """A loja foi salva (horário, calendário…): regravar no iFood depois do commit.

    Liga sem ``sender`` e filtra pela instância porque o Admin salva a loja por
    proxies (``ShopOperation`` e irmãos), e ``post_save`` de proxy chega com o
    proxy como sender — ``sender=Shop`` perderia justamente a tela do horário.
    """
    from shopman.shop.models import Shop

    if not isinstance(instance, Shop) or kwargs.get("raw"):
        return
    transaction.on_commit(lambda: ifood_merchant.enqueue_sync("shop_saved"), robust=True)


__all__ = ["IFoodMerchantSyncHandler", "IFoodMerchantInterruptionHandler", "on_shop_saved"]
