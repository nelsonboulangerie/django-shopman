"""A cobrança deste pedido espera a fila?

Política da casa (28/08/2026): "Encomenda cobra antes. Fornada de hoje não
cobra para garantir vaga."

A casa assa a fornada de hoje de qualquer jeito: quem desiste devolve o pão à
gôndola, que o vende. Cobrar para guardar a vaga seria pedir garantia contra um
prejuízo que não existe. Então o pedido que entra na fila da fornada de hoje
não nasce cobrado: a cobrança nasce quando o cliente confirma a vaga
(``services.waitlist.confirm``), como a fila promete ("Nada foi cobrado ainda").

Fila é sempre da fornada de hoje. O pedido de hoje com item que só sai noutro
dia é recusado no commit (``policies.order_date_before_batch``): o cliente
escolhe a data, e com data combinada o pedido é ENCOMENDA, que não está na fila
e cobra antes, como sempre.

Quem pergunta é todo caminho que faz a cobrança NASCER fora da fila: o commit
(``lifecycle._should_initiate_payment_on_commit``) e a recuperação da tela de
acompanhamento (``services.customer_orders.ensure_payment_intent``). Dois
caminhos, uma régua: sem ela o segundo recriava o Pix que o primeiro deixou de
criar. Medido em 18/11/2026 (issue #2730): com ``payment.timing = at_commit`` o
Pix nascia no commit com o pedido em ``fermata``, e a fila nunca chegava a
confirmar ninguém.
"""

from __future__ import annotations


def charge_waits_for_the_queue(order) -> bool:
    """True enquanto a cobrança do pedido espera a fila da fornada.

    - ``fermata`` (a fornada ainda não saiu) e ``confirming`` (a loja chamou e
      espera o gesto do cliente): espera. É a confirmação que faz a cobrança
      nascer.
    - fora da fila (``none``), confirmado ou liberado: não espera.
    - encomenda e pedido pago nunca estão na fila (``waitlist.state_for``).

    O estado é lido da RESERVA do pedido, então no commit isto só responde
    certo depois de ``stock.hold``.
    """
    from shopman.shop.services import waitlist

    if waitlist.state_for(order) not in (waitlist.FERMATA, waitlist.CONFIRMING):
        return False
    return waitlist.config(order.channel_ref).charge_at == "confirmation"
