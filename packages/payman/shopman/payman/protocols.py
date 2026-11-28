"""
Payment Protocols — Interfaces para backends de gateway.

Os DTOs e protocols definem o contrato entre os handlers do App
e os backends de gateway (Mock, Efi, Stripe, etc.).

O PaymentService (service.py) gerencia o lifecycle no DB.
Os backends implementam a comunicação com o gateway externo.

Uso:
    from shopman.payman.protocols import PaymentBackend, GatewayIntent, CaptureResult
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class GatewayIntent:
    """Intenção de pagamento retornada pelo gateway."""

    intent_id: str
    status: str  # "pending", "authorized", "requires_action", "captured", "failed"
    amount_q: int
    currency: str
    client_secret: str | None = None  # Para frontend (Stripe Elements, QR code, etc)
    expires_at: datetime | None = None
    metadata: dict | None = None


@dataclass(frozen=True)
class CaptureResult:
    """Resultado de captura/autorização."""

    success: bool
    transaction_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class RefundResult:
    """Resultado de reembolso."""

    success: bool
    refund_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class PaymentStatus:
    """Status atual do pagamento no gateway."""

    intent_id: str
    status: str  # "pending", "authorized", "captured", "refunded", "failed", "cancelled"
    amount_q: int
    captured_q: int
    refunded_q: int
    currency: str
    metadata: dict | None = None


@runtime_checkable
class PaymentBackend(Protocol):
    """
    Protocol para backends de pagamento (gateway).

    Implementações:
    - channels.backends.payment_mock.MockPaymentBackend
    - channels.backends.payment_efi.EfiPixBackend
    - channels.backends.payment_stripe.StripeBackend
    """

    def create_intent(
        self,
        amount_q: int,
        currency: str,
        *,
        reference: str | None = None,
        metadata: dict | None = None,
    ) -> GatewayIntent: ...

    def authorize(
        self,
        intent_id: str,
        *,
        payment_method: str | None = None,
    ) -> CaptureResult: ...

    def capture(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reference: str | None = None,
    ) -> CaptureResult: ...

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult: ...

    def cancel(self, intent_id: str) -> bool: ...

    def get_status(self, intent_id: str) -> PaymentStatus: ...


@runtime_checkable
class RefundBackend(Protocol):
    """Quem devolve o dinheiro de uma cobrança pelo gateway dela.

    O Payman sabe quanto entrou e quanto saiu; não sabe falar com a Efí nem com a
    Stripe. O Admin de cobranças estorna por este contrato, configurado em
    ``PAYMAN["REFUND_BACKEND"]`` (caminho pontuado de uma classe), para que o
    dinheiro saia pelo MESMO caminho que o resto do sistema usa, sem o Core
    importar o orquestrador. Sem backend configurado, o Admin não estorna: gravar
    no livro um estorno que não saiu do gateway afirmaria que o cliente recebeu.

    O backend devolve pelo gateway e registra no Payman (``PaymentService.refund``)
    na mesma operação. ``idempotency_key`` é estável por gesto: a mesma chave
    reapresentada não devolve duas vezes. ``actor`` é quem pediu o estorno, e vai
    para o motivo da transação. Recusa e falha voltam como ``success=False`` com
    ``message`` em português, pronta para a tela; nada é gravado nesse caso.
    """

    def refund(
        self,
        intent_ref: str,
        *,
        amount_q: int,
        idempotency_key: str,
        actor: str,
    ) -> RefundResult: ...
