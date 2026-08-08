"""
Product feed — o 🛰 Feed de plataforma (``google``/``meta``), RSS 2.0 público.

Um canal de exibição com formato declarado (``Channel`` com
``commerce_policy="display"`` e ``display.format`` em ``google_merchant``/
``meta_catalog``) compõe N coleções; cada coleção vira o ``custom_label_0`` do produto
(o análogo das smart collections p/ anúncios — Google custom_labels, Meta product
sets). Pull: Google Merchant e Meta buscam a URL agendado (ambos aceitam o XML
``g:``). O único campo que diverge é ``availability`` — Google usa underscore, Meta
usa espaço; o formato do canal decide.

**O preço vem do canal apontado por ``display.prices_from``** (a loja online, porque
é lá que quem clicou compra), não de ``Product.base_price_q``. Ver
``services/display_prices.py``. Este é o feed PÚBLICO — Google e Meta precisam
buscá-lo sem credencial —, e é justamente por isso que o preço nele tem de ser o
preço que a loja honra.

Spec verificada (2026-07-01): support.google.com/merchants/answer/7052112 (Google) +
facebook.com/business/help/120325381656392 (Meta). Detalhes em
docs/plans/CATALOG-FEEDS-GOOGLE-META.md.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

logger = logging.getLogger(__name__)

# availability diverge por plataforma (verificado): Google underscore, Meta espaço.
_AVAILABILITY = {
    "google_merchant": {True: "in_stock", False: "out_of_stock"},
    "meta_catalog": {True: "in stock", False: "out of stock"},
}


class ProductFeedError(Exception):
    pass


def _resolve_feed_channel(ref: str):
    """Canal de exibição COM formato declarado. Sem formato é menuboard, não feed."""
    from shopman.shop.models import Channel

    channel = Channel.objects.filter(
        ref=ref, is_active=True, commerce_policy=Channel.CommercePolicy.DISPLAY
    ).first()
    if channel is None:
        raise ProductFeedError("not a display channel")
    fmt = ((channel.config or {}).get("display") or {}).get("format") or ""
    if fmt not in _AVAILABILITY:
        raise ProductFeedError(f"display channel has no feed format: {fmt!r}")
    return channel, fmt


def _storefront_base(request) -> str:
    base = getattr(settings, "SHOPMAN_STOREFRONT_URL", "") or ""
    return (base or request.build_absolute_uri("/")).rstrip("/")


def build_feed_items(ref: str, request) -> list[dict]:
    """Itens do feed a partir das coleções do canal. Formatação = camada de view."""
    from shopman.offerman.models import Collection

    from shopman.shop.services.display_prices import resolve_prices

    channel, fmt = _resolve_feed_channel(ref)
    display = (channel.config or {}).get("display") or {}
    collection_refs = list(display.get("collections") or [])
    paused = set(display.get("paused_skus") or [])  # pausa LOCAL (a global é do produto)
    avail = _AVAILABILITY[fmt]
    base = _storefront_base(request)

    colls = {c.ref: c for c in Collection.objects.filter(ref__in=collection_refs)}

    # Preço de todos de uma vez: o feed inteiro numa consulta, não uma por item.
    everything = [
        product
        for coll_ref in collection_refs
        if (coll := colls.get(coll_ref)) is not None
        for product in coll.product_queryset()
    ]
    prices = resolve_prices(channel, everything)

    items: list[dict] = []
    seen: set[str] = set()
    for coll_ref in collection_refs:
        coll = colls.get(coll_ref)
        if coll is None:
            continue
        for product in coll.product_queryset():
            if product.sku in seen or not product.image_url:
                # dedupe (1ª coleção do feed vence o custom_label); item sem
                # imagem é omitido (image_link é obrigatório — seria reprovado).
                continue
            seen.add(product.sku)
            available = product.is_published and product.is_sellable and product.sku not in paused
            items.append({
                "id": product.sku,
                "title": product.name[:150],
                "description": (product.long_description or product.short_description or product.name)[:5000],
                "link": f"{base}/produto/{product.sku}",
                "image_link": product.image_url,
                "availability": avail[available],
                "price": f"{prices.get(product.sku, product.base_price_q) / 100:.2f} BRL",
                "product_type": coll.name,
                "custom_label_0": coll.ref,
            })
    return items


class ProductFeedView(View):
    """Saída RSS 2.0 pública (Google/Meta) de um canal de exibição com formato."""

    def get(self, request, ref: str):
        try:
            items = build_feed_items(ref, request)
        except ProductFeedError as exc:
            raise Http404(str(exc)) from exc

        brand = ""
        try:
            from shopman.shop.models import Shop

            shop = Shop.objects.only("name").first()
            brand = shop.name if shop else ""
        except Exception:
            logger.debug("product_feed.brand_lookup_failed", exc_info=True)

        content = render(
            request,
            "feed/products.xml",
            {"ref": ref, "brand": brand, "items": items, "link": _storefront_base(request)},
        ).content
        return HttpResponse(content, content_type="application/xml; charset=utf-8")
