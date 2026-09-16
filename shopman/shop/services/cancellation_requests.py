"""Solicitação eletrônica de cancelamento pelo titular do pedido.

O cancelamento automático continua pertencendo à política canônica do pedido.
Quando essa janela fecha, este serviço registra a intenção do cliente, entrega
um protocolo estável e encaminha a análise para o app de Pedidos. Não altera
status, pagamento ou estoque por conta própria.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.adapters import alert as alert_adapter

EVENT_TYPE = "customer_cancellation_requested"
ALERT_TYPE = "customer_cancellation_requested"
TERMINAL_STATUSES = {Order.Status.CANCELLED, Order.Status.RETURNED}


class CancellationRequestUnavailable(Exception):
    """The order already has the requested terminal outcome."""


@dataclass(frozen=True)
class CancellationRequest:
    protocol: str
    reason: str
    requested_at: datetime


def current(order: Order) -> CancellationRequest | None:
    event = order.events.filter(type=EVENT_TYPE).order_by("-seq").first()
    if event is None:
        return None
    payload = event.payload if isinstance(event.payload, dict) else {}
    return CancellationRequest(
        protocol=str(payload.get("protocol") or ""),
        reason=str(payload.get("reason") or ""),
        requested_at=event.created_at,
    )


@transaction.atomic
def request_cancellation(order: Order, *, reason: str = "") -> CancellationRequest:
    """Record at most one open request and route it durably to Orders."""
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status in TERMINAL_STATUSES:
        raise CancellationRequestUnavailable

    existing = current(locked)
    if existing is not None:
        return existing

    requested_at = timezone.now()
    protocol = f"SC-{requested_at:%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    clean_reason = str(reason or "").strip()[:500]
    event = locked.emit_event(
        EVENT_TYPE,
        actor="customer:self-service",
        payload={"protocol": protocol, "reason": clean_reason},
    )
    message = (
        f"O cliente solicitou análise de cancelamento do pedido {locked.ref}. "
        f"Protocolo {protocol}. Abra o pedido para decidir o cancelamento e eventual estorno."
    )
    if clean_reason:
        message += f" Motivo informado: {clean_reason}"
    # A criação do alerta participa da mesma transação: nunca confirmamos ao
    # cliente uma solicitação que não chegou a uma fila operacional.
    alert_adapter.create(
        ALERT_TYPE,
        "warning",
        message,
        order_ref=locked.ref,
        audience="orders",
    )
    return CancellationRequest(
        protocol=protocol,
        reason=clean_reason,
        requested_at=event.created_at,
    )
