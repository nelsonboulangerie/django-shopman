"""
Channel protocols — contratos de backend consolidados.

Protocols que vivem no orderman core são re-exportados.
Protocols que viviam nos mini-apps são definidos inline aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ── Fiscal ── (vive na persona Fiscalman, re-export)
from shopman.fiscalman.contracts import (  # noqa: F401
    FiscalBackend,
)

# ── Accounting ── (vive no orderman core, re-export)
from shopman.orderman.protocols import (  # noqa: F401
    AccountingBackend,
)

# ── Payment ── (vivem no payments core, re-export)
from shopman.payman.protocols import (  # noqa: F401
    CaptureResult,
    GatewayIntent,
    PaymentBackend,
    PaymentStatus,
    RefundResult,
)

# ── Stock ── (vocabulário de promessa do Stockman, composto abaixo)
from shopman.stockman.protocols.sku import PromiseReasonCode

# Note: Stock no longer has a class-based protocol — the canonical entrypoint
# is the module `shopman.adapters.stock` (function-style adapter resolved via
# `get_adapter("stock")`). See ADR-001 for the protocol/adapter pattern.


class ReserveRefusal(StrEnum):
    """Vocabulário FECHADO da recusa de reserva no orquestrador.

    Compõe o ``PromiseReasonCode`` do Stockman (pausado, falta de oferta) com
    as recusas que só o orquestrador conhece: o portão da vitrine do canal, o
    portão do grupo (produto de coleção exclusiva, ``GROUP_EXCLUSIVE``, que a
    sacola e o checkout da loja recusam a quem não é do grupo), o SKU que o
    catálogo não tem e a quantidade inválida. Toda recusa de
    ``create_hold`` (adapter), ``availability.reserve`` e
    ``availability.reconcile`` sai daqui. Código cru do Stockman
    (``INSUFFICIENT_AVAILABLE``) não atravessa o adapter, e código que não
    está aqui é erro de programação: ``ReserveRefusal(code)`` levanta.
    """

    PAUSED = PromiseReasonCode.PAUSED.value
    INSUFFICIENT_SUPPLY = PromiseReasonCode.INSUFFICIENT_SUPPLY.value
    NOT_IN_LISTING = "not_in_listing"
    GROUP_EXCLUSIVE = "group_exclusive"
    PRODUCT_NOT_FOUND = "product_not_found"
    INVALID_QUANTITY = "invalid_quantity"


# ── Notification (inline — era shopman.notifications.protocols) ──


@dataclass(frozen=True)
class NotificationResult:
    """Resultado do envio."""

    success: bool
    message_id: str | None = None
    error: str | None = None
    outcome_unknown: bool = False
    #: Nada saiu e o provedor só pode ser chamado de novo depois deste prazo (ex.: o
    #: assinante já tem uma mensagem com flow assentando no ManyChat).
    retry_after_seconds: int | None = None


# ── Pricing (inline — era shopman.pricing.protocols) ──


__all__ = [
    # Payment
    "PaymentBackend",
    "GatewayIntent",
    "CaptureResult",
    "RefundResult",
    "PaymentStatus",
    # Fiscal
    "FiscalBackend",
    # Accounting
    "AccountingBackend",
    # Notification
    "NotificationResult",
]


# ── Entrega ── (DEV-2026-030, M1: um contrato, várias implementações)
#
# O módulo de cada serviço de entrega (hoje ``adapters/courier_machine``, a TaOn; na M2 o
# entregador da casa) declara o que sabe fazer em ``CAPABILITIES`` e traduz o seu estado
# próprio para o vocabulário da casa em ``ride_state``. A tela mostra só o que o serviço
# escolhido sabe fazer. Plano: docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md §2.2.


class RideState(StrEnum):
    """O estado de uma corrida no vocabulário da casa, igual para qualquer serviço."""

    SEARCHING = "searching"  # o serviço procura quem leve
    GROUPED = "grouped"  # o serviço juntou com outra corrida
    REASSIGNING = "reassigning"  # trocando de entregador
    ASSIGNED = "assigned"  # alguém aceitou ou foi designado
    AT_STORE = "at_store"  # o entregador está na loja
    ON_ROUTE = "on_route"  # saiu da loja com as sacolas
    DONE = "done"  # terminou
    NOT_SERVED = "not_served"  # ninguém atendeu
    CANCELLED = "cancelled"  # cancelada


@dataclass(frozen=True)
class DeliveryCapabilities:
    """O que um serviço de entrega sabe fazer. A tela esconde o que ele não sabe."""

    quote: bool  # cota antes de chamar
    multi_stop: int  # paradas por corrida (1 = uma só); o teto da casa vale por cima
    cancel_reasons: bool  # cancelar pede motivo da tabela do serviço
    customer_tracking: bool  # entrega link de rastreio por parada para o cliente
    push_status: bool  # avisa sozinho (webhook)
    door_charge: bool  # leva cobrança na porta, troco e maquininha
    needs_return: bool  # cobrança na porta exige corrida com volta
    assign: bool  # o operador escolhe a pessoa (a central não distribui)
