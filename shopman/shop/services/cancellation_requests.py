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

# Termos §7 (versão 2026-09-25): o pedido pago ainda não preparado aceita
# desistência com devolução do valor inteiro. "Antes do preparo" é o pedido que
# não chegou a ``preparing`` — e vale o estado NO MOMENTO da solicitação, que o
# evento grava: se a cozinha começar depois, a promessa já estava feita.
BEFORE_PREPARATION_STATUSES = frozenset({Order.Status.NEW, Order.Status.ACCEPTED})


def operational_message(*, order_ref: str, protocol: str, before_preparation: bool) -> str:
    """O texto do alerta para o app de Pedidos, só com dado operacional.

    Fonte única: a solicitação escreve com ele, e a anonimização do titular
    reconstrói com ele (sem o motivo, que é texto pessoal).

    Antes do preparo, o alerta não pede "decisão": diz a regra dos Termos e o
    gesto que a cumpre. Cancelar pedido pago continua sob a assinatura do
    gerente (``operator_cancel_policy``); o estorno do Pix ou do cartão sai do
    próprio cancelamento (``lifecycle._on_cancelled`` → ``payment.refund``).
    """
    protocol_copy = f" Protocolo {protocol}." if protocol else ""
    if before_preparation:
        action = (
            "O pedido ainda não estava em preparo: pelos Termos (§7), a desistência vale e o "
            "valor volta inteiro. Cancele o pedido; o estorno do Pix ou do cartão sai sozinho."
        )
    else:
        action = "Abra o pedido para decidir o cancelamento e eventual estorno."
    return f"O cliente solicitou análise de cancelamento do pedido {order_ref}.{protocol_copy} {action}"


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
    before_preparation = locked.status in BEFORE_PREPARATION_STATUSES
    event = locked.emit_event(
        EVENT_TYPE,
        actor="customer:self-service",
        payload={
            "protocol": protocol,
            "reason": clean_reason,
            "before_preparation": before_preparation,
        },
    )
    message = operational_message(
        order_ref=locked.ref,
        protocol=protocol,
        before_preparation=before_preparation,
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
