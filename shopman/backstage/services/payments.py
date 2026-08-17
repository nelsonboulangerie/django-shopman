"""Como o dinheiro de um pedido se reparte entre formas de pagamento.

Uma pergunta, um dono. Esta regra nasceu dentro do fechamento do dia e era o
único lugar que sabia ler ``order.data.payment`` — o B.I. que quisesse contar o
mesmo dinheiro teria de reimplementá-la, e as duas telas divergiriam no primeiro
caso de borda (pagamento dividido, cobrança na entrega ainda não recebida). Por
isso ela mora aqui, e tanto ``services/closing.py`` quanto
``projections/bi_payments.py`` a chamam em vez de reescrevê-la.

Três fatos que a regra precisa respeitar:

- **Pedido pode ter mais de um pagamento.** O PDV aceita divisão
  (``payment.tenders``), e nesse caso é a soma dos tenders que vale, não o total
  do pedido.
- **Pedido antigo/simples não tem tenders**, só ``payment.method`` — aí o valor
  é o total do pedido.
- **Cobrança na entrega ainda não recebida NÃO é dinheiro recebido.** Ela existe
  (é receita a receber) e por isso sai marcada, em vez de sumir: quem soma
  recebido a ignora, quem quer saber o que está na rua a encontra.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

# Sem forma declarada o pedido não vira "desconhecido": ``external`` é o que o
# fechamento já usava, e trocar isso aqui reescreveria relatórios antigos.
DEFAULT_METHOD = "external"


@dataclass(frozen=True)
class OrderPayment:
    """Uma parcela do pagamento de um pedido."""

    method: str
    amount_q: int
    pending: bool
    """Cobrança na entrega ainda não recebida. Não é dinheiro em caixa."""


def iter_order_payments(data: dict | None, total_q: int | None) -> Iterator[OrderPayment]:
    """Reparte o valor de um pedido entre as formas de pagamento usadas."""
    payment = (data or {}).get("payment") or {}
    tenders = payment.get("tenders") or []

    if tenders:
        for tender in tenders:
            method = str(tender.get("method") or DEFAULT_METHOD)
            collection = str(tender.get("collection") or "terminal")
            status = str(tender.get("status") or "")
            yield OrderPayment(
                method=method,
                amount_q=int(tender.get("amount_q") or 0),
                pending=collection == "on_delivery" and status != "received",
            )
        return

    yield OrderPayment(
        method=str(payment.get("method") or DEFAULT_METHOD),
        amount_q=int(total_q or 0),
        pending=(
            payment.get("collection") == "on_delivery"
            and not payment.get("cod_settled_at")
        ),
    )
