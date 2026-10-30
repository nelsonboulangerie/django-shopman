"""
Product feed — o 🛰 Feed da Meta, RSS 2.0 público.

Traduz para o XML ``g:`` a decisão de ``services/display_catalog`` (quem entra, preço,
disponível, oculto). Pull: o catálogo da Meta busca a URL agendado. O Ocultar sai como
``status=archived``, campo fora da especificação ``g:`` e por isso sem o prefixo
(developers.facebook.com/docs/marketing-api/catalog/reference).

O Google não passa por aqui: o canal dele é escrito só pela Merchant API
(``adapters/catalog_projection_google``), e canal de formato ``google_merchant`` responde
404 nesta rota.

Este é o feed PÚBLICO — a Meta precisa buscá-lo sem credencial —, e é justamente por
isso que o preço nele tem de ser o preço que a loja honra.

⚠️ Vida curta: o envio pela API (``docs/plans/CATALOG-PUSH-GOOGLE-META-PLAN.md``)
substitui este feed como escritor único da Meta.

Spec verificada (2026-07-01): facebook.com/business/help/120325381656392.
"""

from __future__ import annotations

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views import View

from shopman.shop.services import display_catalog

# A Meta grafa availability com espaço (verificado).
_AVAILABILITY = {True: "in stock", False: "out of stock"}


def build_feed_items(ref: str) -> list[dict]:
    """Itens do feed da Meta. Canal de outro formato não tem feed."""
    _channel, fmt = display_catalog.resolve_channel(ref)
    if fmt != "meta_catalog":
        raise display_catalog.DisplayCatalogError(f"display channel has no XML feed: {fmt!r}")
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
            "availability": _AVAILABILITY[item.available],
            "price": f"{item.price_q / 100:.2f} BRL",
            "product_type": item.product_type,
            "custom_label_0": item.custom_label_0,
            "status": "archived" if item.hidden else "",
        }
        for item in display_catalog.display_items(ref)
    ]


class ProductFeedView(View):
    """Saída RSS 2.0 pública do canal de exibição da Meta."""

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
