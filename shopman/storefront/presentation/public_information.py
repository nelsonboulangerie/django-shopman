"""Canonical public information shared by the storefront and Concierge."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from shopman.shop.projections.channel_policy import resolve_channel_policy
from shopman.storefront.presentation.shop_status import _format_opening_hours, _shop_status


@dataclass(frozen=True)
class FAQItemProjection:
    ref: str
    question: str
    answer: str


_OPERATIONAL_SEARCH_TERMS = {
    "delivery": ("entrega", "entregam", "delivery", "frete", "taxa", "receber em casa"),
    "hours": ("horário", "horarios", "abre", "aberto", "fecha", "funcionamento"),
    "location": ("endereço", "localização", "onde fica", "como chegar"),
    "contact": ("contato", "telefone", "e-mail", "email", "falar", "atendimento"),
}


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _operational_faq(
    *,
    channel_ref: str,
    shop,
    status: dict | None = None,
    opening_hours: tuple | list | None = None,
) -> list[FAQItemProjection]:
    policy = resolve_channel_policy(channel_ref)
    status = status if status is not None else _shop_status()
    hours = opening_hours if opening_hours is not None else _format_opening_hours()
    items: list[FAQItemProjection] = []

    if "delivery" in policy.fulfillment_types:
        delivery_answer = (
            "Sim. Fazemos entrega. Para confirmar se o endereço está na área atendida e calcular "
            "a taxa, precisamos do endereço completo com número."
        )
    else:
        delivery_answer = "No momento, este canal oferece retirada na loja."
    items.append(
        FAQItemProjection(
            ref="delivery",
            question="Vocês fazem entrega?",
            answer=delivery_answer,
        )
    )

    if hours:
        schedule = "; ".join(
            f"{getattr(entry, 'label', None) or entry['label']}: {getattr(entry, 'hours', None) or entry['hours']}"
            for entry in hours
        )
        current = str(status.get("label") or "").strip()
        answer = f"{current}. {schedule}" if current else schedule
        items.append(
            FAQItemProjection(
                ref="hours",
                question="Quais são os horários de funcionamento?",
                answer=answer,
            )
        )

    address = str(getattr(shop, "full_address", "") or "").replace("\n", ", ").strip()
    if address:
        items.append(
            FAQItemProjection(
                ref="location",
                question="Onde vocês ficam?",
                answer=f"Ficamos em {address}.",
            )
        )

    contacts = []
    phone = str(getattr(shop, "phone_display", "") or "").strip()
    email = str(getattr(shop, "email", "") or "").strip()
    if phone:
        contacts.append(f"telefone {phone}")
    if email:
        contacts.append(f"e-mail {email}")
    if contacts:
        items.append(
            FAQItemProjection(
                ref="contact",
                question="Como falar com vocês?",
                answer="Você pode falar conosco por " + " ou ".join(contacts) + ".",
            )
        )
    return items


def build_public_faq(
    *,
    channel_ref: str,
    shop=None,
    status: dict | None = None,
    opening_hours: tuple | list | None = None,
) -> tuple[FAQItemProjection, ...]:
    """Project dynamic operational answers plus published curated answers."""
    from shopman.shop.models import FAQEntry, Shop

    shop = shop or Shop.load()
    if shop is None:
        return ()

    items = _operational_faq(
        channel_ref=channel_ref,
        shop=shop,
        status=status,
        opening_hours=opening_hours,
    )
    items.extend(
        FAQItemProjection(
            ref=f"curated-{entry.ref}",
            question=entry.question.strip(),
            answer=entry.answer.strip(),
        )
        for entry in FAQEntry.objects.filter(is_published=True).order_by("position", "id")
    )
    return tuple(item for item in items if item.question and item.answer)


def search_public_faq(
    query: str,
    *,
    channel_ref: str,
    shop=None,
    limit: int = 4,
) -> tuple[FAQItemProjection, ...]:
    """Return public answers ranked by normalized token overlap."""
    from shopman.shop.models import FAQEntry

    items = build_public_faq(channel_ref=channel_ref, shop=shop)
    curated_search_terms = {
        f"curated-{ref}": terms
        for ref, terms in FAQEntry.objects.filter(is_published=True).values_list("ref", "search_terms")
    }
    needle = _fold(query).strip()
    if not needle:
        return items[:limit]
    terms = {term for term in needle.split() if len(term) >= 3}
    ranked: list[tuple[int, int, FAQItemProjection]] = []
    for index, item in enumerate(items):
        extra_terms = _OPERATIONAL_SEARCH_TERMS.get(item.ref, ())
        if item.ref.startswith("curated-"):
            extra_terms = tuple(
                term.strip() for term in curated_search_terms.get(item.ref, "").split(",") if term.strip()
            )
        haystack = _fold(f"{item.question} {item.answer} {' '.join(extra_terms)}")
        score = (10 if needle in haystack else 0) + sum(1 for term in terms if term in haystack)
        if score:
            ranked.append((-score, index, item))
    ranked.sort()
    return tuple(item for _, _, item in ranked[:limit])


__all__ = ["FAQItemProjection", "build_public_faq", "search_public_faq"]
