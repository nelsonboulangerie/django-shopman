"""Como o PEDIDO declara que foi pago — a repartição entre formas de pagamento.

Uma pergunta, um dono. Esta regra lê ``order.data.payment`` e responde o que só
o pedido sabe: como o cliente declarou pagar (método, tenders, troco) e se uma
cobrança na entrega ainda está na rua. É isso que o fiscal, o recibo e o recorte
do B.I. por contexto do pedido (hora, canal) precisam.

⚠️ NÃO é fonte de caixa nem de receita por método (ADR-022). "Quanto entrou, por
método" é do ``payman`` (intents capturados de TODOS os métodos, dinheiro
incluso); "quanto há na gaveta" é do ``cashman``. O fechamento do dia
(``services/closing.py``) usa esta função só para o pendente de entrega
(``cod_pending_*``); o mix de meios ele lê do ``payman``.

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
