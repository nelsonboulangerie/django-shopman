"""O motivo "Não retirado" e o que o cliente lê sobre ele (WP-G11).

``not_picked_up`` não é motivo de "Cancelar pedido" nem cancelamento automático:
é o encerramento que um Gerente assina no Gestor, por gesto próprio
(``services/no_show``), para o pedido de retirada que ficou pronto e o cliente
não veio buscar. Por isso a chave nasce aqui, fora da lista que o operador
escolhe; ``services/cancel_reasons`` só a conhece para resolver rótulo e texto.

O texto diz o destino do dinheiro a partir do bloco ``order.data["no_show"]``,
porque a regra é "o dinheiro segue o produto": o que voltou à venda é devolvido,
o que se perdeu fica com a loja, como dizem os Termos.

Voz da casa: frase inteira com ponto final (entra no ``{status_note}`` do aviso
``order_cancelled``, entre "foi cancelado." e "Qualquer dúvida…"), sem
travessão, sem culpar o cliente.
"""

from __future__ import annotations

KEY = "not_picked_up"
LABEL = "Não retirado"

#: O fato, sem dinheiro: é a frase inteira do pedido que não foi pago.
BASE_TEXT = "Ele ficou pronto e não foi retirado."


def customer_text(no_show: dict | None) -> str:
    """A frase do "Não retirado" com o destino do dinheiro.

    - nada foi pago: só o fato, sem frase de dinheiro;
    - tudo volta: quanto, e que vai voltar pelo mesmo meio de pagamento;
    - nada volta (tudo se perdeu): o valor ficou com a loja, como dizem os Termos;
    - volta uma parte: as duas metades, para o cliente não procurar a diferença.
    """
    from shopman.utils.monetary import format_money

    block = no_show if isinstance(no_show, dict) else {}
    paid_q = _amount(block.get("paid_q"))
    refund_q = _amount(block.get("refund_q"))
    retained_q = _amount(block.get("retained_q"))
    if paid_q <= 0:
        return BASE_TEXT
    if refund_q <= 0:
        return f"{BASE_TEXT} O valor ficou com a loja, como dizem os Termos."
    # "Vamos devolver", no futuro, de propósito: quando o aviso sai, o gateway
    # só recebeu o pedido de estorno, e dinheiro e maquininha ainda esperam o
    # gesto de alguém da casa no PDV. "Devolvemos" afirmaria o que não aconteceu.
    refund = f"Vamos devolver R$ {format_money(refund_q)} pelo mesmo meio de pagamento"
    if retained_q > 0:
        return (
            f"{BASE_TEXT} {refund}, pelo que ainda pôde voltar à venda. "
            f"R$ {format_money(retained_q)} ficaram com a loja, como dizem os Termos."
        )
    return f"{BASE_TEXT} {refund}."


def _amount(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
