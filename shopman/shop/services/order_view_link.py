"""O link do aviso abre O pedido, e só ele (DEV-2026-093, atualização da D5/X6 em 25/11/2026).

O cliente chega pelo site, entra pelo WhatsApp, recebe o aviso no WhatsApp e toca no
link do pedido. O link abre no navegador embutido do WhatsApp, que não tem a sessão
do site, e a loja pedia para entrar de novo. A fala do dono: "Tem que ter uma forma de
resolver isso!!!".

A forma é uma **capacidade de pedido**: o link leva, num único segmento de URL, o ref e
um selo calculado pela casa (``/pedido/<ref>~<selo>``). O selo é um HMAC do
``SECRET_KEY`` sobre ``order-view``, o ref e a revisão do link (``view_link_rev`` em
``Order.data``). Sem estado no banco, como o selo do aviso de estoque
(``storefront/services/stock_alerts.py``).

O espírito da D5 continua: **o aviso nunca leva credencial de login ou de conta.** A
capacidade não entra na conta, não cria usuário, não lista pedidos, não abre a sacola
nem o canal de tempo real. Ela deixa VER este pedido e fazer o que o próprio aviso pede
(pagar, falar com a loja, confirmar o recebimento). Cancelar, pedir de novo e avaliar
pedem a entrada, e a tela mostra o endereço abreviado (ver
``customer_orders.order_access_mode``).

Validade: enquanto o pedido estiver aberto e mais sete dias depois de concluído,
cancelado ou devolvido. Revogar é trocar a revisão (``revoke``): todo link já enviado
deixa de abrir na hora, inclusive em navegador que já tinha trocado o selo.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

logger = logging.getLogger(__name__)

#: O que separa o ref do selo no segmento da URL. ``~`` é caractere não reservado
#: (RFC 3986), não aparece no ref (``orderman/ids.py``) nem no base64url do selo.
SEPARATOR = "~"

#: Chave de ``Order.data`` com a revisão do link (inteiro; ausente = 0).
REV_KEY = "view_link_rev"

#: Depois de concluído, cancelado ou devolvido, o link ainda abre por este tempo.
VALIDITY_AFTER_CLOSE = timedelta(days=7)

#: Estados em que o pedido terminou para o cliente, com o carimbo de cada um.
_CLOSED_AT_FIELDS = {
    "delivered": "delivered_at",
    "completed": "completed_at",
    "cancelled": "cancelled_at",
    "returned": "returned_at",
}

_SALT = "shopman.order-view"
#: 128 bits do HMAC-SHA256: 22 caracteres em base64url, sem padding.
_CAPABILITY_BYTES = 16


def link_rev(order) -> int:
    """A revisão atual do link do pedido (0 para quem nunca revogou)."""
    try:
        return int((order.data or {}).get(REV_KEY) or 0)
    except (TypeError, ValueError):
        return 0


def capability(order) -> str:
    """O selo do pedido na revisão atual: base64url, sem padding."""
    digest = salted_hmac(
        _SALT,
        f"order-view:{order.ref}:{link_rev(order)}",
        algorithm="sha256",
    ).digest()
    return base64.urlsafe_b64encode(digest[:_CAPABILITY_BYTES]).rstrip(b"=").decode("ascii")


def link_ref(order) -> str:
    """O segmento da URL que o aviso leva: ``<ref>~<selo>``."""
    return f"{order.ref}{SEPARATOR}{capability(order)}"


def split_link_ref(value: str) -> tuple[str, str]:
    """``"<ref>~<selo>"`` → ``(ref, selo)``; sem selo, ``(ref, "")``."""
    ref, sep, cap = str(value or "").strip().rpartition(SEPARATOR)
    if not sep:
        return cap, ""
    return ref, cap


def closed_at(order) -> datetime | None:
    """Quando o pedido terminou para o cliente, ou ``None`` se ainda está aberto.

    O primeiro carimbo de término que o pedido tem: entregue e depois concluído conta
    da entrega. Sem carimbo (dado antigo), o ``updated_at`` é a melhor aproximação.
    """
    if order.status not in _CLOSED_AT_FIELDS:
        return None
    stamps = [getattr(order, field, None) for field in _CLOSED_AT_FIELDS.values()]
    stamps = [stamp for stamp in stamps if stamp is not None]
    if stamps:
        return min(stamps)
    return getattr(order, "updated_at", None) or timezone.now()


def is_within_validity(order, *, now: datetime | None = None) -> bool:
    """Aberto, ou terminado há no máximo ``VALIDITY_AFTER_CLOSE``."""
    ended = closed_at(order)
    if ended is None:
        return True
    return (now or timezone.now()) <= ended + VALIDITY_AFTER_CLOSE


def verify(order, cap: str, *, now: datetime | None = None) -> bool:
    """O selo é DESTE pedido, na revisão atual, e o link ainda vale?"""
    if order is None or not cap:
        return False
    if not constant_time_compare(str(cap), capability(order)):
        return False
    return is_within_validity(order, now=now)


def revoke(order) -> int:
    """Troca a revisão do link: todo selo já enviado deixa de abrir. Devolve a nova."""
    from shopman.orderman.models import Order

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        data = dict(locked.data or {})
        rev = link_rev(locked) + 1
        data[REV_KEY] = rev
        locked.data = data
        locked.save(update_fields=["data"])
    order.data = data
    logger.info("order_view_link.revoked order=%s rev=%s", order.ref, rev)
    return rev


def path_for(order) -> str:
    """A página do pedido com o selo: ``/pedido/<ref>~<selo>``."""
    from shopman.shop.services import storefront_links

    return storefront_links.path_order_tracking(link_ref(order))


def url_for(order) -> str:
    """O link absoluto da loja para o pedido, com o selo."""
    from shopman.shop.services import storefront_links

    return storefront_links.storefront_url(path_for(order))


def path_for_ref(ref: str) -> str:
    """O caminho com selo a partir do ref (quem só tem o número na mão, como a Concierge)."""
    from shopman.shop.services import storefront_links
    from shopman.shop.services.customer_orders import find_order

    order = find_order(str(ref or ""))
    if order is None:
        return storefront_links.path_order_tracking(str(ref or ""))
    return path_for(order)


__all__ = [
    "REV_KEY",
    "SEPARATOR",
    "VALIDITY_AFTER_CLOSE",
    "capability",
    "closed_at",
    "is_within_validity",
    "link_ref",
    "link_rev",
    "path_for",
    "path_for_ref",
    "revoke",
    "split_link_ref",
    "url_for",
    "verify",
]
