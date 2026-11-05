"""Canonical public information shared by the storefront and Concierge."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from shopman.shop.projections.channel_state import channel_capabilities
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
    "payment": ("pagamento", "pagar", "pix", "cartão", "cartao", "crédito", "credito"),
    "preorder": ("encomenda", "encomendar", "agendar", "reservar", "data"),
    "allergens": ("alérgeno", "alergenos", "alergia", "glúten", "gluten", "lactose", "restrição"),
}

#: Como o cliente chama cada forma de pagamento do canal (``ChannelConfig.payment``).
_PAYMENT_LABELS = {
    "pix": "Pix",
    "card": "cartão",
    "credit": "cartão de crédito",
    "debit": "cartão de débito",
    "cash": "dinheiro",
}


def _join_pt(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " ou " + parts[-1]


def _payment_faq(channel_ref: str) -> FAQItemProjection | None:
    from shopman.shop.config import ChannelConfig

    method = ChannelConfig.for_channel(channel_ref).payment.method
    methods = [method] if isinstance(method, str) else list(method or [])
    labels: list[str] = []
    for item in methods:
        label = _PAYMENT_LABELS.get(str(item))
        if label and label not in labels:
            labels.append(label)
    if not labels:
        return None
    return FAQItemProjection(
        ref="payment",
        question="Como posso pagar?",
        answer=f"Pelo site, você paga com {_join_pt(labels)}.",
    )


def _preorder_faq(channel_ref: str) -> FAQItemProjection | None:
    from shopman.shop.config import ChannelConfig
    from shopman.shop.services.preorder_dates import max_preorder_days

    if not ChannelConfig.for_channel(channel_ref).stock.preorder:
        return None
    days = max_preorder_days()
    if days <= 0:
        return None
    window = "1 dia" if days == 1 else f"{days} dias"
    return FAQItemProjection(
        ref="preorder",
        question="Vocês aceitam encomendas?",
        answer=f"Sim. Ao finalizar o pedido, você escolhe o dia, com até {window} de antecedência.",
    )


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
    policy = channel_capabilities(channel_ref)
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

    # O subtítulo da página promete pagamento, encomendas e alérgenos; as respostas
    # saem da configuração da loja, nunca de texto inventado (beta 05/11, LOJA-07).
    for extra in (_payment_faq(channel_ref), _preorder_faq(channel_ref)):
        if extra is not None:
            items.append(extra)
    notice = food_safety_notice(shop)
    if notice:
        items.append(
            FAQItemProjection(
                ref="allergens",
                question="Os produtos têm alérgenos?",
                answer=f"{notice} Os ingredientes de cada produto estão na página dele.",
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


def food_safety_notice(shop=None) -> str:
    """O aviso de produção compartilhada da casa (``Shop.food_safety_notice``).

    Uma fonte só: é o texto que a página de cada produto mostra em Ingredientes
    e restrições e o que a Concierge responde sobre glúten. O gestor edita no
    Admin e os dois lugares mudam juntos.
    """
    from shopman.shop.models import Shop

    shop = shop or Shop.load()
    return (getattr(shop, "food_safety_notice", "") or "").strip() if shop else ""


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


__all__ = ["FAQItemProjection", "build_public_faq", "food_safety_notice", "search_public_faq"]
