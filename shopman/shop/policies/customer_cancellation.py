"""A régua do cliente que quer cancelar (decisão do dono, 06/11/2026).

"Se for antes do preparo, cancelamos e reembolsamos. Se for depois, o pedido não
pode mais ser cancelado, e no máximo é encaminhado para falar com o gerente."

Antes do preparo o cliente cancela sozinho, pago ou não, e o dinheiro volta pelo
próprio cancelamento (``lifecycle._on_cancelled``). Depois, não há cancelar: há o
contato com o responsável (``customer_contact``, origem ``cancellation``).
"""

from __future__ import annotations

#: O preparo ainda não começou: o cliente cancela sozinho e o valor volta inteiro.
BEFORE_PREPARATION_STATUSES = frozenset({"new", "accepted"})

#: O preparo começou e o pedido ainda não chegou ao cliente: não cancela; o
#: cliente pode pedir para falar com o responsável.
AFTER_PREPARATION_STATUSES = frozenset({"preparing", "ready", "dispatched"})


def can_self_cancel(status: str, *, payment_status: str) -> bool:
    """O cliente cancela sozinho: antes do preparo, com o pagamento legível.

    ``unknown`` é o pagamento que não se consegue ler: cancelar sem saber se há
    dinheiro a devolver é o risco que a casa não corre sem uma pessoa olhando.
    """
    return str(status) in BEFORE_PREPARATION_STATUSES and str(payment_status or "").lower() != "unknown"


def offers_contact_instead(status: str) -> bool:
    """O preparo começou: no lugar do cancelar, o contato com o responsável."""
    return str(status) in AFTER_PREPARATION_STATUSES
