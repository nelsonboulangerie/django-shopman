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
