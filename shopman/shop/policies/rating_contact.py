"""Decide se a avaliação do cliente oferece o contato da ouvidoria."""

from __future__ import annotations

#: Nota 3 costuma ser "não foi ruim, mas algo incomodou": é aí que um contato
#: mais salva cliente (dono, 27/10/2026). O aviso urgente ``low_rating`` segue em 2.
CONTACT_MAX_RATING = 3


def can_request_contact(rating: int | None, *, already_requested: bool) -> bool:
    """Nota até ``CONTACT_MAX_RATING`` oferece o contato, uma vez por pedido."""
    if already_requested or not rating:
        return False
    return int(rating) <= CONTACT_MAX_RATING
