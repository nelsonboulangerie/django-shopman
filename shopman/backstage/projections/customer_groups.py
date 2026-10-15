"""Projeção dos grupos comerciais para o Gestor, sem consultas por linha."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Q
from shopman.utils.monetary import format_money

from shopman.shop.models import Promotion
from shopman.shop.services.customer_groups import ADVANTAGE_KINDS
from shopman.shop.services.promotions import GROUP_DISCOUNT_REF_PREFIX


@dataclass(frozen=True)
class CustomerGroupOptionProjection:
    value: str
    label: str


@dataclass(frozen=True)
class CustomerGroupAdvantageProjection:
    """Uma vantagem TIPADA do grupo, como o gestor lê e edita.

    ``config`` é tipado por ``kind`` e documentado em
    ``docs/reference/data-schemas.md``: frete grátis usa ``min_order_q``; coleções
    exclusivas usam ``collection_refs``; avisos exclusivos usam ``campaign_refs``.
    """

    kind: str
    kind_label: str
    is_active: bool
    priority: int
    #: A frase que resume a configuração atual, sem repetir o que já é campo.
    summary_label: str
    min_order_q: int
    min_order_display: str
    collection_refs: tuple[str, ...]
    campaign_refs: tuple[str, ...]


@dataclass(frozen=True)
class CustomerGroupFormOptionsProjection:
    channels: tuple[CustomerGroupOptionProjection, ...]
    listings: tuple[CustomerGroupOptionProjection, ...]
    collections: tuple[CustomerGroupOptionProjection, ...]
    discount_types: tuple[CustomerGroupOptionProjection, ...]


@dataclass(frozen=True)
class CustomerGroupProjection:
    ref: str
    name: str
    description: str
    listing_ref: str
    listing_name: str
    priority: int
    is_default: bool
    customer_count: int
    customer_count_label: str
    discount_type: str
    discount_value: str
    discount_label: str
    channel_refs: tuple[str, ...]
    channels_label: str
    pickup_only: bool
    discount_kind: str
    rounding: bool
    savings_message: str
    advantages: tuple[CustomerGroupAdvantageProjection, ...]
    revision: str


@dataclass(frozen=True)
class CustomerGroupListProjection:
    items: tuple[CustomerGroupProjection, ...]
    total: int
    total_label: str
    form: CustomerGroupFormOptionsProjection


def build_customer_group_form_options() -> CustomerGroupFormOptionsProjection:
    from shopman.offerman.models import Collection, Listing

    from shopman.shop.models import Channel

    channels = tuple(
        CustomerGroupOptionProjection(value=channel.ref, label=channel.name or channel.ref)
        for channel in Channel.objects.filter(is_active=True).order_by("display_order", "name", "ref")
    )
    listings = tuple(
        CustomerGroupOptionProjection(value=listing.ref, label=f"{listing.name} · {listing.ref}")
        for listing in Listing.objects.filter(is_active=True).order_by("-priority", "name", "ref")
    )
    collections = tuple(
        CustomerGroupOptionProjection(value=collection.ref, label=collection.name)
        for collection in Collection.objects.filter(is_active=True).order_by("sort_order", "name", "ref")
    )
    return CustomerGroupFormOptionsProjection(
        channels=channels,
        listings=listings,
        collections=collections,
        discount_types=(
            CustomerGroupOptionProjection(value="", label="Sem desconto"),
            CustomerGroupOptionProjection(value=Promotion.PERCENT, label="Percentual em cada item"),
            CustomerGroupOptionProjection(value=Promotion.FIXED, label="Valor em reais por pedido"),
        ),
    )


def _advantage_summary(kind: str, *, min_order_q: int, collections: int, campaigns: int) -> str:
    if kind == "free_shipping":
        return (
            f"Frete grátis em pedidos a partir de R$ {format_money(min_order_q)}"
            if min_order_q > 0
            else "Frete grátis em qualquer pedido"
        )
    if kind == "exclusive_collections":
        if collections == 0:
            return "Nenhuma coleção exclusiva escolhida"
        return "1 coleção exclusiva" if collections == 1 else f"{collections} coleções exclusivas"
    if campaigns == 0:
        return "Nenhum aviso exclusivo escolhido"
    return "1 aviso exclusivo" if campaigns == 1 else f"{campaigns} avisos exclusivos"


def _advantage_projections(tier) -> tuple[CustomerGroupAdvantageProjection, ...]:
    """As vantagens do grupo na ordem canônica dos tipos, lendo o prefetch do tier."""
    from shopman.guestman.models import PriceTierAdvantage

    kind_labels = dict(PriceTierAdvantage.Kind.choices)
    by_kind = {advantage.kind: advantage for advantage in tier.advantages.all()}
    projections: list[CustomerGroupAdvantageProjection] = []
    for kind in ADVANTAGE_KINDS:
        advantage = by_kind.get(kind)
        config = advantage.config if advantage is not None and isinstance(advantage.config, dict) else {}
        raw_min_order = config.get("min_order_q", 0)
        min_order_q = (
            int(raw_min_order)
            if isinstance(raw_min_order, int) and not isinstance(raw_min_order, bool) and raw_min_order > 0
            else 0
        )
        collection_refs = tuple(str(ref) for ref in (config.get("collection_refs") or []) if ref)
        campaign_refs = tuple(str(ref) for ref in (config.get("campaign_refs") or []) if ref)
        projections.append(
            CustomerGroupAdvantageProjection(
                kind=kind,
                kind_label=str(kind_labels.get(kind, kind)),
                is_active=bool(advantage.is_active) if advantage is not None else False,
                priority=int(advantage.priority) if advantage is not None else 0,
                summary_label=_advantage_summary(
                    kind,
                    min_order_q=min_order_q,
                    collections=len(collection_refs),
                    campaigns=len(campaign_refs),
                ),
                min_order_q=min_order_q,
                min_order_display=f"R$ {format_money(min_order_q)}" if min_order_q else "",
                collection_refs=collection_refs,
                campaign_refs=campaign_refs,
            )
        )
    return tuple(projections)


def _project(tier, promo: Promotion | None, listings: dict[str, str]) -> CustomerGroupProjection:
    metadata = tier.metadata if isinstance(tier.metadata, dict) else {}
    count = int(getattr(tier, "customer_count", 0) or 0)
    discount_type = promo.type if promo is not None and promo.is_active else ""
    if not discount_type:
        discount_value = ""
        discount_label = "Sem desconto automático"
    elif discount_type == Promotion.PERCENT:
        discount_value = str(int(promo.value))
        discount_label = f"{int(promo.value)}% em cada item"
    else:
        discount_value = f"{Decimal(promo.value) / 100:.2f}"
        discount_label = f"R$ {format_money(int(promo.value))} por pedido"
    channel_refs = tuple(channel.ref for channel in promo.channels.all()) if promo is not None else ()
    channels_label = (
        ", ".join(channel.name or channel.ref for channel in promo.channels.all())
        if discount_type and channel_refs
        else "Todos os canais"
    )
    return CustomerGroupProjection(
        ref=tier.ref,
        name=tier.name,
        description=tier.description or "",
        listing_ref=tier.listing_ref or "",
        listing_name=listings.get(tier.listing_ref, ""),
        priority=tier.priority,
        is_default=tier.is_default,
        customer_count=count,
        customer_count_label="1 cliente" if count == 1 else f"{count} clientes",
        discount_type=discount_type,
        discount_value=discount_value,
        discount_label=discount_label,
        channel_refs=channel_refs,
        channels_label=channels_label,
        pickup_only=bool(promo is not None and list(promo.fulfillment_types or []) == ["pickup"]),
        discount_kind=str(metadata.get("discount_kind") or ""),
        rounding=int(metadata.get("rounding", 50) or 0) > 0,
        savings_message=str(metadata.get("savings_message") or ""),
        advantages=_advantage_projections(tier),
        revision=tier.updated_at.isoformat(),
    )


def build_customer_group_list() -> CustomerGroupListProjection:
    from shopman.guestman.models import PriceTier
    from shopman.offerman.models import Listing

    tiers = list(
        PriceTier.objects.annotate(customer_count=Count("customers", filter=Q(customers__is_active=True)))
        .prefetch_related("advantages")
        .order_by("-priority", "name", "ref")
    )
    refs = [f"{GROUP_DISCOUNT_REF_PREFIX}{tier.ref}" for tier in tiers]
    promotions = {
        promo.ref.removeprefix(GROUP_DISCOUNT_REF_PREFIX): promo
        for promo in Promotion.objects.filter(ref__in=refs).prefetch_related("channels")
    }
    listing_refs = {tier.listing_ref for tier in tiers if tier.listing_ref}
    listings = dict(Listing.objects.filter(ref__in=listing_refs).values_list("ref", "name"))
    items = tuple(_project(tier, promotions.get(tier.ref), listings) for tier in tiers)
    total = len(items)
    return CustomerGroupListProjection(
        items=items,
        total=total,
        total_label="1 grupo" if total == 1 else f"{total} grupos",
        form=build_customer_group_form_options(),
    )


def build_customer_group_detail(ref: str) -> CustomerGroupProjection | None:
    from shopman.guestman.models import PriceTier
    from shopman.offerman.models import Listing

    tier = (
        PriceTier.objects.annotate(customer_count=Count("customers", filter=Q(customers__is_active=True)))
        .prefetch_related("advantages")
        .filter(ref=ref)
        .first()
    )
    if tier is None:
        return None
    promo = Promotion.objects.filter(ref=f"{GROUP_DISCOUNT_REF_PREFIX}{ref}").prefetch_related("channels").first()
    listings = dict(Listing.objects.filter(ref=tier.listing_ref).values_list("ref", "name")) if tier.listing_ref else {}
    return _project(tier, promo, listings)
