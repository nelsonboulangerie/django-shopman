"""A virada do dia reenvia o inventário local ao Google (WP-G14c, issue #2655).

O ``pickupSla`` de cada item sai do dia da promessa da Loja
(``projections/ready_promise``), e esse dia muda sem que nada no estoque mude:

- **no corte**: a grade de retirada de hoje acaba (casa fechada, último horário
  passado), e o item que era "pronto hoje" passa a ser "pronto amanhã";
- **à meia-noite local**: o item da fornada de amanhã passa a ser de hoje.

Nenhum dos dois gera sinal de estoque, e sem reenvio o Google ficaria com o
``SAME_DAY`` das 10h até a reconciliação de 24h, a mesma divergência com a página
do produto que nega a "retirada no mesmo dia".

Aqui não há relógio novo: o ``sync_platform_catalogs``, que já roda a cada volta do
``maintenance_worker``, pergunta em que **fase** o dia está (a data local e se a
grade de hoje ainda tem horário) e, quando a fase mudou desde a última volta,
reenfileira os itens visíveis do canal pelo mesmo caminho dos gestos do Gestor
(``enqueue_display_skus``). A fase da última volta fica no cache compartilhado;
cache perdido conta como virada, e o custo é um reenvio a mais.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

CACHE_KEY = "shopman:pickup_turn:{ref}"
CACHE_TTL_SECONDS = 3 * 24 * 3600
TRIGGER = "day_turn"

OPEN = "open"
CLOSED = "closed"


def current_phase(*, now: datetime | None = None) -> str:
    """``"AAAA-MM-DD:open"`` enquanto hoje ainda tem horário de retirada; ``:closed`` depois do corte."""
    from shopman.shop.projections.ready_promise import PromiseFacts

    now = now or timezone.now()
    today = timezone.localtime(now).date() if timezone.is_aware(now) else now.date()
    has_window = bool(PromiseFacts(now=now, today=today).grid(today))
    return f"{today.isoformat()}:{OPEN if has_window else CLOSED}"


def visible_skus(ref: str) -> list[str]:
    """Os SKUs do canal que levam inventário local: na composição, publicados e não ocultos aqui."""
    from shopman.offerman.models import Product

    from shopman.shop.services import display_catalog

    channel, _fmt = display_catalog.resolve_channel(ref)
    hidden = set(((channel.config or {}).get("display") or {}).get("hidden_skus") or [])
    composition = [sku for sku in display_catalog.composition_skus(ref) if sku not in hidden]
    published = set(Product.objects.filter(sku__in=composition, is_published=True).values_list("sku", flat=True))
    return [sku for sku in composition if sku in published]


def resend_on_turn(ref: str, *, now: datetime | None = None) -> int:
    """Reenfileira os itens visíveis de ``ref`` quando a fase do dia virou. Devolve quantos."""
    from shopman.shop.handlers.catalog_projection import enqueue_display_skus

    phase = current_phase(now=now)
    key = CACHE_KEY.format(ref=ref)
    if cache.get(key) == phase:
        return 0
    from shopman.shop.models import CatalogSyncState

    skus = visible_skus(ref)
    # O que já está na fila sai com a retirada nova: o envio lê o estado na hora.
    queued = set(
        CatalogSyncState.objects.filter(channel_ref=ref, sku__in=skus, status="pending").values_list("sku", flat=True)
    )
    count = enqueue_display_skus(ref, [sku for sku in skus if sku not in queued], trigger=TRIGGER)
    cache.set(key, phase, CACHE_TTL_SECONDS)
    logger.info("pickup_turn: %s virou para %s, %d item(ns) reenfileirado(s)", ref, phase, count)
    return count
