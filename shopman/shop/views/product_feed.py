"""
Product feed — o 🛰 Feed de plataforma (``google``/``meta``), RSS 2.0 público.

Traduz para o XML ``g:`` a decisão de ``services/display_catalog`` (quem entra, preço,
disponível, oculto). Pull: Google Merchant e Meta buscam a URL agendado (ambos aceitam
o XML ``g:``). O que diverge entre as plataformas é a grafia: ``availability`` (Google
usa underscore, Meta usa espaço) e o Ocultar (``excluded_destination`` no Google,
``status=archived`` na Meta, campo fora da especificação do Google e por isso sem o
prefixo ``g:``, developers.facebook.com/docs/marketing-api/catalog/reference).

Este é o feed PÚBLICO — Google e Meta precisam buscá-lo sem credencial —, e é
justamente por isso que o preço nele tem de ser o preço que a loja honra.

⚠️ Vida curta: o envio pela API (``docs/plans/CATALOG-PUSH-GOOGLE-META-PLAN.md``)
substitui este feed como escritor único de cada plataforma.

Spec verificada (2026-07-01): support.google.com/merchants/answer/7052112 (Google) +
facebook.com/business/help/120325381656392 (Meta). Detalhes em
docs/plans/completed/CATALOG-FEEDS-GOOGLE-META.md.
"""

from __future__ import annotations

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

from shopman.shop.services import display_catalog

# availability diverge por plataforma (verificado): Google underscore, Meta espaço.
_AVAILABILITY = {
    "google_merchant": {True: "in_stock", False: "out_of_stock"},
    "meta_catalog": {True: "in stock", False: "out of stock"},
}


def build_feed_items(ref: str) -> list[dict]:
    """Itens do feed na grafia do formato do canal."""
    _channel, fmt = display_catalog.resolve_channel(ref)
    avail = _AVAILABILITY[fmt]
    excluded = tuple(feed for feed, _api in display_catalog.GOOGLE_DESTINATIONS)
    return [
        {
            "id": item.sku,
            "title": item.title,
            "description": item.description,
            "link": item.link,
            "image_link": item.image_link,
            "brand": item.brand,
            "gtin": item.gtin,
            "mpn": item.mpn,
            "condition": item.condition,
            "google_product_category": item.google_product_category,
            "availability": avail[item.available],
            "price": f"{item.price_q / 100:.2f} BRL",
            "product_type": item.product_type,
            "custom_label_0": item.custom_label_0,
            "excluded_destinations": excluded if item.hidden and fmt == "google_merchant" else (),
            "status": "archived" if item.hidden and fmt == "meta_catalog" else "",
        }
        for item in display_catalog.display_items(ref)
    ]


class ProductFeedView(View):
    """Saída RSS 2.0 pública (Google/Meta) de um canal de exibição com formato."""

    def get(self, request, ref: str):
        try:
            items = build_feed_items(ref)
        except display_catalog.DisplayCatalogError as exc:
            raise Http404(str(exc)) from exc

        from shopman.shop.models import Shop

        # Loja ausente usa a referência no título; erro de banco não vira feed válido.
        shop = Shop.objects.only("name").first()
        brand = shop.name if shop else ""

        content = render(
            request,
            "feed/products.xml",
            {"ref": ref, "brand": brand, "items": items, "link": display_catalog.storefront_base()},
        ).content
        return HttpResponse(content, content_type="application/xml; charset=utf-8")
