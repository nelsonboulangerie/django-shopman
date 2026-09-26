"""O "Marcar pronto" do Gestor não deixa ticket pendurado no KDS.

O pedido avançava a READY por ``operator_orders.advance_order`` e os tickets
abertos ficavam na grade das estações — e na Saída, como "em preparo" — depois
de a sacola ter saído. Quem avança o pedido afirma que a cozinha terminou: os
tickets abertos fecham junto, com o ator e a porta registrados.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from shopman.orderman.models import Order

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.services import kds as kds_core
from shopman.shop.services import operator_orders

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel():
    from shopman.shop.models import Channel

    Channel.objects.create(
        ref="web-orf",
        name="Loja (tickets órfãos)",
        config={
            "confirmation": {"mode": "auto_confirm", "timeout_minutes": 5},
            "payment": {"method": ["pix"], "timing": "post_commit", "timeout_minutes": 10},
        },
    )
    cache.clear()
    yield
    cache.clear()


def _paid_preparing_order(ref: str) -> Order:
    from shopman.payman import PaymentService

    order = Order.objects.create(
        ref=ref,
        channel_ref="web-orf",
        session_key=f"SESS-{ref}",
        status=Order.Status.ACCEPTED,
        total_q=2500,
        data={"payment": {"method": "pix"}, "fulfillment_type": "pickup"},
    )
    intent = PaymentService.create_intent(order_ref=order.ref, amount_q=order.total_q, method="pix")
    order.data["payment"]["intent_ref"] = intent.ref
    order.save(update_fields=["data"])
    PaymentService.authorize(intent.ref, gateway_id=f"gw-{ref}")
    PaymentService.capture(intent.ref)
    order.transition_status(Order.Status.PREPARING, actor="test")
    return order


def _ticket(order: Order, station_ref: str, *, status: str = "pending") -> KDSTicket:
    station, _ = KDSInstance.objects.get_or_create(
        ref=station_ref, defaults={"name": station_ref.title(), "type": "prep"}
    )
    return KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=station,
        status=status,
        items=[{"sku": "X", "name": "Item", "qty": 1, "line_id": f"{station_ref}-1"}],
    )


@pytest.mark.usefixtures("channel")
def test_marcar_pronto_no_gestor_conclui_os_tickets_abertos():
    order = _paid_preparing_order("ORF-1")
    aberto = _ticket(order, "lanches")
    em_preparo = _ticket(order, "cafes", status="in_progress")

    assert operator_orders.advance_order(order, actor="gestor:ana") == Order.Status.READY

    for ticket in (aberto, em_preparo):
        ticket.refresh_from_db()
        assert ticket.status == "done"
        assert ticket.completed_at is not None
        assert ticket.completed_by == "gestor:ana"
        assert ticket.completed_via == KDSTicket.COMPLETED_VIA_ORDER_ADVANCED


@pytest.mark.usefixtures("channel")
def test_ticket_ja_concluido_e_cancelado_ficam_como_estavam():
    order = _paid_preparing_order("ORF-2")
    pronto = _ticket(order, "lanches")
    kds_core.complete_ticket(pronto, actor="kds:joao")
    order.refresh_from_db()
    cancelado = _ticket(order, "cafes", status="cancelled")
    aberto = _ticket(order, "encomendas")

    operator_orders.advance_order(order, actor="gestor:ana")

    pronto.refresh_from_db()
    cancelado.refresh_from_db()
    aberto.refresh_from_db()
    assert (pronto.status, pronto.completed_by, pronto.completed_via) == ("done", "kds:joao", "station")
    assert cancelado.status == "cancelled"
    assert aberto.completed_via == KDSTicket.COMPLETED_VIA_ORDER_ADVANCED


def test_close_open_tickets_sem_ticket_aberto_devolve_zero(db):
    order = Order.objects.create(
        ref="ORF-3", channel_ref="web", session_key="SESS-ORF-3", status=Order.Status.READY, total_q=100,
    )
    assert kds_core.close_open_tickets(order, actor="gestor:ana") == 0


def test_a_porta_da_baixa_fica_no_ticket_e_o_desfazer_a_apaga(db):
    order = Order.objects.create(
        ref="ORF-4", channel_ref="web", session_key="SESS-ORF-4", status=Order.Status.PREPARING, total_q=100,
    )
    first = _ticket(order, "lanches")
    _ticket(order, "cafes")

    kds_core.complete_ticket(first, actor="pdv:carla", via=KDSTicket.COMPLETED_VIA_POS)
    first.refresh_from_db()
    assert (first.completed_by, first.completed_via) == ("pdv:carla", "pos")

    kds_core.reopen_ticket(first, actor="kds:joao")
    first.refresh_from_db()
    assert (first.status, first.completed_by, first.completed_via) == ("in_progress", "", "")
