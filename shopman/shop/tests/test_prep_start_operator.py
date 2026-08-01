"""prep_start="operator": pagar não manda pra cozinha — o operador é que fisga.

Modelo escolhido pelo Pablo: para o canal web (cliente acompanhando de longe), o
pedido pago fica em "Aceito" e só vira "Em preparo" quando o operador dá "Iniciar
preparo" no gestor. Honesto com o cliente ("Em preparo" só quando alguém encosta)
e fiel à cozinha. Configurável por canal (``ChannelConfig.fulfillment.prep_start``):
iFood/PDV ficam em "auto".
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.lifecycle import dispatch
from shopman.shop.services import operator_orders

pytestmark = pytest.mark.django_db


@pytest.fixture
def web_operator_channel():
    from shopman.shop.models import Channel

    Channel.objects.create(
        ref="web-op",
        name="Loja Online (operador inicia)",
        config={
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5},
            "payment": {"method": ["pix"], "timing": "post_commit", "timeout_minutes": 10},
            "fulfillment": {"prep_start": "operator"},
        },
    )
    cache.clear()
    yield
    cache.clear()


def _paid_accepted_order(ref="WEB-OP-1", *, data_extra=None):
    from shopman.payman import PaymentService

    order = Order.objects.create(
        ref=ref,
        channel_ref="web-op",
        session_key=f"SESS-{ref}",
        status=Order.Status.ACCEPTED,
        total_q=2500,
        data={"payment": {"method": "pix"}, **(data_extra or {})},
    )
    intent = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method="pix")
    order.data["payment"]["intent_ref"] = intent.ref
    order.save(update_fields=["data"])
    PaymentService.authorize(intent.ref, gateway_id=f"gw-{ref}")
    PaymentService.capture(intent.ref)
    return order


@pytest.mark.usefixtures("web_operator_channel")
def test_paid_order_stays_accepted_until_operator_starts_prep():
    order = _paid_accepted_order()

    # Pagamento confirmado NÃO avança pra "preparando".
    dispatch(order, "on_paid")
    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED

    # E a bola é do operador: sem bloqueio de pagamento, o "Iniciar preparo" abre.
    assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.NONE
    assert operator_orders.next_status_for(order) == Order.Status.PREPARING


@pytest.mark.usefixtures("web_operator_channel")
def test_operator_start_prep_moves_to_preparing():
    order = _paid_accepted_order(ref="WEB-OP-2")
    dispatch(order, "on_paid")
    order.refresh_from_db()

    operator_orders.advance_order(order, actor="operator:test")

    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING


@pytest.mark.usefixtures("web_operator_channel")
def test_future_preorder_cannot_be_started_early():
    tomorrow = (timezone.localdate() + timedelta(days=3)).isoformat()
    order = _paid_accepted_order(ref="WEB-OP-PRE", data_extra={"delivery_date": tomorrow})

    # Encomenda para daqui a 3 dias: o preparo não abre antes do dia.
    assert operator_orders.advance_block(order) == operator_orders.AdvanceBlock.PREORDER_NOT_DUE
    with pytest.raises(ValueError):
        operator_orders.advance_order(order, actor="operator:test")
    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED
