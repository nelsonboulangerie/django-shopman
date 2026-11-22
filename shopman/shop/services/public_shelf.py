"""O aviso público da vitrine, só quando o ESTADO PÚBLICO de um SKU muda (#2784).

O canal cru de estoque (``stock-<canal>``) leva cada venda e cada entrada de lote, com
o SKU: aberto ao público, entregaria o ritmo da loja (ADR-018 §5.1). Por isso a loja
viva (WP-L04) recebia só um aviso SEM conteúdo, no máximo um a cada 5 s, e toda página
aberta relia a cada aviso, mesmo quando a mudança não a afetava.

Aqui o shop publica ``shelf-<canal>`` com o SKU, e só quando muda o que a vitrine já
mostra a qualquer visitante desse SKU:

- o estado do card (pode pedir, últimas unidades, fornada planejada, indisponível);
- quantas unidades restam, só quando o card mostra "últimas unidades";
- o DIA da promessa (hoje, ou o dia da próxima fornada).

Dez vendas que não mudam nada disso não geram aviso: o aviso diz o que qualquer um já
vê, e não conta vendas. A comparação é com a última assinatura publicada, guardada em
cache por canal e SKU; sem lembrança (cache vazio, reinício), o primeiro aviso sai, e
um aviso a mais é barato, uma página velha não.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.core.cache import cache

logger = logging.getLogger(__name__)

#: Quanto tempo a última assinatura publicada fica lembrada.
SIGNATURE_TTL_SECONDS = 24 * 60 * 60

#: O evento do canal público.
SHELF_EVENT = "shelf-update"

#: Os canais de venda que têm vitrine pública (quem ouve ``shelf-<canal>``). Quem
#: registra é a superfície pública, no boot (o storefront, que é quem sabe o canal
#: dele): o shop não lê configuração de loja por settings (ADR-042) e, assim, não
#: gasta leitura de disponibilidade em canal que ninguém ouve (balcão, iFood).
_PUBLIC_CHANNELS: set[str] = set()


def register_public_channel(channel_ref: str) -> None:
    """A superfície pública avisa que ``channel_ref`` tem vitrine aberta ao visitante."""
    if channel_ref:
        _PUBLIC_CHANNELS.add(channel_ref)


def public_channels() -> frozenset[str]:
    return frozenset(_PUBLIC_CHANNELS)


def shelf_channel(channel_ref: str) -> str:
    """O canal público da vitrine de um canal de venda."""
    return f"shelf-{channel_ref}"


def _signature_key(channel_ref: str, sku: str) -> str:
    return f"shelf-signature:{channel_ref}:{sku}"


def public_signature(sku: str, *, channel_ref: str) -> tuple:
    """O que a vitrine mostra de ``sku`` neste canal, numa tupla comparável.

    Lê pelos MESMOS caminhos do cardápio: a disponibilidade do canal
    (``catalog_context.availability_for_sku`` + ``basic_availability``, com o limiar de
    "últimas unidades" do canal) e o dia da promessa (``ready_promise``).
    """
    from shopman.shop.config import ChannelConfig
    from shopman.shop.projections import catalog_context
    from shopman.shop.projections.ready_promise import read_promise_facts

    raw = catalog_context.availability_for_sku(sku, channel_ref=channel_ref)
    threshold = Decimal(str(ChannelConfig.for_channel(channel_ref).stock.low_stock_threshold))
    basic = catalog_context.basic_availability(raw, is_sellable=True, low_stock_threshold=threshold)
    remaining = basic.available_qty if basic.status == "low_stock" else None

    facts = read_promise_facts([sku], channel_ref=channel_ref)
    if facts.today_orderable.get(sku, True):
        promise_day = facts.today.isoformat()
    else:
        next_day = facts.next_batch.get(sku)
        promise_day = next_day.isoformat() if next_day else ""
    return (basic.status, remaining, promise_day)


def bundles_using(sku: str) -> list[str]:
    """Os pacotes que levam ``sku``: o estado público deles anda com o do item.

    "Restam 2 pacotes" pode virar "Resta 1" sem o estado público do pão mudar; por
    isso o aviso de um item reavalia também os pacotes que o usam, cada um com o
    próprio SKU.
    """
    from shopman.offerman.models import ProductComponent

    return list(
        ProductComponent.objects.filter(component__sku=sku)
        .values_list("parent__sku", flat=True)
        .distinct()
    )


def changed_channels(sku: str, channel_refs: list[str]) -> list[str]:
    """Os canais PÚBLICOS em que o estado de ``sku`` mudou desde o último aviso.

    Só olha os canais com vitrine pública registrada; os outros nem são lidos. Guarda a
    assinatura nova de cada canal. Falha ao ler um canal conta como mudança (o aviso a
    mais é barato; a página velha, não) e não lembra nada desse canal.
    """
    changed: list[str] = []
    for ref in [ref for ref in channel_refs if ref in _PUBLIC_CHANNELS]:
        key = _signature_key(ref, sku)
        try:
            signature = public_signature(sku, channel_ref=ref)
        except Exception:
            logger.warning("public_shelf.signature_failed sku=%s channel=%s", sku, ref, exc_info=True)
            cache.delete(key)
            changed.append(ref)
            continue
        if cache.get(key) == list(signature):
            continue
        cache.set(key, list(signature), SIGNATURE_TTL_SECONDS)
        changed.append(ref)
    return changed
