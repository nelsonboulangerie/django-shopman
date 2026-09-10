"""A gêmea na tela do gate de pagamento, no board de expedição.

Régua de servidor mais apertada do que a da tela inventa bloqueio invisível: o
operador toca em "Despachar", leva recusa seca e o cliente está esperando. O
card da expedição precisa dizer ANTES do toque, com o mesmo rótulo curto e o
mesmo motivo que o Gestor mostra — e não pode dizer nada quando o pagamento é
na porta, que é venda legítima.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import KDSInstance
from shopman.backstage.projections.kds import build_kds_board
from shopman.shop.models import Channel, Shop


@pytest.fixture
def expedition_board(db):
    Shop.objects.create(name="Loja")
    Channel.objects.create(
        ref="web",
        name="Loja online",
        config={"payment": {"method": ["pix", "link"], "timing": "post_commit"}},
    )
    return KDSInstance.objects.create(ref="exp-twin", name="Expedição", type="expedition")


def _ready_order(ref, payment):
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"sk-{ref}",
        status=Order.Status.READY,
        total_q=2000,
        data={"fulfillment_type": "delivery", "payment": payment},
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="SKU", name="Produto", qty=1, unit_price_q=2000, line_total_q=2000
    )
    return order


def _card(board, ref):
    return next(card for card in board.tickets if card.order_ref == ref)


@pytest.mark.django_db
def test_unpaid_link_card_shows_the_reason_instead_of_the_dispatch_button(expedition_board):
    _ready_order("EXP-LINK", {"method": "link", "intent_ref": "int-nope"})

    card = _card(build_kds_board(expedition_board.ref), "EXP-LINK")

    assert card.advance_block_label == "Aguardando pagamento…"
    assert "Pagamento ainda não foi confirmado" in card.advance_block_reason


@pytest.mark.django_db
def test_cash_on_delivery_card_keeps_the_dispatch_button(expedition_board):
    _ready_order("EXP-COD", {"method": "cash", "collection": "on_delivery"})

    card = _card(build_kds_board(expedition_board.ref), "EXP-COD")

    assert card.advance_block_label == ""
    assert card.advance_block_reason == ""


@pytest.mark.django_db
def test_the_card_says_exactly_what_the_server_would_refuse(expedition_board):
    """A tela e o servidor leem a MESMA régua — o card nunca promete o que a API nega."""
    from shopman.shop.services import kds as kds_core

    for ref, payment in (
        ("EXP-SAME-LINK", {"method": "link", "intent_ref": "int-nope"}),
        ("EXP-SAME-COD", {"method": "cash", "collection": "on_delivery"}),
    ):
        order = _ready_order(ref, payment)
        card = _card(build_kds_board(expedition_board.ref), ref)
        assert card.advance_block_reason == kds_core.expedition_block_reason(
            order, action="dispatch"
        )
