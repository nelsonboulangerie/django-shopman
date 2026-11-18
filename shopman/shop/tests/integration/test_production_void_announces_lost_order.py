"""Lote cancelado com encomenda paga vinculada vira fato do pedido (#2547).

Antes o cancelamento soltava a reserva do pedido aceito com "Produção cancelada"
e só a sacola aberta ficava sabendo. O cliente tinha lido "Pedido garantido para
amanhã", e o Gestor não mostrava nada. Agora o pedido ganha o evento na linha do
tempo e o Gestor, o aviso no sino com o pedido nomeado, sem ninguém abrir painel.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.service import CraftService as craft
from shopman.orderman.models import Order, OrderEvent
from shopman.stockman import stock
from shopman.stockman.models import Hold, HoldStatus

from shopman.backstage.models import OperatorAlert

pytestmark = pytest.mark.django_db


def _hold(product, qty, *, reference, target_date):
    hold_id = stock.hold(quantity=Decimal(qty), product=product, target_date=target_date, reference=reference)
    stock.confirm(hold_id)
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


def _encomenda(ref, *, status="accepted", day):
    return Order.objects.create(
        ref=ref, channel_ref="web", status=status, total_q=5000, data={"delivery_date": day.isoformat()},
    )


def test_cancelar_o_unico_lote_avisa_o_gestor_e_marca_o_pedido(recipe, croissant, position_loja, tomorrow):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    order = _encomenda("ENC-PAGA", day=tomorrow)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    hold = _hold(croissant, "4", reference="order:ENC-PAGA", target_date=tomorrow)

    craft.void(wo, reason="Cancelada")

    hold.refresh_from_db()
    assert hold.status == HoldStatus.RELEASED

    alert = OperatorAlert.objects.get(type="order_promise_lost", order_ref="ENC-PAGA")
    assert alert.audience == "orders"
    assert "Pedido ENC-PAGA" in alert.message
    assert "4 un." in alert.message
    assert "Avise o cliente" in alert.message

    event = OrderEvent.objects.get(order=order, type="production_hold_lost")
    assert event.payload["sku"] == croissant.sku
    assert event.payload["qty"] == "4"
    assert event.payload["work_order_ref"] == wo.ref


def test_pedido_coberto_pela_outra_fornada_nao_e_avisado(recipe, croissant, position_loja, tomorrow):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    _encomenda("ENC-COBERTA", day=tomorrow)
    wo_a = craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    _hold(croissant, "8", reference="order:ENC-COBERTA", target_date=tomorrow)

    craft.void(wo_a, reason="Cancelada")

    assert not OperatorAlert.objects.filter(type="order_promise_lost").exists()


def test_pedido_que_ja_acabou_nao_e_avisado(recipe, croissant, position_loja, tomorrow):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    _encomenda("ENC-CANCELADA", status="cancelled", day=tomorrow)
    wo = craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    _hold(croissant, "4", reference="order:ENC-CANCELADA", target_date=tomorrow)

    craft.void(wo, reason="Cancelada")

    assert not OperatorAlert.objects.filter(type="order_promise_lost").exists()


def test_o_mesmo_cancelamento_nao_avisa_duas_vezes(recipe, croissant, position_loja, tomorrow):
    from shopman.shop.services import production_promise

    _encomenda("ENC-UMA-VEZ", day=tomorrow)
    for _ in range(2):
        production_promise.announce_lost_holds(
            {"ENC-UMA-VEZ": Decimal("4")}, sku=croissant.sku, date=tomorrow,
        )
    assert OperatorAlert.objects.filter(type="order_promise_lost", order_ref="ENC-UMA-VEZ").count() == 1
