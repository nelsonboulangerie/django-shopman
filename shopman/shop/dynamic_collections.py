"""Dynamic collections — coleções curadas pelo sistema, resolvidas em tempo real.

Complementam as Collections estáticas do Offerman (operador cria, produto é
associado). Dinâmicas não têm linhas no DB — são Python resolvers que retornam
os SKUs dos produtos, em ordem, baseados em métricas (vendas, data de produção,
novidade, etc.). Só o SKU: quem mostra a seção (o cardápio) já tem o card de
cada produto montado, com preço e disponibilidade, e reusa o card pelo SKU.

**Configuração**: quais dinâmicas aparecem no menu e em que ordem fica em
``Shop.defaults["menu"]["dynamic_collections"]`` (ou ``Channel.config``),
como lista de refs (``["featured", "fresh_from_oven"]``).

**Uso**:
    from shopman.shop import dynamic_collections as dyn
    section = dyn.resolve("featured", channel_ref="web")
    # Retorna DynamicSection(meta, skus) ou None se ref desconhecido
    # ou nenhum SKU.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DynamicCollectionMeta:
    """Metadata estática de uma dinâmica: ref, label, ícone, descrição."""

    ref: str            # "featured", "fresh_from_oven", ...
    label: str          # "Destaques"
    icon: str           # Material Symbols ligature
    description: str    # Subtítulo para a seção


@dataclass(frozen=True)
class DynamicSection:
    """Resultado de um resolver: metadados + SKUs, na ordem da seção."""

    meta: DynamicCollectionMeta
    skus: tuple[str, ...]


class DynamicCollectionResolver(Protocol):
    meta: DynamicCollectionMeta

    def resolve(self, channel_ref: str, limit: int = 20) -> list[str]:
        ...


# ── Registry ──────────────────────────────────────────────────────────

_registry: dict[str, DynamicCollectionResolver] = {}


def register(resolver_instance: DynamicCollectionResolver) -> None:
    """Registra uma dinâmica no registry global."""
    _registry[resolver_instance.meta.ref] = resolver_instance


def get(ref: str) -> DynamicCollectionResolver | None:
    return _registry.get(ref)


def all_refs() -> list[str]:
    return list(_registry.keys())


def resolve(ref: str, *, channel_ref: str, limit: int = 20) -> DynamicSection | None:
    """Resolve uma dinâmica para um canal. Retorna None se vazio ou ausente."""
    resolver = _registry.get(ref)
    if resolver is None:
        return None
    try:
        skus = resolver.resolve(channel_ref, limit=limit)
    except Exception:
        logger.exception(
            "dynamic_collections.resolve failed ref=%s channel=%s", ref, channel_ref,
        )
        return None
    if not skus:
        return None
    return DynamicSection(meta=resolver.meta, skus=tuple(skus))


# ── Built-in resolvers ────────────────────────────────────────────────


# O ranking dos mais vendidos (agregado de ``OrderItem`` × ``Order`` de 30 dias)
# é a única leitura cara do cardápio que não depende de quem pede, e ele é lido
# a cada ``menu/``. Guardado por poucos minutos: um pedido novo pode demorar até
# ``FEATURED_RANKING_TTL_SECONDS`` para mexer na ordem dos Destaques. Só o
# ranking fica guardado — publicação e pausa do produto continuam lidas na hora,
# e o card (preço, disponibilidade) vem do cardápio, ao vivo.
FEATURED_RANKING_CACHE_KEY = "shop:dynamic_collections:featured_ranking"
FEATURED_RANKING_TTL_SECONDS = 300


def invalidate_featured_ranking() -> None:
    cache.delete(FEATURED_RANKING_CACHE_KEY)


class FeaturedResolver:
    """Destaques: mais vendidos nos últimos 30 dias; fallback: sort_order."""

    meta = DynamicCollectionMeta(
        ref="featured",
        label="Destaques",
        icon="local_fire_department",
        description="Os mais vendidos e curados pela casa.",
    )

    WINDOW_DAYS = 30

    def resolve(self, channel_ref: str, limit: int = 20) -> list[str]:
        from shopman.offerman.models import Product

        top_skus = self._top_selling_skus(limit)
        if top_skus:
            # Manter ordem de mais vendidos
            preserved = {sku: idx for idx, sku in enumerate(top_skus)}
            skus = list(
                Product.objects
                .filter(sku__in=top_skus, is_published=True, is_sellable=True)
                .values_list("sku", flat=True)
            )
            skus.sort(key=lambda sku: preserved.get(sku, 9999))
            if skus:
                return skus

        # Fallback: produtos com is_featured no metadata ou menor sort_order
        qs = Product.objects.filter(is_published=True, is_sellable=True)
        featured_in_meta = [
            sku for sku, metadata in qs.values_list("sku", "metadata")
            if (metadata or {}).get("is_featured")
        ]
        if featured_in_meta:
            return featured_in_meta[:limit]
        return list(qs.order_by("sort_order", "name").values_list("sku", flat=True)[:limit])

    def _top_selling_skus(self, limit: int) -> list[str]:
        """Os ``limit`` SKUs mais vendidos da janela, do cache curto ou do banco.

        Cache fora do ar não derruba a seção: lê do banco, como sem cache.
        """
        try:
            cached = cache.get(FEATURED_RANKING_CACHE_KEY)
        except Exception:
            logger.warning("featured_ranking_cache_read_failed", exc_info=True)
            cached = None
        if cached is not None and cached[0] == limit:
            return list(cached[1])

        from django.db.models import Count
        from shopman.orderman.models import OrderItem

        since = timezone.now() - timedelta(days=self.WINDOW_DAYS)
        top_skus = list(
            OrderItem.objects
            .filter(order__created_at__gte=since)
            .values("sku")
            .annotate(n=Count("id"))
            .order_by("-n")
            .values_list("sku", flat=True)[:limit]
        )
        try:
            cache.set(FEATURED_RANKING_CACHE_KEY, (limit, tuple(top_skus)), FEATURED_RANKING_TTL_SECONDS)
        except Exception:
            logger.warning("featured_ranking_cache_write_failed", exc_info=True)
        return top_skus


class FreshFromOvenResolver:
    """Recém saídos do forno: WorkOrders finalizadas nos últimos 60 minutos."""

    meta = DynamicCollectionMeta(
        ref="fresh_from_oven",
        label="Recém saídos do forno",
        icon="schedule",
        description="Saíram do forno nos últimos 60 minutos.",
    )

    WINDOW_MINUTES = 60

    def resolve(self, channel_ref: str, limit: int = 20) -> list[str]:
        try:
            from shopman.craftsman.models import WorkOrder
        except ImportError:
            return []
        from shopman.offerman.models import Product

        since = timezone.now() - timedelta(minutes=self.WINDOW_MINUTES)
        try:
            recent_skus = (
                WorkOrder.objects
                .filter(status="finished", finished_at__gte=since)
                .values_list("output_sku", flat=True)
                .distinct()
            )
            recent_skus = list(recent_skus)
        except Exception:
            logger.debug("fresh_from_oven: query failed, returning empty", exc_info=True)
            return []

        if not recent_skus:
            return []
        return list(
            Product.objects
            .filter(sku__in=recent_skus, is_published=True, is_sellable=True)
            .order_by("name")
            .values_list("sku", flat=True)[:limit]
        )


class NewArrivalsResolver:
    """Novidades: produtos publicados nos últimos 14 dias."""

    meta = DynamicCollectionMeta(
        ref="new_arrivals",
        label="Novidades",
        icon="fiber_new",
        description="Chegaram recentemente ao cardápio.",
    )

    WINDOW_DAYS = 14

    def resolve(self, channel_ref: str, limit: int = 20) -> list[str]:
        from shopman.offerman.models import Product

        since = timezone.now() - timedelta(days=self.WINDOW_DAYS)
        return list(
            Product.objects
            .filter(is_published=True, is_sellable=True, created_at__gte=since)
            .order_by("-created_at")
            .values_list("sku", flat=True)[:limit]
        )


# Registra built-ins
register(FeaturedResolver())
register(FreshFromOvenResolver())
register(NewArrivalsResolver())
