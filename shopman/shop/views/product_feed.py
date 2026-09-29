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

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

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
        ref=ref, commerce_policy=Channel.CommercePolicy.DISPLAY
    ).first()
    if channel is None:
        raise ProductFeedError("not a display channel")
    fmt = ((channel.config or {}).get("display") or {}).get("format") or ""
    if fmt not in _AVAILABILITY:
        raise ProductFeedError(f"display channel has no feed format: {fmt!r}")
    return channel, fmt


def _storefront_base() -> str:
    """Base da LOJA, onde o produto tem página — nunca o host que serviu o feed.

    Lia ``SHOPMAN_STOREFRONT_URL``, um setting que não existe (o da casa é
    ``SHOPMAN_STOREFRONT_BASE_URL``, via ``storefront_links``), e caía no host da
    própria requisição. O feed é servido pelo Django headless, que não tem página
    de produto: em 22/09/2026 os 48 itens do ``google-shopping`` no ar apontavam para
    ``https://api.boulangerie.com.br/produto/<sku>``, que responde 404. Merchant
    Center reprova item cuja landing page não abre.

    Sem a base configurada não há link certo para dar, e um feed com link errado é
    pior que feed nenhum: falha fechado.
    """
    from shopman.shop.services.storefront_links import storefront_base_url

    base = storefront_base_url()
    if not base:
        raise ProductFeedError("SHOPMAN_STOREFRONT_BASE_URL vazio: o feed não tem para onde mandar o cliente")
    return base


def build_feed_items(ref: str) -> list[dict]:
    """Itens do feed a partir das coleções do canal. Formatação = camada de view."""
    from shopman.offerman import get_social_attributes
    from shopman.offerman.models import Collection

    from shopman.shop.services.channel_switch import effective_active
    from shopman.shop.services.display_prices import resolve_prices
    from shopman.shop.services.storefront_links import path_product

    channel, fmt = _resolve_feed_channel(ref)
    switched_on = effective_active(channel)
    display = (channel.config or {}).get("display") or {}
    collection_refs = list(display.get("collections") or [])
    paused = set(display.get("paused_skus") or [])  # pausa LOCAL (a global é do produto)
    avail = _AVAILABILITY[fmt]
    base = _storefront_base()

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
            attributes = get_social_attributes(product)
            # Feed desligado no Gestor: todo item sai FORA DE ESTOQUE, e não some.
            # Google e Meta param de anunciar item sem estoque, sem penalidade, e o
            # item volta a rodar assim que o feed é religado. Tirar o item (feed
            # vazio) apagaria o produto na plataforma — religar viraria cadastro
            # novo, com nova revisão; e um 404 faria a busca agendada falhar, com a
            # plataforma seguindo a anunciar a última versão que conseguiu ler.
            available = (
                switched_on
                and product.is_published
                and product.is_sellable
                and product.sku not in paused
            )
            items.append({
                "id": product.sku,
                "title": product.name[:150],
                "description": (product.long_description or product.short_description or product.name)[:5000],
                "link": f"{base}{path_product(product.sku)}",
                "image_link": product.image_url,
                "brand": attributes.brand,
                "gtin": attributes.gtin,
                "mpn": attributes.mpn,
                "condition": attributes.condition,
                "google_product_category": attributes.google_product_category,
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
            items = build_feed_items(ref)
        except ProductFeedError as exc:
            raise Http404(str(exc)) from exc

        from shopman.shop.models import Shop

        # Loja ausente usa a referência no título; erro de banco não vira feed válido.
        shop = Shop.objects.only("name").first()
        brand = shop.name if shop else ""

        content = render(
            request,
            "feed/products.xml",
            {"ref": ref, "brand": brand, "items": items, "link": _storefront_base()},
        ).content
        return HttpResponse(content, content_type="application/xml; charset=utf-8")
