"""As frases dos cartões Retirada e Entrega do PDV (Recebimento e assistente da encomenda)."""

from __future__ import annotations

from shopman.backstage.projections.pos import _fulfillment_options


def test_cartoes_dizem_o_que_acontece_com_o_pedido_em_paralelo():
    options = {option.ref: option for option in _fulfillment_options(("pickup", "delivery"))}
    assert options["pickup"].description == "O cliente retira no balcão."
    assert options["delivery"].description == "O pedido vai até o endereço do cliente."
    # Nota de rodapé do engenheiro (omotenashi-copy, D6): quem digita o endereço não
    # é assunto do cartão.
    assert "operador" not in options["delivery"].description
