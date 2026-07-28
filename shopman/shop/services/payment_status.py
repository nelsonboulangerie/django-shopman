"""Payment policy facade — write-side, surface-agnostic.

The thin policy seam over Payman used by the spine (lifecycle, handlers,
cancellation) and by the read-side projections. It answers *policy* questions
only — captured-payment sufficiency, live status, cancellability — never shapes
a payment page. The payment page read-model lives in
``shop.projections.payment_status`` (data) and ``storefront.presentation.payment``
(appearance).
"""

from __future__ import annotations

import logging

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from shopman.shop.services import payment as payment_service

logger = logging.getLogger(__name__)


def get_payment_status(order) -> str | None:
    """Return payment status from Payman via the payment service."""
    return payment_service.get_payment_status(order)


def has_sufficient_captured_payment(order) -> bool:
    """Return whether captured funds still cover the order total."""
    return payment_service.has_sufficient_captured_payment(order) is True


def can_cancel(order) -> bool:
    return payment_service.can_cancel(order)


__all__ = [
    "can_cancel",
    "get_payment_status",
    "has_sufficient_captured_payment",
]


def deadline_passed(order, expires_at_str: str | None) -> bool:
    """True quando o prazo informado venceu sem pagamento suficiente.

    Fonte ÚNICA da expiração de pagamento. Vive aqui, na camada de política,
    porque as duas projections que dependem dela (``order_tracking`` e
    ``payment_status``) já consomem este módulo — e porque a regra é de
    domínio, não de apresentação.

    Prazo malformado degrada para "não expirado": recusar o pagamento por
    causa de um parse ruim é pior do que deixar o cliente tentar.
    """
    if not expires_at_str:
        return False
    if has_sufficient_captured_payment(order):
        return False
    if getattr(order, "status", "") == "cancelled":
        return False
    try:
        expires_at = parse_datetime(str(expires_at_str))
    except Exception:
        logger.warning(
            "payment_deadline_parse_failed order=%s", getattr(order, "ref", "?"), exc_info=True
        )
        return False
    return bool(expires_at and timezone.now() > expires_at)


def payment_deadline_passed(order) -> bool:
    """Atalho para o prazo canônico do pagamento (``data.payment.expires_at``)."""
    raw = ((order.data or {}).get("payment") or {}).get("expires_at")
    return deadline_passed(order, raw)
