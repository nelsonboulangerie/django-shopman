"""O catálogo de um canal de exibição de plataforma: o que o Google e a Meta recebem.

Um canal de exibição com formato declarado (``Channel`` com
``commerce_policy="display"`` e ``display.format`` em ``google_merchant``/
``meta_catalog``) compõe N coleções; cada coleção vira o ``custom_label_0`` do produto
(o análogo das smart collections p/ anúncios — Google custom_labels, Meta product
sets).

Aqui mora a ÚNICA decisão sobre cada item: entra ou não, preço, disponível ou não,
oculto ou não. Quem fala com a plataforma só traduz: o envio ao Google pela Merchant
API (``adapters/catalog_projection_google``), o envio à Meta (``adapters/catalog_projection_meta``)
e o XML do feed da Meta (``views/product_feed.py``). Duas leituras da mesma regra divergiriam em
silêncio, e a plataforma reprova item cujo dado não bate com a página da loja.

**O preço vem do canal apontado por ``display.prices_from``** (a loja online, porque é
lá que quem clicou compra), não de ``Product.base_price_q``. Ver
``services/display_prices.py``.

Os dois gestos do Catálogo chegam diferentes às plataformas (verificado em 23/10/2026):

- **Pausar** (segue à mostra, sem compra) é ``available=False``: fora de estoque. A
  Meta mostra "esgotado" na loja e tira dos anúncios; o Google para de anunciar.
- **Ocultar** (some do canal) é ``hidden=True``: o item continua na plataforma, mas
  fora de todos os destinos. Tirar o item apaga o produto na plataforma, e religar
  viraria cadastro novo, com nova revisão. No Google, ``excludedDestinations`` com
  cada destino (support.google.com/merchants/answer/6324486); ``pause`` não serve,
  porque o ``all`` arquiva o produto depois de 14 dias (answer/11909930). Na Meta,
  ``status=archived`` ("Only active items can be seen by people in your ads, shops",
  developers.facebook.com/docs/commerce-platform/catalog/fields).
"""

from __future__ import annotations

from dataclasses import dataclass

FEED_FORMATS = ("google_merchant", "meta_catalog")

#: Destinos do Google que o Ocultar exclui, no ``DestinationEnum`` da Merchant API
#: (google/shopping/type/types.proto; lista de destinos em answer/6324486).
GOOGLE_DESTINATIONS = (
    "SHOPPING_ADS",
    "DISPLAY_ADS",
    "LOCAL_INVENTORY_ADS",
    "FREE_LISTINGS",
    "FREE_LOCAL_LISTINGS",
    "YOUTUBE_AFFILIATE",
    "YOUTUBE_SHOPPING",
)


class DisplayCatalogError(Exception):
    pass


@dataclass(frozen=True)
class DisplayItem:
    sku: str
    title: str
    description: str
    link: str
    image_link: str
    brand: str
    gtin: str
    mpn: str
    condition: str
    google_product_category: str
    price_q: int
    product_type: str
    custom_label_0: str
    #: Pode ser comprado agora: canal ligado, não pausado, vendável e com estoque.
    available: bool
    #: Ocultado aqui ou no produto: fica na plataforma, fora de todos os destinos.
    hidden: bool
    additional_image_links: tuple[str, ...] = ()


def resolve_channel(ref: str):
    """Canal de exibição COM formato declarado. Sem formato é menuboard, não feed."""
    from shopman.shop.models import Channel

    channel = Channel.objects.filter(
        ref=ref, commerce_policy=Channel.CommercePolicy.DISPLAY
    ).first()
    if channel is None:
        raise DisplayCatalogError("not a display channel")
    fmt = ((channel.config or {}).get("display") or {}).get("format") or ""
    if fmt not in FEED_FORMATS:
        raise DisplayCatalogError(f"display channel has no feed format: {fmt!r}")
    return channel, fmt


def is_platform_channel(ref: str) -> bool:
    try:
        resolve_channel(ref)
    except DisplayCatalogError:
        return False
    return True


def storefront_base() -> str:
    """Base da LOJA, onde o produto tem página — nunca o host que serviu o feed.

    O catálogo é servido pelo Django headless, que não tem página de produto: em
    22/09/2026 os 48 itens do ``google-shopping`` no ar apontavam para
    ``https://api.boulangerie.com.br/produto/<sku>``, que responde 404. Merchant
    Center reprova item cuja landing page não abre. Sem a base configurada não há
    link certo para dar, e link errado é pior que item nenhum: falha fechado.
    """
    from shopman.shop.services.storefront_links import storefront_base_url

    base = storefront_base_url()
    if not base:
        raise DisplayCatalogError("Base da loja vazia: o catálogo não tem para onde mandar o cliente")
    return base


