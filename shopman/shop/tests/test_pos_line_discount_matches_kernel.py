"""A review mede o desconto de LINHA como o kernel mede.

Regressão de dinheiro provada numa venda real (PDV-260826-V03): o checkout exibiu
total R$ 44,78 e TROCO R$ 25,22; o pedido selou R$ 45,80 e registrou troco
R$ 24,20. A diferença de R$ 1,02 era uma cortesia de 10% numa linha que já levava
"Semana do Pão −15%" — o kernel descarta ("maior desconto ganha, um por item") e
a review somava assim mesmo. O operador devolveria R$ 1,02 a mais do que a gaveta
contava, em TODA venda com desconto de linha perdedor.
"""

from shopman.shop.services.pos import _payload_line_discounts_q


def _payload(**item):
    base = {"sku": "TAB", "qty": 2, "unit_price_q": 510}
    base.update(item)
    return {"items": [base]}


def test_desconto_de_linha_que_PERDE_do_automatico_nao_entra_na_conta():
    # Etiqueta 6,00; automático já tirou 0,90 (unit 5,10). Manual de 10% sobre a
    # etiqueta = 0,60 < 0,90 → o kernel descarta, e a review não pode prometer.
    payload = _payload(
        list_price_q=600,
        discount={"type": "percent", "value": 10, "reason": "cortesia"},
    )
    assert _payload_line_discounts_q(payload) == 0


def test_desconto_de_linha_que_GANHA_entra_pela_DIFERENCA():
    # Etiqueta 6,00; automático 0,90. Manual de 30% = 1,80 > 0,90 → substitui.
    # O subtotal da review já é pós-automático (5,10), então o que ainda sai é a
    # diferença: 1,80 − 0,90 = 0,90 por unidade.
    payload = _payload(
        list_price_q=600,
        discount={"type": "percent", "value": 30, "reason": "cortesia"},
    )
    assert _payload_line_discounts_q(payload) == 90 * 2


def test_linha_sem_desconto_automatico_desconta_o_percentual_inteiro():
    payload = {
        "items": [{
            "sku": "PAO", "qty": 1, "unit_price_q": 500, "list_price_q": 500,
            "discount": {"type": "percent", "value": 10, "reason": "cortesia"},
        }],
    }
    assert _payload_line_discounts_q(payload) == 50


def test_sem_etiqueta_declarada_a_linha_se_comporta_como_sem_automatico():
    # Venda sem comanda (o servidor não tem `_list_q` para carimbar): etiqueta e
    # preço cobrado são o mesmo número, e o manual vale inteiro.
    payload = _payload(discount={"type": "percent", "value": 10, "reason": "cortesia"})
    assert _payload_line_discounts_q(payload) == 51 * 2


def test_linha_sem_desconto_nao_soma_nada():
    assert _payload_line_discounts_q(_payload(list_price_q=600)) == 0


def test_desconto_nunca_passa_do_preco_cobrado_da_linha():
    payload = _payload(
        list_price_q=600,
        discount={"type": "percent", "value": 100, "reason": "cortesia"},
    )
    # 100% da etiqueta = 6,00; menos o automático de 0,90 = 5,10, que é
    # exatamente o preço cobrado — nunca mais que isso.
    assert _payload_line_discounts_q(payload) == 510 * 2
