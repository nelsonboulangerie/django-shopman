"""A oferta anunciada, resolvida no CLIQUE — nunca no envio.

Uma campanha anuncia uma promoção (`Campaign.promotion_ref`). Quando o cliente toca no
link, a sacola é montada aqui. O ponto inteiro deste módulo é **quando** as perguntas são
respondidas.

## Por que resolver no clique, e não ao mandar a mensagem

Mensagem de marketing dorme horas no WhatsApp. Se a sacola fosse montada no envio:

· o **preço** envelheceria entre o envio e o clique (ADR-020 §9);
· o **estoque** seria segurado para quem nunca clicou — `cart.add_item` chama
  `_reserve_or_raise`, que toma hold no Stockman, então marketing prometeria pão a um e
  negaria a outro;
· haveria uma `Session` órfã por destinatário, que `cleanup_stale_sessions` depois varre.

Por isso a campanha **emite uma Action, não cria carrinho** — o precedente certo é o
`reorder` (`services/customer_orders.py::add_reorder_items`), que re-resolve preço no
clique, pula o que não é vendável e pula o que o Stockman recusa, devolvendo os
descartados para a superfície explicar. Este módulo é o mesmo idioma para oferta.

## Oferta com SKU e oferta sem SKU não são a mesma coisa

`Promotion.skus` vazio quer dizer "vale para tudo" — e não existe sacola de "tudo". Então:

· promoção que **nomeia** SKUs → sacola montada com um toque;
· promoção que não nomeia → link para onde ela vale, sem prometer sacola.

Fingir que os dois casos são um só produziria o pior resultado possível: um botão
"montar sacola" que não monta nada.

## O link é NÃO autenticado

Não se usa `build_access_url`: `AccessLink` expira em 5 minutos e é single-use — morreria
antes do clique. E aumentar o TTL para campanha espalharia links de concessão de sessão,
de vida longa, em históricos de conversa que são encaminhados e printados. O link carrega
a **oferta**; a autenticação acontece onde já acontece, no checkout. Ninguém precisa estar
logado para encher uma sacola.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_CHANNEL_REF = "web"


class OfferUnavailable(Exception):
    """A oferta não existe, não vale mais, ou não vale neste canal."""


@dataclass(frozen=True)
class SkippedOfferItem:
    """Um item que a oferta não conseguiu montar.

    Carrega o SKU junto do nome: sem ele a tela só conseguia CONTAR o que ficou
    de fora ("alguns itens não estavam disponíveis"), sem poder nomear nem
    oferecer o "Me avise" — o link do anúncio terminava em beco.
    """

    sku: str
    name: str


@dataclass(frozen=True)
class OfferItems:
    """O que a oferta consegue montar, e o que ela não conseguiu."""

    added: tuple[str, ...] = ()
    #: O que ficou de fora — sem venda, sem estoque, sem preço.
    skipped: tuple[SkippedOfferItem, ...] = ()

    @property
    def assembled(self) -> bool:
        return bool(self.added)


def get_offer(ref: str, *, channel_ref: str = DEFAULT_CHANNEL_REF, now=None):
    """A promoção viva com este `ref`, ou erro dizendo por quê.

    A validade é conferida AQUI e não no envio: uma relâmpago que venceu enquanto a
    mensagem dormia não pode montar sacola nenhuma.
    """
    from shopman.shop.models import Promotion

    ref = (ref or "").strip()
    if not ref:
        raise OfferUnavailable("Oferta não informada.")

    now = now or timezone.now()
    promotion = Promotion.objects.filter(ref=ref).prefetch_related("channels").first()
    if promotion is None:
        raise OfferUnavailable("Esta oferta não existe mais.")
    if not promotion.is_active:
        raise OfferUnavailable("Esta oferta foi encerrada.")
    if promotion.valid_from > now:
        raise OfferUnavailable("Esta oferta ainda não começou.")
    if promotion.valid_until < now:
        raise OfferUnavailable("Esta oferta já terminou.")
    if channel_ref and not promotion.applies_to_channel(channel_ref):
        raise OfferUnavailable("Esta oferta não vale por aqui.")
    return promotion


def offer_skus(promotion) -> tuple[str, ...]:
    """Os SKUs que a oferta nomeia, direto ou pelas coleções.

    Vazio significa "vale para tudo", e é isso que separa a oferta que monta sacola da
    que só aponta o caminho.
    """
    skus = [str(sku).strip() for sku in (promotion.skus or []) if str(sku).strip()]
    if skus:
        return tuple(dict.fromkeys(skus))

    refs = [str(ref).strip() for ref in (promotion.collections or []) if str(ref).strip()]
    if not refs:
        return ()
    return tuple(_collection_skus(refs))


def _collection_skus(collection_refs: list[str]) -> list[str]:
    """SKUs das coleções da oferta, na ordem da coleção, sem repetir.

    Pertencimento a coleção é `CollectionItem`, não `ListingItem`: listing é a vitrine
    de um canal, e a oferta não é escopada por vitrine — ela é escopada por `channels`.
    """
    from shopman.offerman.models import CollectionItem

    # Sem filtro de vendabilidade aqui de propósito: quem responde "isto se vende?" é
    # `_sellable_product`, no momento de montar. Duplicar a regra criaria dois donos para
    # a mesma pergunta, e eles divergiriam no dia em que uma delas mudasse.
    items = (
        CollectionItem.objects.filter(collection__ref__in=collection_refs)
        .select_related("product")
        .order_by("sort_order", "pk")
    )
    return list(dict.fromkeys(item.product.sku for item in items if item.product_id))


def add_offer_items(
    request,
    promotion,
    *,
    cart_service,
    channel_ref: str = DEFAULT_CHANNEL_REF,
) -> OfferItems:
    """Montar a sacola da oferta, resolvendo preço e estoque AGORA.

    Mesmo idioma do `reorder`: o que não é vendável e o que o Stockman recusa saem da
    sacola e voltam na resposta, para a tela explicar em vez de mentir.
    """
    from shopman.shop.services import customer_orders

    added: list[str] = []
    skipped: list[SkippedOfferItem] = []

    for sku in offer_skus(promotion):
        product = customer_orders._sellable_product(sku)
        if product is None:
            skipped.append(SkippedOfferItem(sku=sku, name=sku))
            continue

        try:
            cart_service.add_item(
                request,
                sku=sku,
                qty=1,
                unit_price_q=customer_orders._price_q(product, channel_ref=channel_ref),
                name=product.name,
            )
        except Exception:
            # Inclui `CartUnavailableError` (estoque recusou). Uma oferta que não pode
            # ser montada inteira ainda vale pelo que couber — melhor sacola parcial
            # explicada que erro na cara de quem clicou num anúncio.
            logger.info("offer.add_item_failed promotion=%s sku=%s", promotion.ref, sku, exc_info=True)
            skipped.append(SkippedOfferItem(sku=sku, name=product.name or sku))
            continue

        added.append(sku)

    return OfferItems(added=tuple(added), skipped=tuple(skipped))


def offer_action(promotion_ref: str) -> dict[str, Any]:
    """A `Action` da ADR-012 que monta a sacola da oferta.

    Contrato idêntico ao do `reorder` (`storefront/api/account.py::_reorder_action`),
    porque é a mesma natureza de gesto: uma mutação idempotente que enche a sacola.
    """
    return {
        "ref": "claim_offer",
        "kind": "mutation",
        "label": "Quero esta oferta",
        "priority": "primary",
        "href": f"/api/v1/offers/{promotion_ref}/claim/",
        "method": "POST",
        "payload_schema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["replace", "append"]},
                "idempotency_key": {"type": "string"},
            },
        },
        "idempotency": "required",
    }
