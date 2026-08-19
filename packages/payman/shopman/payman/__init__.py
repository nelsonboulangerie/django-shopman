"""
Shopman Payman — Payment Lifecycle Management.

Usage:
    from shopman.payman import PaymentService, PaymentError

    intent = PaymentService.create_intent("ORD-001", 1500, "pix")
    PaymentService.authorize(intent.ref, gateway_id="efi_txid_123")
    tx = PaymentService.capture(intent.ref)
    PaymentService.refund(intent.ref, amount_q=500, reason="item danificado")

    # Sem gateway (dinheiro no balcão, cobrança externa): nasce capturado.
    intent = PaymentService.settle("ORD-002", 1500, "cash")

7 verbos: create_intent, settle, authorize, capture, refund, cancel, fail.
Reconciliação: reconcile_gateway_status (snapshot cumulativo do gateway).
Consultas: get, get_by_order, get_by_gateway_id, get_active_intent
(cobrança de pé — pendente ou autorizada, nunca capturada).
Somas: captured_total, refunded_total, chargeback_total.

Philosophy: SIREL (Simples, Robusto, Elegante)
"""

from shopman.payman.exceptions import PaymentError


def __getattr__(name):
    """Lazy import to avoid AppRegistryNotReady errors."""
    if name == "PaymentService":
        from shopman.payman.service import PaymentService

        return PaymentService
    if name == "PaymentIntent":
        from shopman.payman.models.intent import PaymentIntent

        return PaymentIntent
    if name == "PaymentTransaction":
        from shopman.payman.models.transaction import PaymentTransaction

        return PaymentTransaction
    if name == "PaymentReconciliationResult":
        from shopman.payman.service import PaymentReconciliationResult

        return PaymentReconciliationResult
    # Protocol DTOs (no DB dependency, safe to import eagerly)
    _protocol_names = {"GatewayIntent", "CaptureResult", "RefundResult", "PaymentStatus", "PaymentBackend"}
    if name in _protocol_names:
        import shopman.payman.protocols as _p

        return getattr(_p, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PaymentService",
    "PaymentError",
    "PaymentIntent",
    "PaymentTransaction",
    "PaymentReconciliationResult",
    # Protocols (gateway DTOs)
    "GatewayIntent",
    "CaptureResult",
    "RefundResult",
    "PaymentStatus",
    "PaymentBackend",
]

__version__ = "0.2.0"
