"""
Canonical DTOs for payment adapter contracts.

All payment adapters (mock, stripe, efi) MUST return these dataclasses from
their public functions. The orchestrating service (shopman.services.payment)
consumes them by attribute access — no dict lookups, no `.get()`.

This is the contract between framework/shopman/services/payment.py and the
adapter modules in framework/shopman/adapters/payment_*.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PaymentIntent:
    """Result of `adapter.create_intent()`.

    `intent_ref` is the canonical id, aligned with `payman.PaymentService.ref`
    (the DB row ref). The orchestrator persists this in
    `order.data["payment"]["intent_ref"]`.
    """

    intent_ref: str
    status: str  # "pending" | "authorized" | "requires_action" | "captured" | ...
    amount_q: int
    currency: str = "BRL"
    client_secret: str | None = None
    expires_at: datetime | None = None
    gateway_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PaymentResult:
    """Result of `adapter.capture()`, `refund()`, `cancel()`.

    `success=False` carries `error_code` + `message`. On success, `transaction_id`
    is the gateway-side identifier (e.g. Stripe charge id, EFI e2e id).
    """

    success: bool
    transaction_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None
    # Cartão: "credit" | "debit" | "prepaid" | "unknown", como o gateway informa
    # DEPOIS da captura. Só a Stripe preenche; é o que separa 03 de 04 na NFC-e.
    card_funding: str | None = None


def pix_timeout_minutes_from(config: dict) -> int:
    """O prazo do Pix que o orquestrador decidiu, em minutos. Sem default.

    Fonte única: ``services.payment._adapter_config`` (o ``timeout_minutes`` do
    canal, ou o prazo do link na encomenda do PDV). Antes o adapter caía num
    segundo número quando a chave não vinha (``SHOPMAN_PIX_EXPIRY_SECONDS`` na
    Efí, 30 no simulador): o QR vencia num relógio e o pedido cancelava em outro.
    """
    raw = config.get("pix_timeout_minutes")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError(
            f"pix_timeout_minutes ausente ou inválido ({raw!r}): o prazo do Pix vem "
            "do canal (ChannelConfig.payment.timeout_minutes)"
        )
    return raw
