"""Ponte do estorno do Admin do Payman para o gateway (``PAYMAN["REFUND_BACKEND"]``).

O Admin de cobranças mora no Core (Payman) e não importa o orquestrador. Ele pede
o estorno por ``shopman.payman.protocols.RefundBackend``; esta classe atende pelo
mesmo caminho do estorno do pedido (``services.payment.refund_intent_at_gateway``,
que usa os adapters ``payment_efi``/``payment_stripe``). Uma implementação de
estorno só: esta classe traduz o resultado, não devolve dinheiro por conta própria.
"""

from __future__ import annotations

from shopman.payman.protocols import RefundResult


class GatewayRefundBackend:
    def refund(self, intent_ref: str, *, amount_q: int, idempotency_key: str, actor: str) -> RefundResult:
        from shopman.shop.services import payment

        result = payment.refund_intent_at_gateway(
            intent_ref, amount_q=amount_q, idempotency_key=idempotency_key, actor=actor
        )
        return RefundResult(
            success=result.success,
            refund_id=result.transaction_id,
            amount_q=result.amount_q,
            error_code=result.error_code,
            message=result.message,
        )
