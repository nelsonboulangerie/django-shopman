"""
Projeção dos canais de EXIBIÇÃO para o Gestor — o lado display do cardápio.

Um Feed exibe um recorte de coleções para fora (📺 menuboard / 🛰 Google/Meta) sem
transacionar. Esta projeção lista os feeds + a saída (URL para abrir/prever) +
as coleções disponíveis (para o operador escolher quais cada um mostra). A ordem de
exibição das coleções é global (``Collection.sort_order``), reordenável no catálogo.

Read-only. Frozen dataclasses convertidos por ``backstage.api.projections``.
"""

from __future__ import annotations

from dataclasses import dataclass

# O `kind` da tela deriva de `display.format`: formato VAZIO é quadro (rota nossa),
# formato preenchido é feed de plataforma (dialeto de terceiro).
_FORMAT_META = {
    "": {"kind": "menuboard", "label": "Menuboard (TV)", "icon": "tv", "capability": "display"},
    "google_merchant": {"kind": "google", "label": "Feed Google", "icon": "rss", "capability": "feed"},
    "meta_catalog": {"kind": "meta", "label": "Feed Meta", "icon": "rss", "capability": "feed"},
}


def _output_path(ref: str, fmt: str) -> str:
    """Caminho da saída (abrir/prever).

    O `?platform=` saiu: o formato é propriedade do CANAL, não parâmetro de query —
    dois jeitos de dizer a mesma coisa é um jeito a mais de discordarem.
    """
    if not fmt:
        return f"/menuboard/{ref}/"
    return f"/feed/{ref}.xml"


@dataclass(frozen=True)
class FeedCollectionRef:
    ref: str
    name: str
    exists: bool  # a coleção ainda existe?


@dataclass(frozen=True)
class FeedProjection:
    ref: str
    name: str
    kind: str
    kind_label: str
    kind_icon: str
    capability: str  # display | feed
    is_active: bool
    output_path: str
    collections: tuple[FeedCollectionRef, ...]  # coleções que ele exibe (em ordem global)


@dataclass(frozen=True)
class CollectionOptionProjection:
    ref: str
    name: str
    product_count: int


@dataclass(frozen=True)
class FeedBoardProjection:
    feeds: tuple[FeedProjection, ...]
    all_collections: tuple[CollectionOptionProjection, ...]  # opções p/ o picker (ordem global)


def build_feed_board() -> FeedBoardProjection:
    from shopman.offerman.models import Collection

    from shopman.shop.models import Channel

    collections = list(Collection.objects.filter(is_active=True).order_by("sort_order", "name"))
    coll_by_ref = {c.ref: c for c in collections}
    order_index = {c.ref: i for i, c in enumerate(collections)}

    feeds: list[FeedProjection] = []
    channels = Channel.objects.filter(
        commerce_policy=Channel.CommercePolicy.DISPLAY
    ).order_by("name")
    for sc in channels:
        display = (sc.config or {}).get("display") or {}
        fmt = display.get("format") or ""
        meta = _FORMAT_META.get(fmt, {"kind": fmt, "label": fmt, "icon": "monitor", "capability": "display"})
        # resolve + ordena as coleções do canal pela ordem global (sort_order)
        refs = list(display.get("collections") or [])
        resolved = [
            FeedCollectionRef(
                ref=r,
                name=coll_by_ref[r].name if r in coll_by_ref else r,
                exists=r in coll_by_ref,
            )
            for r in refs
        ]
        resolved.sort(key=lambda c: order_index.get(c.ref, 10_000))
        feeds.append(
            FeedProjection(
                ref=sc.ref,
                name=sc.name or sc.ref,
                kind=meta["kind"],
                kind_label=meta["label"],
                kind_icon=meta["icon"],
                capability=meta["capability"],
                is_active=sc.is_active,
                output_path=_output_path(sc.ref, fmt),
                collections=tuple(resolved),
            )
        )

    options = tuple(
        CollectionOptionProjection(ref=c.ref, name=c.name, product_count=c.product_queryset().count())
        for c in collections
    )
    return FeedBoardProjection(feeds=tuple(feeds), all_collections=options)
