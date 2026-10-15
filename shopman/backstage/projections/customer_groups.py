"""Projeção dos grupos comerciais para o Gestor, sem consultas por linha."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Q
from shopman.utils.monetary import format_money

from shopman.shop.models import Promotion
from shopman.shop.services.promotions import GROUP_DISCOUNT_REF_PREFIX


@dataclass(frozen=True)
class CustomerGroupOptionProjection:
    value: str
    label: str


@dataclass(frozen=True)
class CustomerGroupFormOptionsProjection:
    channels: tuple[CustomerGroupOptionProjection, ...]
    listings: tuple[CustomerGroupOptionProjection, ...]
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
    revision: str


@dataclass(frozen=True)
class CustomerGroupListProjection:
    items: tuple[CustomerGroupProjection, ...]
    total: int
    total_label: str
    form: CustomerGroupFormOptionsProjection


def build_customer_group_form_options() -> CustomerGroupFormOptionsProjection:
    from shopman.offerman.models import Listing

    from shopman.shop.models import Channel

    channels = tuple(
        CustomerGroupOptionProjection(value=channel.ref, label=channel.name or channel.ref)
        for channel in Channel.objects.filter(is_active=True).order_by("display_order", "name", "ref")
    )
    listings = tuple(
        CustomerGroupOptionProjection(value=listing.ref, label=f"{listing.name} · {listing.ref}")
        for listing in Listing.objects.filter(is_active=True).order_by("-priority", "name", "ref")
    )
    return CustomerGroupFormOptionsProjection(
        channels=channels,
        listings=listings,
        discount_types=(
            CustomerGroupOptionProjection(value="", label="Sem desconto"),
            CustomerGroupOptionProjection(value=Promotion.PERCENT, label="Percentual em cada item"),
            CustomerGroupOptionProjection(value=Promotion.FIXED, label="Valor em reais por pedido"),
        ),
    )


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
        revision=tier.updated_at.isoformat(),
    )


def build_customer_group_list() -> CustomerGroupListProjection:
    from shopman.guestman.models import PriceTier
    from shopman.offerman.models import Listing

    tiers = list(
        PriceTier.objects.annotate(customer_count=Count("customers", filter=Q(customers__is_active=True)))
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
        .filter(ref=ref)
        .first()
    )
    if tier is None:
        return None
    promo = Promotion.objects.filter(ref=f"{GROUP_DISCOUNT_REF_PREFIX}{ref}").prefetch_related("channels").first()
    listings = dict(Listing.objects.filter(ref=tier.listing_ref).values_list("ref", "name")) if tier.listing_ref else {}
    return _project(tier, promo, listings)
