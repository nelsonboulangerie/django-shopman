"""
Payment Signals.

Sinais emitidos pelo PaymentService durante o lifecycle de um PaymentIntent.

Uso:
    from shopman.payman.signals import payment_captured

    @receiver(payment_captured)
    def on_payment_captured(sender, intent, order_ref, amount_q, **kwargs):
        print(f"Pagamento {intent.ref} capturado: {amount_q}q")

Entrega DEPOIS do COMMIT
------------------------

Todo anúncio sai por ``transaction.on_commit`` (``PaymentService._announce``):
o receiver só é chamado quando o dinheiro já é fato no banco, e uma exceção
dele não derruba a cobrança. Duas consequências para quem escuta:

* dentro de um bloco atômico o receiver roda no fim, fora dele; um rollback
  descarta o anúncio junto com o pagamento (nada de efeito fantasma);
* ``intent`` é a instância viva, não um retrato do instante do fato — quando
  um verbo encadeia transições (``reconcile_gateway_status`` autorizando e
  capturando no mesmo snapshot) o receiver lê o estado FINAL. Para o valor
  exato de cada etapa use ``transaction`` (linha imutável) ou releia o banco.

Consumidor real hoje: o fan-out SSE do orquestrador
(``shopman/shop/handlers/_sse_emitters.py``, ``_on_payment_changed``).

Sinais disponíveis:
    payment_authorized — Intent autorizado (pending → authorized)
    payment_captured   — Intent capturado (authorized → captured)
    payment_failed     — Intent falhou (→ failed)
    payment_cancelled  — Intent cancelado (→ cancelled)
    payment_refunded   — Reembolso registrado (parcial ou total)
"""

from django.dispatch import Signal

# kwargs: intent (PaymentIntent), order_ref (str), amount_q (int), method (str)
payment_authorized = Signal()

# kwargs: intent (PaymentIntent), order_ref (str), amount_q (int), transaction (PaymentTransaction)
payment_captured = Signal()

# kwargs: intent (PaymentIntent), order_ref (str), error_code (str), message (str)
payment_failed = Signal()

# kwargs: intent (PaymentIntent), order_ref (str)
payment_cancelled = Signal()

# kwargs: intent (PaymentIntent), order_ref (str), amount_q (int), transaction (PaymentTransaction)
payment_refunded = Signal()
