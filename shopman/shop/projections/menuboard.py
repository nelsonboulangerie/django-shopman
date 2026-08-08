"""
Menuboard projection — o quadro de cardápio numa TV da loja.

Um canal de exibição (``Channel`` com ``commerce_policy="display"`` e formato vazio)
compõe N coleções; no menuboard cada coleção é uma SEÇÃO (Pães, Doces, Bebidas…).
Pausar o produto globalmente tira do quadro; pausar em ``display.paused_skus`` tira
só deste quadro.

**O preço vem do canal apontado por ``display.prices_from``, não de
``Product.base_price_q``.** A TV do balcão aponta para o PDV porque está na loja e
tem de concordar com o caixa. Antes ela mostrava o preço de tabela, que não é o preço
de nenhum canal em particular — invisível enquanto todos cobram igual, e mentira no
dia em que o PDV tiver preço próprio. Ver ``services/display_prices.py``.

Superfície INTERNA, não pública: preço alcançável publicamente é preço a honrar (ver
``menuboard_access.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MenuboardItem:
    sku: str
    name: str
    price_q: int  # centavos — a superfície formata (appearance na apresentação)
    available: bool
    description: str


@dataclass(frozen=True)
class MenuboardGroup:
    title: str
    items: tuple[MenuboardItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MenuboardProjection:
    ref: str
    title: str
    subtitle: str
    groups: tuple[MenuboardGroup, ...] = field(default_factory=tuple)
    available_count: int = 0
    is_display: bool = True


class MenuboardError(Exception):
    """Raised when a ref is not a valid, active menuboard channel."""


def resolve_menuboard(ref: str):
    """Valida que ``ref`` é um canal de exibição do tipo quadro, e o devolve.

    Formato VAZIO é o que identifica um menuboard: ele é uma rota nossa, não um
    dialeto de terceiro. Google e Meta declaram formato porque têm dialeto.
    """
    from shopman.shop.models import Channel

    channel = Channel.objects.filter(
        ref=ref, is_active=True, commerce_policy=Channel.CommercePolicy.DISPLAY
    ).first()
    if channel is None:
        raise MenuboardError(f"Menuboard '{ref}' não encontrado ou inativo.")
    if ((channel.config or {}).get("display") or {}).get("format"):
        raise MenuboardError(f"Canal '{ref}' é um feed de plataforma, não um quadro.")
    return channel


def _display(channel) -> dict:
    return (channel.config or {}).get("display") or {}


def build_menuboard(ref: str) -> MenuboardProjection:
    """Monta o quadro: uma seção por coleção do canal, na ordem das coleções."""
    from shopman.offerman.models import Collection

    from shopman.shop.services.display_prices import resolve_prices

    channel = resolve_menuboard(ref)
    display = _display(channel)
    collection_refs = list(display.get("collections") or [])
    paused = set(display.get("paused_skus") or [])

    # Coleções na ordem do canal; ordenação de exibição = sort_order da coleção.
    colls = {c.ref: c for c in Collection.objects.filter(ref__in=collection_refs)}

    # Uma passada para juntar os produtos, outra para os preços: o quadro tem
    # dezenas de itens e recarrega a cada evento de estoque.
    by_collection: dict[str, list] = {}
    everything = []
    for coll_ref in collection_refs:
        coll = colls.get(coll_ref)
        if coll is None:
            continue
        products = list(coll.product_queryset().order_by("name"))
        by_collection[coll_ref] = products
        everything.extend(products)

    prices = resolve_prices(channel, everything)

    groups: list[MenuboardGroup] = []
    available_count = 0
    for coll_ref in collection_refs:
        coll = colls.get(coll_ref)
        if coll is None:
            continue
        items: list[MenuboardItem] = []
        for product in by_collection.get(coll_ref, []):
            available = product.is_published and product.is_sellable and product.sku not in paused
            if available:
                available_count += 1
            items.append(
                MenuboardItem(
                    sku=product.sku,
                    name=product.name,
                    price_q=prices.get(product.sku, product.base_price_q),
                    available=available,
                    description=product.short_description or "",
                )
            )
        if items:
            groups.append(MenuboardGroup(title=coll.name, items=tuple(items)))

    return MenuboardProjection(
        ref=ref,
        title=channel.name,
        subtitle="",
        groups=tuple(groups),
        available_count=available_count,
    )
