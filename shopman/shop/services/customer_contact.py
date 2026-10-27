"""Ouvidoria da avaliação: o cliente que não gostou pede que a casa fale com ele.

Depois de avaliar, quem deu nota até ``CONTACT_MAX_RATING`` vê a oferta de contato;
aceita, ela vira um caso no app de Pedidos (evento no pedido + aviso ``orders``) que
só fecha quando alguém da equipe marca "Resolvido", com uma nota do que foi feito.

O convite para publicar a opinião no Google é outra coisa e vale para TODA nota
(decisão do dono, 27/10/2026): a política do Google proíbe convidar só quem gostou.
A ouvidoria vem primeiro para quem não gostou; o convite continua lá para todos.

O caso mora nos eventos do pedido, como a solicitação de cancelamento: a abertura
é ``customer_contact_requested``, o fechamento é ``customer_contact_resolved``.
Não altera status, pagamento nem a avaliação.

O comentário do cliente NÃO é copiado para o evento nem para o aviso: ele mora só
em ``Order.data["customer_rating"]``, de onde a exclusão de conta o apaga. Cópia
em texto livre é PII que a anonimização não alcança.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from django.db import transaction
from shopman.orderman.models import Order

from shopman.shop.adapters import alert as alert_adapter

REQUESTED_EVENT = "customer_contact_requested"
RESOLVED_EVENT = "customer_contact_resolved"
ALERT_TYPE = "customer_contact_requested"

#: Nota 3 costuma ser "não foi ruim, mas algo incomodou": é aí que um contato
#: mais salva cliente (dono, 27/10/2026). O aviso urgente ``low_rating`` segue em 2.
CONTACT_MAX_RATING = 3

GOOGLE_REVIEW_URL = "https://search.google.com/local/writereview?placeid={place_id}"


class ContactRequestUnavailable(Exception):
    """The order has no rating that allows a contact request."""


class ContactRequestNotOpen(Exception):
    """There is no open contact request to resolve."""


@dataclass(frozen=True)
class ContactRequest:
    rating: int
    comment: str
    requested_at: datetime
    resolved: bool
    resolution_note: str = ""


def google_review_url() -> str:
    """O formulário de avaliação do Perfil da Empresa no Google, ou vazio sem Place ID."""
    from shopman.shop.models import Shop

    shop = Shop.load()
    place_id = (getattr(shop, "place_id", "") or "").strip()
    if not place_id:
        return ""
    return GOOGLE_REVIEW_URL.format(place_id=quote(place_id, safe=""))


def _rating(order: Order) -> dict:
    data = order.data if isinstance(order.data, dict) else {}
    rating = data.get("customer_rating")
    return rating if isinstance(rating, dict) and rating.get("rating") else {}


def current(order: Order) -> ContactRequest | None:
    requested = order.events.filter(type=REQUESTED_EVENT).order_by("-seq").first()
    if requested is None:
        return None
    resolved = order.events.filter(type=RESOLVED_EVENT, seq__gt=requested.seq).order_by("-seq").first()
    payload = requested.payload if isinstance(requested.payload, dict) else {}
    resolved_payload = resolved.payload if resolved is not None and isinstance(resolved.payload, dict) else {}
    return ContactRequest(
        rating=int(payload.get("rating") or 0),
        comment=str(_rating(order).get("comment") or ""),
        requested_at=requested.created_at,
        resolved=resolved is not None,
        resolution_note=str(resolved_payload.get("note") or ""),
    )


def open_request(order: Order) -> ContactRequest | None:
    request = current(order)
    return request if request is not None and not request.resolved else None


def can_offer(order: Order) -> bool:
    """A avaliação pede a oferta de contato, e ela ainda não foi aceita."""
    rating = _rating(order)
    if not rating or int(rating["rating"]) > CONTACT_MAX_RATING:
        return False
    return current(order) is None


def operational_message(*, order_ref: str, rating: int) -> str:
    return (
        f"O cliente do pedido {order_ref} deu nota {rating}/5 e pediu que a loja fale com ele. "
        "Abra o pedido para ler o comentário, chame no WhatsApp e marque Resolvido com o que foi feito."
    )


@transaction.atomic
def request_contact(order: Order) -> ContactRequest:
    """Record the customer's request once and route it durably to Orders."""
    locked = Order.objects.select_for_update().get(pk=order.pk)
    existing = current(locked)
    if existing is not None:
        return existing
    if not can_offer(locked):
        raise ContactRequestUnavailable
    rating = _rating(locked)
    score = int(rating["rating"])
    comment = str(rating.get("comment") or "")
    event = locked.emit_event(
        REQUESTED_EVENT,
        actor="customer:self-service",
        payload={"rating": score},
    )
    # Mesma transação: o cliente só ouve "a equipe vai te chamar" se o caso
    # chegou à fila do app de Pedidos.
    alert_adapter.create(
        ALERT_TYPE,
        "warning",
        operational_message(order_ref=locked.ref, rating=score),
        order_ref=locked.ref,
        audience="orders",
    )
    return ContactRequest(rating=score, comment=comment, requested_at=event.created_at, resolved=False)


@transaction.atomic
def resolve(order: Order, *, note: str, actor: str) -> ContactRequest:
    """Close the open request with what the team did, and clear its alert."""
    locked = Order.objects.select_for_update().get(pk=order.pk)
    request = open_request(locked)
    if request is None:
        raise ContactRequestNotOpen
    clean_note = str(note or "").strip()[:500]
    locked.emit_event(RESOLVED_EVENT, actor=actor, payload={"note": clean_note})
    alert_adapter.resolve(ALERT_TYPE, order_ref=locked.ref, actor=actor)
    return ContactRequest(
        rating=request.rating,
        comment=request.comment,
        requested_at=request.requested_at,
        resolved=True,
        resolution_note=clean_note,
    )
