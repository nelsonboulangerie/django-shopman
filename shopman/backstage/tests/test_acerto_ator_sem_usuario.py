"""Troco e acerto da entrega quando o ator não é um usuário (``system:*``, KDS).

O fallback do operador do lançamento no livro-caixa é quem abriu o turno
(``Shift.opened_by``). O código pedia ``cash_shift.operator``, campo que o
turno não tem: todo despacho com troco e todo acerto feito por um ator sem
usuário estourava ``AttributeError`` — o livro ficava sem o lançamento e a
tela sem resposta.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from shopman.cashman import Entry
from shopman.cashman import services as cash
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Shop
from shopman.shop.services import operator_orders

pytestmark = pytest.mark.django_db


def _order(ref: str) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status="ready",
        total_q=3000,
        data={
            "customer": {"name": "Ana"},
            "fulfillment_type": "delivery",
            "payment": {"method": "cash", "collection": "on_delivery", "amount_q": 3000, "change_for_q": 5000},
        },
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=3000, line_total_q=3000)
    return order


def test_troco_despachado_por_ator_sem_usuario_vai_para_quem_abriu_o_turno():
    Shop.objects.create(name="Loja")
    abriu = User.objects.create_user("marina", password="pw", is_staff=True)
    shift = cash.open_shift(operator=abriu, float_q=10000)
    order = _order("DLV-SYS-1")

    operator_orders.advance_order(order, actor="system:kds", change_out_q=2000, cash_shift=shift)

    entry = Entry.objects.get(order_ref="DLV-SYS-1", kind="courier_out")
    assert entry.operator == abriu
    assert entry.amount_q == -2000
