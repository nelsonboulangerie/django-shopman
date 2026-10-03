"""O estoque nos canais de fora: iFood, catálogo da Meta e feed do Google/Meta.

A loja e o PDV já tratam o esgotado (a loja bloqueia e oferece "Me avise", o PDV
mostra o selo). Os canais de fora olhavam só publicado/vendável, nunca o estoque:
o iFood seguia ``AVAILABLE`` e o pedido entrava para ser recusado. Aqui mora a
resposta única que eles passam a consultar.

**A regra é a do portão de pedido** (:func:`availability.decide` com uma unidade),
a mesma que recusa o pedido quando ele chega. Assim o canal mostra disponível
exatamente quando o pedido seria aceito, sem uma segunda régua:

- produto sem rastreio de estoque (nenhum quant) segue disponível;
- política ``demand_ok`` segue disponível;
- fornada planejada que a política ``planned_ok`` aceita conta como disponível;
- kit é limitado pelo componente que acabar.

Desta resposta só vale a **falta de estoque**. Pausa (global, do canal, ou a
pausa local do feed) já é lida pelas flags do produto e da listagem, e continua
vencendo: produto pausado segue indisponível com estoque cheio. Ausência na
listagem do canal de origem também não é falta, e não muda nada aqui.

Leitura que falha responde "tem estoque": ausência de resposta não é resposta,
e tirar um produto do ar por um erro de consulta é pior que manter o de antes.

**De onde vem o estoque.** Canal transacional (iFood) lê o próprio escopo. Canal
de exibição (catálogo da Meta, feed) não vende: lê o estoque do canal para onde
manda o cliente, o mesmo ``display.prices_from`` de onde tira o preço.

**Quando o canal de fora fica sabendo.** O feed é lido pela plataforma, então a
resposta é calculada na hora da leitura. Os canais empurrados (iFood, catálogo
da Meta) recebem a diretiva ``catalog.project_sku`` quando a oferta do produto
vira, no mesmo instante em que o ``ShelfOutage`` registra a passagem por zero e
a volta (evento de estoque/reserva e reconciliação periódica).
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# Motivos do portão que significam "acabou". Os demais (pausa, fora da listagem)
# já são lidos por outras flags e não são assunto deste módulo.
STOCK_SHORTAGE_REASONS = frozenset({"insufficient_supply", "insufficient_stock"})


def stock_channel_ref(channel_ref: str) -> str:
    """O canal cujo estoque responde por ``channel_ref``.

    Canal de exibição com ``display.prices_from`` lê o estoque do canal apontado
    (onde quem clicou compra); qualquer outro lê o próprio.
    """
    try:
        from shopman.shop.models import Channel
        from shopman.shop.services.display_prices import price_source_ref

        channel = Channel.objects.filter(ref=channel_ref).first()
        if channel is not None and channel.commerce_policy == Channel.CommercePolicy.DISPLAY:
            return price_source_ref(channel) or channel_ref
    except Exception:
        logger.debug("external_availability.stock_channel_ref degraded", exc_info=True)
    return channel_ref


def in_stock(sku: str, *, channel_ref: str) -> bool:
    """O canal de fora pode mostrar este SKU como disponível, pelo estoque?"""
    from shopman.shop.services import availability

    source = stock_channel_ref(channel_ref)
    try:
        decision = availability.decide(sku, Decimal("1"), channel_ref=source)
    except Exception:
        logger.warning(
            "external_availability.in_stock lookup failed sku=%s channel=%s",
            sku, source, exc_info=True,
        )
        return True
    if decision.get("approved"):
        return True
    return decision.get("reason_code") not in STOCK_SHORTAGE_REASONS


def in_stock_map(skus: list[str], *, channel_ref: str) -> dict[str, bool]:
    """:func:`in_stock` para vários SKUs do mesmo canal."""
    return {sku: in_stock(sku, channel_ref=channel_ref) for sku in dict.fromkeys(skus)}


def projection_refs_stocked_by(channel_ref: str) -> list[str]:
    """Canais empurrados (backend de projeção) cujo estoque vem de ``channel_ref``."""
    from shopman.offerman.conf import get_projection_backend_channels

    return [
        ref for ref in get_projection_backend_channels()
        if stock_channel_ref(ref) == channel_ref
    ]


def on_offer_changed(sku: str, *, channel_ref: str) -> None:
    """A oferta de ``sku`` em ``channel_ref`` virou: reenvia aos canais empurrados.

    Idempotente: enquanto a diretiva anterior do mesmo SKU e canal ainda está na
    fila, a nova se junta a ela; e o handler lê o estado na hora de enviar, então
    zerar e voltar em seguida converge para o estado final.
    """
    refs = projection_refs_stocked_by(channel_ref)
    if not refs:
        return
    from shopman.shop.handlers.catalog_projection import enqueue_project

    for ref in refs:
        enqueue_project(sku, ref, trigger="stock_changed")
