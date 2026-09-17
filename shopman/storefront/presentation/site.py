"""O site para quem ainda não chegou: busca, cartão de link e dados do negócio.

Uma projeção só, lida por todas as páginas públicas do storefront. Cada texto tem
dois donos em cascata: o que o gestor escreveu em Admin → Busca e compartilhamento
e, na falta dele, o que a loja deriva da própria marca. O campo vazio nunca vira
buraco no Google.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.storefront.presentation.public_information import FAQItemProjection, build_public_faq
from shopman.storefront.presentation.shop_status import DAY_ORDER

#: `Shop.social_links` guarda também canais de conversa. `sameAs` declara PERFIS
#: da marca; um link de WhatsApp ali diria ao Google que o número é uma identidade.
_CONVERSATION_PLATFORMS = frozenset({"whatsapp", "telegram"})


@dataclass(frozen=True)
class PageSeoProjection:
    title: str
    description: str


@dataclass(frozen=True)
class SitePagesProjection:
    home: PageSeoProjection
    menu: PageSeoProjection
    faq: PageSeoProjection


@dataclass(frozen=True)
class SiteVerificationsProjection:
    google: str
    bing: str
    facebook: str
    pinterest: str


@dataclass(frozen=True)
class BusinessAddressProjection:
    street: str
    neighborhood: str
    locality: str
    region: str
    postal_code: str
    country_code: str


@dataclass(frozen=True)
class GeoProjection:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class OpeningHoursSpecProjection:
    days: tuple[str, ...]
    opens: str
    closes: str


@dataclass(frozen=True)
class BusinessProjection:
    type: str
    name: str
    legal_name: str
    description: str
    url: str
    telephone: str
    email: str
    logo_url: str
    price_range: str
    founding_year: int | None
    address: BusinessAddressProjection
    geo: GeoProjection | None
    opening_hours: tuple[OpeningHoursSpecProjection, ...]
    maps_url: str
    same_as: tuple[str, ...]


@dataclass(frozen=True)
class SiteProjection:
    pages: SitePagesProjection
    share_image_url: str
    verifications: SiteVerificationsProjection
    business: BusinessProjection
    faq: tuple[FAQItemProjection, ...]


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _in_city(shop) -> str:
    city = _clean(shop.city)
    return f" em {city}" if city else ""


def build_pages(shop) -> SitePagesProjection:
    brand = _clean(shop.brand_name or shop.name)
    tagline = _clean(shop.tagline)
    description = _clean(shop.description)

    derived_home_title = f"{brand} · {tagline}{_in_city(shop)}" if tagline else brand
    derived_home_description = description or (f"{tagline}{_in_city(shop)}." if tagline else brand)

    return SitePagesProjection(
        home=PageSeoProjection(
            title=_clean(shop.seo_home_title) or derived_home_title,
            description=_clean(shop.seo_home_description) or derived_home_description,
        ),
        menu=PageSeoProjection(
            title="Cardápio",
            description=_clean(shop.seo_menu_description)
            or f"Cardápio da {brand}{_in_city(shop)}, com a disponibilidade do dia e pedido online.",
        ),
        faq=PageSeoProjection(
            title="Perguntas frequentes",
            description=_clean(shop.seo_faq_description)
            or f"Perguntas frequentes sobre pedidos, retirada, horários e atendimento da {brand}.",
        ),
    )


def build_opening_hours(opening_hours: dict | None) -> tuple[OpeningHoursSpecProjection, ...]:
    """Agrupa os dias com o mesmo horário, na ordem da semana; dia ausente é fechado."""
    groups: dict[tuple[str, str], list[str]] = {}
    for day in DAY_ORDER:
        entry = (opening_hours or {}).get(day) or {}
        opens, closes = _clean(entry.get("open")), _clean(entry.get("close"))
        if not opens or not closes:
            continue
        groups.setdefault((opens, closes), []).append(day.capitalize())
    return tuple(
        OpeningHoursSpecProjection(days=tuple(days), opens=opens, closes=closes)
        for (opens, closes), days in groups.items()
    )


def _street(shop) -> str:
    route, number = _clean(shop.route), _clean(shop.street_number)
    if route and number:
        return f"{route}, {number}"
    return route


def build_business(shop) -> BusinessProjection:
    geo = None
    if shop.latitude is not None and shop.longitude is not None:
        geo = GeoProjection(latitude=float(shop.latitude), longitude=float(shop.longitude))

    return BusinessProjection(
        type=shop.business_type or "Bakery",
        name=_clean(shop.brand_name or shop.name),
        legal_name=_clean(shop.legal_name),
        description=_clean(shop.description),
        # O host público é do storefront, não do Django: quem monta a URL é a borda.
        url="",
        telephone=shop.phone_url.removeprefix("tel:"),
        email=_clean(shop.email),
        logo_url=shop.logo.url if shop.logo else "",
        price_range=_clean(shop.price_range),
        founding_year=shop.founding_year,
        address=BusinessAddressProjection(
            street=_street(shop),
            neighborhood=_clean(shop.neighborhood),
            locality=_clean(shop.city),
            region=_clean(shop.state_code),
            postal_code=_clean(shop.postal_code),
            country_code=_clean(shop.country_code),
        ),
        geo=geo,
        opening_hours=build_opening_hours(shop.opening_hours),
        maps_url=shop.maps_url,
        same_as=tuple(
            link["url"]
            for link in shop.social_links_resolved
            if link["platform"] not in _CONVERSATION_PLATFORMS
        ),
    )


def build_site(*, shop, channel_ref: str) -> SiteProjection:
    return SiteProjection(
        pages=build_pages(shop),
        share_image_url=_clean(shop.seo_share_image_url),
        verifications=SiteVerificationsProjection(
            google=_clean(shop.google_site_verification),
            bing=_clean(shop.bing_site_verification),
            facebook=_clean(shop.facebook_domain_verification),
            pinterest=_clean(shop.pinterest_domain_verification),
        ),
        business=build_business(shop),
        # Sem o status do momento ("Aberto até 22h"): a página é lida pelo buscador
        # uma vez e servida por dias. A grade da semana é o que continua verdade.
        faq=build_public_faq(channel_ref=channel_ref, shop=shop, status={}),
    )
