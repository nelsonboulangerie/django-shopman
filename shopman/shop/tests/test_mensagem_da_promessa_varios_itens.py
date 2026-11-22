"""A mensagem do "Resolver": uma oração por situação, sem depender do gênero do produto.

#2809 item 5 (coordenação, 21/11/2026, com o mandato do dono): os itens na mesma
situação viram uma frase só; situações diferentes seguem uma oração cada, e a falta
em parte fica sozinha, porque cada item diz quanto falta dele.

#2809 item 6 (coordenação, 22/11/2026, reversível; prévia em previa-2809-itens-6-7.png):
o catálogo não sabe se o produto é "o" ou "a", e "O item Focaccia" soava como sistema.
A oração carrega o nome sem concordar com ele: "não vamos ter Focaccia amanhã".
"""

from __future__ import annotations

import pytest

from shopman.shop.notification_copy import PROMISE_ITEM_SITUATION, promise_proposal


def _message(*items: dict[str, str]) -> str:
    return promise_proposal(
        "reschedule", shop_name="Nelson Boulangerie", customer_name="Ana", order_ref_short="A17", items=list(items),
    )


def _item(name: str, situation: str, day: str = " amanhã", lacking: str = "") -> dict[str, str]:
    return {"name": name, "situation": situation, "day": day, "lacking": lacking}


def test_um_item_so_diz_o_fato_sem_o_genero_do_produto():
    message = _message(_item("Focaccia", "not_ready"))
    assert message == (
        "Oi, Ana! Aqui é da Nelson Boulangerie 💛 No seu pedido A17, não vamos ter Focaccia amanhã, "
        "e sinto muito por isso. Posso remarcar o seu pedido para outro dia? Me diz qual fica melhor para você ✨"
    )


def test_dois_itens_na_mesma_situacao_viram_uma_oracao():
    message = _message(_item("Focaccia", "not_ready"), _item("Brioche", "not_ready"))
    assert "No seu pedido A17, não vamos ter Focaccia e Brioche amanhã, e sinto muito por isso." in message


def test_tres_itens_na_mesma_situacao_listam_com_virgula_e_e():
    message = _message(_item("Focaccia", "out_of_stock", ""), _item("Brioche", "out_of_stock", ""), _item("Fendu", "out_of_stock", ""))
    assert "No seu pedido A17, estamos sem Focaccia, Brioche e Fendu, e sinto muito" in message


def test_situacoes_diferentes_seguem_uma_oracao_cada():
    message = _message(_item("Focaccia", "not_ready"), _item("Brioche", "late", ""), _item("Fendu", "not_ready"))
    assert (
        "No seu pedido A17, não vamos ter Focaccia e Fendu amanhã "
        "e o preparo de Brioche atrasou, e sinto muito por isso."
    ) in message


def test_o_mesmo_estado_em_dias_diferentes_nao_se_junta():
    message = _message(_item("Focaccia", "not_ready", " amanhã"), _item("Brioche", "not_ready", " para sábado, 21/11"))
    assert "não vamos ter Focaccia amanhã e não vamos ter Brioche para sábado, 21/11" in message


def test_a_falta_em_parte_fica_sozinha_com_quanto_falta():
    message = _message(
        _item("Focaccia", "not_ready_partial", lacking="faltam 2 de 4"),
        _item("Brioche", "not_ready"),
        _item("Fendu", "not_ready"),
    )
    assert (
        "vamos ter menos Focaccia do que você pediu amanhã (faltam 2 de 4) "
        "e não vamos ter Brioche e Fendu amanhã"
    ) in message


@pytest.mark.parametrize("situation", sorted(PROMISE_ITEM_SITUATION))
def test_nenhuma_situacao_concorda_com_o_produto(situation):
    """O nome entra sem artigo nem adjetivo que dependa dele ("A Focaccia", "pronta")."""
    message = _message(_item("Focaccia", situation, lacking="falta 1 de 3"))
    assert "Focaccia" in message
    for gendered in ("O item", "o item Focaccia", "A Focaccia", "a Focaccia", "pronto", "pronta", "atrasad"):
        assert gendered not in message, f"{situation}: {gendered!r} em {message!r}"
    assert "—" not in message
