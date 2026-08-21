"""Desconto percentual sobre quantidade DECIMAL — o dia da balança.

`_qty_decimal` substituiu `int(item.get("qty", 1)) or 1`, que errava nos dois
sentidos: meio quilo virava `int(0.5) == 0`, o `or 1` o promovia a 1 e o cliente
pagava o dobro; um quilo e meio virava 1 e a loja perdia a metade.

Hoje nada é vendido por peso, então o defeito era inócuo — mas inócuo por
acidente do catálogo, não por desenho. Estes testes chamam a conta direto,
porque é ela que tem de estar certa antes de existir um produto a quilo.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from shopman.shop.modifiers import _qty_decimal


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        (1, "1"),
        ("2", "2"),
        (Decimal("0.5"), "0.5"),      # meio quilo: era 0 → promovido a 1 (cobrava o dobro)
        ("1.5", "1.5"),               # um quilo e meio: era 1 (a loja perdia meio quilo)
        (Decimal("0.250"), "0.250"),  # 250 g
        (2.5, "2.5"),                 # float também entra pelo carrinho
    ],
)
def test_quantidade_decimal_atravessa_inteira(bruto, esperado):
    assert _qty_decimal({"qty": bruto}) == Decimal(esperado)


@pytest.mark.parametrize("bruto", [0, "0", Decimal("0"), None, "", "abacaxi", -3])
def test_quantidade_ausente_ou_ilegivel_vale_UMA_unidade(bruto):
    """Linha sem quantidade é linha de uma unidade — o que o resto do carrinho assume.

    Vale para o zero, para o negativo e para o ilegível: nenhum deles pode virar
    linha grátis nem linha de crédito.
    """
    assert _qty_decimal({"qty": bruto}) == Decimal("1")


def test_chave_ausente_vale_uma_unidade():
    assert _qty_decimal({}) == Decimal("1")


def test_o_total_da_linha_usa_arredondamento_da_casa():
    """`monetary_mult` é ROUND_HALF_UP, como o resto do sistema.

    2,5 × R$ 3,33 = R$ 8,325 → R$ 8,33, e não R$ 8,32. Meio centavo para cima é
    a regra do projeto; o que não pode é a quantidade sumir antes da conta.
    """
    from shopman.utils.monetary import monetary_mult

    assert monetary_mult(_qty_decimal({"qty": "2.5"}), 333) == 833
