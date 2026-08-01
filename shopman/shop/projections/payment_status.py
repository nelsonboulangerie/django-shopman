"""Payment status — read-side polling flags (surface-agnostic).

Depois da fusão PAYMENT-TRACKING-MERGE, o pagamento é um degrau do próprio
acompanhamento (``shop.projections.order_tracking``): não há mais tela de
pagamento nem máquina de estados de pagamento à parte — o bloco de Pix/cartão
viaja como dado na promessa do acompanhamento.

O que sobra aqui é o mínimo que o PDV (operador) consome para saber se o Pix no
balcão já caiu: os flags terminais pago/cancelado/expirado. A regra de política
(captura suficiente, prazo vencido) continua em ``shop.services.payment_status``;
este módulo só a projeta como dado de polling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shopman.shop.services import payment_status as payment_policy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaymentStatusData:
    """Flags terminais do pagamento por pedido — dado, sem tela."""

    order_ref: str
    order_status: str
    is_paid: bool
    is_cancelled: bool
    is_expired: bool
    is_terminal: bool


def build_payment_status(order) -> PaymentStatusData:
    """Flags de polling do pagamento (o PDV usa para ver o Pix cair no balcão)."""
    payment = (order.data or {}).get("payment") or {}
    is_paid, is_cancelled, is_expired = _payment_flags(
        order=order,
        expires_at_str=payment.get("expires_at"),
    )
    return PaymentStatusData(
        order_ref=order.ref,
        order_status=str(getattr(order, "status", "") or ""),
        is_paid=is_paid,
        is_cancelled=is_cancelled,
        is_expired=is_expired,
        is_terminal=is_paid or is_cancelled or is_expired,
    )


def _payment_flags(*, order, expires_at_str: str | None) -> tuple[bool, bool, bool]:
    is_paid = payment_policy.has_sufficient_captured_payment(order)
    is_cancelled = order.status == "cancelled"
    # A regra da expiração mora em services.payment_status — a mesma que o
    # acompanhamento usa. Duas cópias eram o que fazia as telas discordarem.
    is_expired = payment_policy.deadline_passed(order, expires_at_str)
    return is_paid, is_cancelled, is_expired


__all__ = [
    "PaymentStatusData",
    "build_payment_status",
]
