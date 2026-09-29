"""O pedido de teste da homologação diz na TELA que é de teste.

Até 19/09/2026 a única pista que o operador tinha era o nome do item vir
"NÃO ENTREGAR" — defesa humana em horário de movimento. Estas travas exigem o
crachá e a frase nas três superfícies por onde o pedido passa: o card e o
detalhe do Gestor, e o card da Saída do KDS.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.projections.kds import _build_expedition_card
from shopman.backstage.projections.order_queue import (
    TEST_ORDER_LABEL,
    TEST_ORDER_NOTICE,
    _test_order_label,
    _test_order_notice,
)


def _order(*, is_test: bool) -> Order:
    return Order.objects.create(
        ref=f"IFOOD-TELA-{'T' if is_test else 'R'}",
        channel_ref="ifood",
        status=Order.Status.ACCEPTED,
        total_q=1500,
        data={
            "origin_channel": "ifood",
            "customer": {"name": "Cliente iFood"},
            "ifood": {"order_code": "abc", "is_test": is_test},
        },
    )


@pytest.mark.django_db
def test_pedido_de_teste_ganha_cracha_e_frase_inteira():
    order = _order(is_test=True)

    assert _test_order_label(order) == TEST_ORDER_LABEL
    assert _test_order_notice(order) == TEST_ORDER_NOTICE
    # A frase diz o que fazer E o que não fazer: sem isso, "pedido de teste"
    # deixa o operador escolher entre duas leituras no meio do movimento.
    assert "não produza nem entregue" in TEST_ORDER_NOTICE


@pytest.mark.django_db
def test_pedido_de_verdade_nao_ganha_cracha_nenhum():
    order = _order(is_test=False)

    assert _test_order_label(order) == ""
    assert _test_order_notice(order) == ""


@pytest.mark.django_db
def test_card_da_saida_marca_o_pedido_de_teste():
    """A Saída é o card do PEDIDO, não do ticket: o pedido de teste chega
    aqui mesmo sem ter passado pela cozinha, e é aqui que a sacola sairia."""
    order = _order(is_test=True)
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500
    )

    assert _build_expedition_card(order).test_order_label == TEST_ORDER_LABEL


@pytest.mark.django_db
def test_card_da_saida_de_pedido_real_fica_limpo():
    order = _order(is_test=False)
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1500, line_total_q=1500
    )

    assert _build_expedition_card(order).test_order_label == ""
