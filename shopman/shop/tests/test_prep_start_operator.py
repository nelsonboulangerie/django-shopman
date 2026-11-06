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


# ── A verdade é da Cozinha, o Gestor é um atalho (dono, 06/11/2026) ─────────
#
# "Ao lançar um pedido, na hora que ele é aceito, já vai para a Cozinha, e fica
# esperando o comando do operador do posto para iniciar o preparo." O ticket
# nasce no aceite; o "Iniciar preparo" do posto põe o pedido em preparo; o do
# Gestor chama o MESMO ato e nunca cria ticket.


@pytest.fixture
def estacao():
    from shopman.backstage.models import KDSInstance

    return KDSInstance.objects.create(ref="encomendas", name="Encomendas", type="picking")


def _paid_accepted_order_with_items(ref):
    from shopman.orderman.models import OrderItem

    order = _paid_accepted_order(ref=ref)
    for line_id, sku in (("1", "PAO"), ("2", "BOLO")):
        OrderItem.objects.create(
            order=order, line_id=line_id, sku=sku, name=sku,
            qty="1", unit_price_q=1000, line_total_q=1000,
        )
    return order


def _tickets(order):
    from shopman.backstage.models import KDSTicket

    return list(KDSTicket.objects.filter(session_key=order.session_key).order_by("pk"))


def _preparing_events(order):
    return [
        e for e in order.events.filter(type="status_changed")
        if (e.payload or {}).get("new_status") == Order.Status.PREPARING
    ]


@pytest.mark.usefixtures("web_operator_channel")
def test_aceito_e_pago_ja_esta_na_cozinha_esperando_iniciar_preparo(estacao):
    order = _paid_accepted_order_with_items("WEB-OP-K1")

    dispatch(order, "on_paid")
    order.refresh_from_db()

    tickets = _tickets(order)
    assert len(tickets) == 1
    assert tickets[0].status == "pending"
    # O pedido espera o posto: o cliente remoto ainda não lê "Em preparo".
    assert order.status == Order.Status.ACCEPTED
    assert operator_orders.next_status_for(order) == Order.Status.PREPARING


@pytest.mark.usefixtures("web_operator_channel")
def test_iniciar_preparo_na_cozinha_poe_o_pedido_em_preparo_sem_ticket_novo(estacao):
    from shopman.shop.services import kds

    order = _paid_accepted_order_with_items("WEB-OP-K2")
    dispatch(order, "on_paid")
    (ticket,) = _tickets(order)

    assert kds.start_ticket(ticket, actor="cozinheira") is True

    order.refresh_from_db()
    ticket.refresh_from_db()
    assert order.status == Order.Status.PREPARING
    assert ticket.status == "in_progress"
    assert ticket.started_by == "cozinheira"
    assert len(_tickets(order)) == 1
    # Tocar de novo (outro tablet, replay) não muda nada nem repete evento.
    assert kds.start_ticket(ticket, actor="outra") is True
    ticket.refresh_from_db()
    assert ticket.started_by == "cozinheira"
    assert len(_preparing_events(order)) == 1


@pytest.mark.usefixtures("web_operator_channel")
def test_iniciar_preparo_do_gestor_e_o_mesmo_ato_da_cozinha(estacao):
    from shopman.shop.services import kds

    order = _paid_accepted_order_with_items("WEB-OP-K3")
    dispatch(order, "on_paid")
    (ticket,) = _tickets(order)

    operator_orders.advance_order(order, actor="gerente", target_status=Order.Status.PREPARING)

    order.refresh_from_db()
    ticket.refresh_from_db()
    assert order.status == Order.Status.PREPARING
    # O ticket que esperava no posto é o que entrou em preparo, com quem tocou.
    assert ticket.status == "in_progress"
    assert ticket.started_by == "gerente"
    assert (order.data.get("kds_started") or {}).get(str(ticket.pk), {}).get("by") == "gerente"
    assert len(_tickets(order)) == 1
    assert len(_preparing_events(order)) == 1

    # O posto toca depois: o card já está em preparo, nada duplica.
    assert kds.start_ticket(ticket, actor="cozinheira") is True
    ticket.refresh_from_db()
    assert ticket.started_by == "gerente"
    # O Gestor toca de novo (duplo clique, SSE atrasado): a etapa já passou.
    with pytest.raises(operator_orders.OrderStateConflict):
        operator_orders.advance_order(order, actor="gerente", target_status=Order.Status.PREPARING)
    assert len(_tickets(order)) == 1
    assert len(_preparing_events(order)) == 1


@pytest.mark.usefixtures("web_operator_channel")
def test_gestor_depois_da_cozinha_nao_oferece_iniciar_de_novo(estacao):
    from shopman.shop.services import kds

    order = _paid_accepted_order_with_items("WEB-OP-K4")
    dispatch(order, "on_paid")
    (ticket,) = _tickets(order)
    kds.start_ticket(ticket, actor="cozinheira")
    order.refresh_from_db()

    # Os dois lados dizem o mesmo: em preparo, e o próximo verbo é o Pronto.
    assert order.status == Order.Status.PREPARING
    assert operator_orders.next_status_for(order) == Order.Status.READY
    assert kds.start_order_tickets(order, actor="gerente") == 0