def _composition(channel):
    """``[(produto, coleção)]`` na ordem do canal: 1ª coleção vence, sem foto fica fora.

    Item sem imagem é omitido: ``image_link`` é obrigatório nas duas plataformas, e o
    item seria reprovado.
    """
    from shopman.offerman.models import Collection

    collection_refs = list(((channel.config or {}).get("display") or {}).get("collections") or [])
    colls = {c.ref: c for c in Collection.objects.filter(ref__in=collection_refs)}
    seen: set[str] = set()
    pairs = []
    for coll_ref in collection_refs:
        coll = colls.get(coll_ref)
        if coll is None:
            continue
        for product in coll.product_queryset():
            if product.sku in seen or not product.image_url:
                continue
            seen.add(product.sku)
            pairs.append((product, coll))
    return pairs


def composition_skus(ref: str) -> list[str]:
    """Os SKUs que o canal publica, sem calcular preço nem estoque (barato)."""
    channel, _fmt = resolve_channel(ref)
    return [product.sku for product, _coll in _composition(channel)]


def display_items(ref: str, *, skus: set[str] | None = None) -> list[DisplayItem]:
    """Os itens do canal com a decisão tomada. ``skus`` limita a conta a esses SKUs."""
    from shopman.offerman import get_social_attributes

    from shopman.shop.services import external_availability
    from shopman.shop.services.channel_switch import effective_active
    from shopman.shop.services.display_prices import resolve_prices
    from shopman.shop.services.storefront_links import path_product

    channel, _fmt = resolve_channel(ref)
    switched_on = effective_active(channel)
    display = (channel.config or {}).get("display") or {}
    paused = set(display.get("paused_skus") or [])  # pausa LOCAL (a global é do produto)
    hidden = set(display.get("hidden_skus") or [])  # ocultação LOCAL (a global é do produto)
    base = storefront_base()

    pairs = [(p, c) for p, c in _composition(channel) if skus is None or p.sku in skus]
    # Preço de todos de uma vez: uma consulta para o lote, não uma por item.
    prices = resolve_prices(channel, [product for product, _coll in pairs])

    items: list[DisplayItem] = []
    for product, coll in pairs:
        attributes = get_social_attributes(product)
        # Canal desligado no Gestor: todo item sai FORA DE ESTOQUE, e não some.
        # Google e Meta param de anunciar item sem estoque, sem penalidade, e o
        # item volta a rodar assim que o canal é religado.
        #
        # Vendável zerado também sai fora de estoque, pela mesma regra que recusa
        # o pedido no canal para onde o clique leva (``external_availability``).
        # A pausa vence: pausado segue fora com estoque cheio. Oculto (aqui ou no
        # produto) vence pausado: sai de todos os destinos.
        is_hidden = not product.is_published or product.sku in hidden
        available = (
            switched_on
            and not is_hidden
            and product.is_sellable
            and product.sku not in paused
            and external_availability.in_stock(product.sku, channel_ref=channel.ref)
        )
        metadata = product.metadata if isinstance(product.metadata, dict) else {}
        gallery = metadata.get("gallery") or []
        extra = tuple(
            str(url) for url in gallery if url and str(url) != product.image_url
        )[:10] if isinstance(gallery, (list, tuple)) else ()
        items.append(DisplayItem(
            sku=product.sku,
            title=product.name[:150],
            description=(product.long_description or product.short_description or product.name)[:5000],
            link=f"{base}{path_product(product.sku)}",
            image_link=product.image_url,
            brand=attributes.brand or "",
            gtin=attributes.gtin or "",
            mpn=attributes.mpn or "",
            condition=attributes.condition or "new",
            google_product_category=attributes.google_product_category or "",
            price_q=int(prices.get(product.sku, product.base_price_q)),
            product_type=coll.name,
            custom_label_0=coll.ref,
            available=bool(available),
            hidden=is_hidden,
            additional_image_links=extra,
        ))
    return items


def display_item(ref: str, sku: str) -> DisplayItem | None:
    """O item ``sku`` no canal, ou ``None`` quando ele não faz parte do canal."""
    found = display_items(ref, skus={sku})
    return found[0] if found else None


def channels_priced_from(source_ref: str) -> list[str]:
    """Canais de plataforma cujo preço (e estoque) vem de ``source_ref``."""
    from shopman.shop.models import Channel
    from shopman.shop.services.display_prices import price_source_ref

    refs = []
    for channel in Channel.objects.filter(commerce_policy=Channel.CommercePolicy.DISPLAY):
        fmt = ((channel.config or {}).get("display") or {}).get("format") or ""
        if fmt in FEED_FORMATS and price_source_ref(channel) == source_ref:
            refs.append(channel.ref)
    return refs
