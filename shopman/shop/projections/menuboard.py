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
class MenuboardPage:
    """Uma TELA da rotação: seções inteiras agrupadas até o teto de itens."""

    groups: tuple[MenuboardGroup, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MenuboardProjection:
    ref: str
    title: str
    subtitle: str
    groups: tuple[MenuboardGroup, ...] = field(default_factory=tuple)
    available_count: int = 0
    is_display: bool = True
    # Rotação de páginas: `pages` sempre tem ao menos 1 página (a página única =
    # todos os groups). `groups` segue completo — é a pintura do servidor, que
    # falha aberta mostrando o cardápio inteiro quando o JS não roda.
    pages: tuple[MenuboardPage, ...] = field(default_factory=tuple)
    rotate_seconds: int = 0


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


def _nonneg_int(value) -> int:
    """Config vem de JSONField editável: valor torto vira 0 (sem paginação)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _paginate(groups: tuple[MenuboardGroup, ...], items_per_page: int) -> tuple[MenuboardPage, ...]:
    """Quebra as seções em páginas de até ``items_per_page`` itens.

    Seções entram INTEIRAS, na ordem; a que não cabe abre página nova. Seção
    maior que o teto quebra em partes com o mesmo título + sufixo de
    continuação — a última parte pode dividir a página com as seções seguintes.
    ``items_per_page <= 0`` = página única com tudo (comportamento clássico).
    """
    if items_per_page <= 0 or not groups:
        return (MenuboardPage(groups=groups),)

    # Seções maiores que o teto viram partes de até `items_per_page` itens.
    parts: list[MenuboardGroup] = []
    for group in groups:
        if len(group.items) <= items_per_page:
            parts.append(group)
            continue
        for start in range(0, len(group.items), items_per_page):
            chunk = group.items[start : start + items_per_page]
            title = group.title if start == 0 else f"{group.title} (cont.)"
            parts.append(MenuboardGroup(title=title, items=chunk))

    pages: list[MenuboardPage] = []
    current: list[MenuboardGroup] = []
    count = 0
    for part in parts:
        if current and count + len(part.items) > items_per_page:
            pages.append(MenuboardPage(groups=tuple(current)))
            current, count = [], 0
        current.append(part)
        count += len(part.items)
    if current:
        pages.append(MenuboardPage(groups=tuple(current)))
    return tuple(pages)


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

    rotate_seconds = _nonneg_int(display.get("rotate_seconds"))
    items_per_page = _nonneg_int(display.get("items_per_page"))
    # Config incoerente (um sem o outro, editada por fora) falha ABERTA: página
    # única com o cardápio inteiro — nunca uma primeira tela parada escondendo
    # o resto.
    if rotate_seconds == 0 or items_per_page == 0:
        rotate_seconds, items_per_page = 0, 0

    return MenuboardProjection(
        ref=ref,
        title=channel.name,
        subtitle="",
        groups=tuple(groups),
        available_count=available_count,
        pages=_paginate(tuple(groups), items_per_page),
        rotate_seconds=rotate_seconds,
    )
