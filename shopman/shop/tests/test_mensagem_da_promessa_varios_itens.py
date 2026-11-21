"""A mensagem do "Resolver" com vários itens: uma oração por situação (#2809 item 5).

Decisão da coordenação em 21/11/2026, com o mandato do dono: os itens na mesma
situação viram uma frase só ("os itens Focaccia e Brioche não vão ficar prontos
amanhã"); situações diferentes seguem uma oração cada, e a falta em parte fica
sozinha, porque cada item diz quanto falta dele.
"""

from __future__ import annotations

from shopman.shop.notification_copy import promise_proposal


def _message(*items: dict[str, str]) -> str:
    return promise_proposal(
        "reschedule", shop_name="Nelson Boulangerie", customer_name="Ana", order_ref_short="A17", items=list(items),
    )


def _item(name: str, situation: str, day: str = " amanhã", lacking: str = "") -> dict[str, str]:
    return {"name": name, "situation": situation, "day": day, "lacking": lacking}


def test_dois_itens_na_mesma_situacao_viram_uma_oracao():
    message = _message(_item("Focaccia", "not_ready"), _item("Brioche", "not_ready"))
    assert "No seu pedido A17, os itens Focaccia e Brioche não vão ficar prontos amanhã, e sinto muito por isso." in message


def test_tres_itens_na_mesma_situacao_listam_com_virgula_e_e():
    message = _message(_item("Focaccia", "out_of_stock", ""), _item("Brioche", "out_of_stock", ""), _item("Fendu", "out_of_stock", ""))
    assert "os itens Focaccia, Brioche e Fendu estão em falta, e sinto muito" in message


def test_situacoes_diferentes_seguem_uma_oracao_cada():
    message = _message(_item("Focaccia", "not_ready"), _item("Brioche", "late", ""), _item("Fendu", "not_ready"))
    assert (
        "No seu pedido A17, os itens Focaccia e Fendu não vão ficar prontos amanhã "
        "e o item Brioche está atrasado, e sinto muito por isso."
    ) in message


def test_o_mesmo_estado_em_dias_diferentes_nao_se_junta():
    message = _message(_item("Focaccia", "not_ready", " amanhã"), _item("Brioche", "not_ready", " para sábado, 21/11"))
    assert (
        "o item Focaccia não vai ficar pronto amanhã e o item Brioche não vai ficar pronto para sábado, 21/11"
    ) in message


def test_a_falta_em_parte_fica_sozinha_com_quanto_falta():
    message = _message(
        _item("Focaccia", "not_ready_partial", lacking="faltam 2 de 4"),
        _item("Brioche", "not_ready"),
        _item("Fendu", "not_ready"),
    )
    assert (
        "o item Focaccia não vai ficar pronto por inteiro amanhã (faltam 2 de 4) "
        "e os itens Brioche e Fendu não vão ficar prontos amanhã"
    ) in message


def test_um_item_so_segue_a_frase_de_um_item():
    message = _message(_item("Focaccia", "not_ready"))
    assert "O item Focaccia do seu pedido A17 não vai ficar pronto amanhã, e sinto muito por isso." in message
