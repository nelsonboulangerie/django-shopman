"""O motivo "Não retirado" e o que o cliente lê sobre ele (WP-G11).

``not_picked_up`` não é motivo de "Cancelar pedido" nem cancelamento automático:
é o encerramento que um Gerente assina no Gestor, por gesto próprio
(``services/no_show``), para o pedido de retirada que ficou pronto e o cliente
não veio buscar. Por isso a chave nasce aqui, fora da lista que o operador
escolhe; ``services/cancel_reasons`` só a conhece para resolver rótulo e texto.

O texto diz o destino do dinheiro a partir do bloco ``order.data["no_show"]``,
com a regra dos Termos (24/11/2026, DEV-2026-089): a revenda e o que volta à venda
voltam inteiros, e dos itens feitos para a encomenda a loja retém até 40%. A
frase diz quanto volta e quanto fica, e não o porquê de cada centavo: a conta
linha a linha está no recibo.

Voz da casa: frase inteira com ponto final (entra no ``{status_note}`` do aviso
``order_cancelled``, entre "foi cancelado." e "Qualquer dúvida…"), sem
travessão, sem culpar o cliente.
"""

from __future__ import annotations

KEY = "not_picked_up"
LABEL = "Não retirado"

#: O fato, sem dinheiro: é a frase inteira do pedido que não foi pago. Com o
#: sujeito escrito ("O pedido"), porque a frase também é lida sozinha, fora do
#: aviso: na prévia do Gestor ("Mensagem que o cliente vai receber") e na página
#: do pedido. Um pronome no lugar do sujeito só teria a quem se referir colado
#: em "Seu pedido foi cancelado."
BASE_TEXT = "O pedido ficou pronto e não foi retirado."

#: Quando a loja ficou com dinheiro, há recibo (#3538), e o aviso diz onde ele
#: está: o link do pedido que fecha a mensagem. A página do pedido não repete a
#: frase, porque o recibo está nela.
RECEIPT_HINT = "O recibo desse valor está no link do pedido."


def customer_text(no_show: dict | None, *, receipt_hint: bool = True) -> str:
    """A frase do "Não retirado" com o destino do dinheiro.

    Com ``receipt_hint`` e dinheiro retido pela loja, termina dizendo onde está
    o recibo (:data:`RECEIPT_HINT`).

    - nada foi pago: só o fato, sem frase de dinheiro;
    - tudo volta: quanto, e que vai voltar pelo mesmo meio de pagamento;
    - nada volta (tudo se perdeu): o valor ficou com a loja, conforme os Termos do serviço;
    - volta uma parte: as duas metades, para o cliente não procurar a diferença.
    """
    block = no_show if isinstance(no_show, dict) else {}
    text = _money_text(block)
    if receipt_hint and kept_money_q(block) > 0:
        return f"{text} {RECEIPT_HINT}"
    return text


def kept_money_q(no_show: dict | None) -> int:
    """O dinheiro que a loja RECEBEU e reteve: o valor do recibo.

    A compra na conta da casa não tem dinheiro recebido (o retido continua como
    dívida). Na venda mista, é o ``kept_q``. Nas outras, o retido de um pedido pago.
    """
    block = no_show if isinstance(no_show, dict) else {}
    if block.get("on_account"):
        return 0
    if "kept_q" in block:
        return _amount(block.get("kept_q"))
    if _amount(block.get("paid_q")) <= 0:
        return 0
    return _amount(block.get("retained_q"))


def _money_text(block: dict) -> str:
    from shopman.utils.monetary import format_money

    paid_q = _amount(block.get("paid_q"))
    refund_q = _amount(block.get("refund_q"))
    retained_q = _amount(block.get("retained_q"))
    if paid_q <= 0:
        return BASE_TEXT
    if block.get("on_account"):
        return _account_text(refund_q=refund_q, retained_q=retained_q)
    if "from_account_q" in block:
        return _mixed_text(block)
    if refund_q <= 0:
        return f"{BASE_TEXT} O valor ficou com a loja, conforme os Termos do serviço."
    # "Vamos devolver", no futuro, de propósito: quando o aviso sai, o gateway
    # só recebeu o pedido de estorno, e dinheiro e maquininha ainda esperam o
    # gesto de alguém da casa no PDV. "Devolvemos" afirmaria o que não aconteceu.
    refund = f"Vamos devolver R$ {format_money(refund_q)} pelo mesmo meio de pagamento"
    if retained_q > 0:
        return (
            f"{BASE_TEXT} {refund}. "
            f"R$ {format_money(retained_q)} ficaram com a loja, conforme os Termos do serviço."
        )
    return f"{BASE_TEXT} {refund}."


def _account_text(*, refund_q: int, retained_q: int) -> str:
    """A compra na conta da loja: o que saiu da conta e o que continua nela (#2697).

    "Tiramos", no passado, porque é verdade no instante do aviso: a conta muda
    junto com o encerramento, sem gateway nem gaveta no caminho.
    """
    from shopman.utils.monetary import format_money

    if refund_q <= 0:
        return f"{BASE_TEXT} O valor continua na sua conta na loja, conforme os Termos do serviço."
    out = f"Tiramos R$ {format_money(refund_q)} da sua conta na loja"
    if retained_q > 0:
        return (
            f"{BASE_TEXT} {out}. "
            f"R$ {format_money(retained_q)} continuam na conta, conforme os Termos do serviço."
        )
    return f"{BASE_TEXT} {out}."


def _mixed_text(block: dict) -> str:
    """Compra com parte na conta da loja (#3151): a conta sai primeiro, depois o dinheiro."""
    from shopman.utils.monetary import format_money

    from_account = _amount(block.get("from_account_q"))
    money = _amount(block.get("money_q"))
    debt_left = _amount(block.get("debt_left_q"))
    kept = _amount(block.get("kept_q"))
    back = []
    if from_account:
        back.append(f"Tiramos R$ {format_money(from_account)} da sua conta na loja")
    if money:
        back.append(f"{'e vamos' if back else 'Vamos'} devolver R$ {format_money(money)} pelo mesmo meio de pagamento")
    stay = []
    if debt_left:
        stay.append(f"R$ {format_money(debt_left)} continuam na sua conta")
    if kept:
        stay.append(f"R$ {format_money(kept)} ficaram com a loja")
    out = BASE_TEXT
    if back:
        out += " " + " ".join(back) + "."
    if stay:
        out += " " + " e ".join(stay) + ", conforme os Termos do serviço."
    return out


def _amount(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
