"""A gêmea do gate de pagamento no card da estação (prévia v4, K11).

O servidor recusa o Finalizar de um pedido que ainda não pode entrar em preparo
(pagamento digital não capturado, pedido sem confirmação). Antes a cozinha só
descobria depois do toque, num toast que chegava quando a janela de "Desfazer"
fechava. O card diz antes, e não diz nada quando o pagamento é na porta.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.backstage.projections.kds import build_kds_board
from shopman.shop.models import Channel, Shop


@pytest.fixture
def station(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(
        ref="web",
        name="Loja online",
        config={"payment": {"method": ["pix", "link"], "timing": "post_commit"}},
    )
    return KDSInstance.objects.create(ref="forno-twin", name="Forno", type="prep")


def _ticket(station, ref, *, status=Order.Status.ACCEPTED, payment=None, ticket_status="pending"):
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"sk-{ref}",
        status=status,
        total_q=2000,
        data={"fulfillment_type": "pickup", "payment": payment or {}},
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="SKU", name="Croissant", qty=4, unit_price_q=500, line_total_q=2000
    )
    KDSTicket.objects.create(
        session_key=order.session_key,
        kds_instance=station,
        status=ticket_status,
        items=[{"sku": "SKU", "name": "Croissant", "qty": 4}],
    )
    return order


def _card(station, ref):
    return next(card for card in build_kds_board(station.ref).tickets if card.order_ref == ref)


@pytest.mark.django_db
def test_unpaid_pix_ticket_says_so_before_the_tap(station):
    _ticket(station, "F15", payment={"method": "pix", "intent_ref": "int-nope"})

    card = _card(station, "F15")

    assert card.finish_block_label.endswith("não confirmado")
    assert "Finalizar libera quando o pagamento entrar" in card.finish_block_reason


@pytest.mark.django_db
def test_cash_on_delivery_ticket_has_no_block(station):
    _ticket(station, "C20", payment={"method": "cash", "collection": "on_delivery"})

    card = _card(station, "C20")

    assert card.finish_block_label == ""
    assert card.finish_block_reason == ""


@pytest.mark.django_db
def test_order_already_preparing_has_no_block(station):
    _ticket(
        station,
        "P30",
        status=Order.Status.PREPARING,
        payment={"method": "pix", "intent_ref": "int-nope"},
        ticket_status="in_progress",
    )

    assert _card(station, "P30").finish_block_label == ""


@pytest.mark.django_db
def test_the_card_blocks_exactly_when_the_server_refuses(station):
    """Card e servidor leem a mesma régua: o card nunca promete o que a API nega."""
    from shopman.shop.services import kds as kds_core

    blocked = _ticket(station, "B40", payment={"method": "pix", "intent_ref": "int-nope"}, ticket_status="in_progress")
    free = _ticket(station, "B41", payment={"method": "cash", "collection": "on_delivery"}, ticket_status="in_progress")

    assert _card(station, "B40").finish_block_label
    assert not _card(station, "B41").finish_block_label

    blocked_ticket = KDSTicket.objects.get(session_key=blocked.session_key)
    with pytest.raises(kds_core.TicketCompletionBlocked):
        kds_core.complete_ticket(blocked_ticket, actor="test")
    free_ticket = KDSTicket.objects.get(session_key=free.session_key)
    assert kds_core.complete_ticket(free_ticket, actor="test") is True
