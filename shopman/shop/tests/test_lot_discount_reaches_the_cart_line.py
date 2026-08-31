"""O desconto de lote (ADR-017 §7) estava desligado na loja, em silêncio.

``cart.add_item`` grava ``meta["batch_ref"]`` na linha a partir do hold que a
reserva ancorou, e esse campo é a ÚNICA fonte do ``LotDiscountModifier``. Quem
o produzia — ``lot_pricing.batch_ref_for_hold`` — filtrava por ``pk=hold_id``,
mas ``hold_id`` nunca é um pk: o formato do Stockman é ``"hold:<pk>"``. A query
levantava ``ValueError`` em TODA chamada, o ``except`` engolia num DEBUG, e a
função devolvia "" para sempre.

Nenhuma tela tinha como perceber: o modificador não achava linha nenhuma para
aplicar, então não havia desconto errado a conferir — havia desconto ausente.
Pão do lote que vence hoje saía pelo preço cheio.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from shopman.offerman.models import AvailabilityPolicy, Product
from shopman.stockman.models import Batch, Hold, HoldStatus, Position, PositionKind, Quant

from shopman.shop.services import lot_pricing

pytestmark = pytest.mark.django_db

SKU = "PAO-LOTE"


@pytest.fixture
def channel(db):
    from shopman.shop.models import Channel

    ch, _ = Channel.objects.get_or_create(
        ref="web", defaults={"name": "Loja online", "is_active": True},
    )
    return ch


@pytest.fixture
def lote(db):
    Product.objects.create(
        sku=SKU,
        name="Pão do lote",
        base_price_q=1000,
        is_published=True,
        is_sellable=True,
        availability_policy=AvailabilityPolicy.STOCK_ONLY,
    )
    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    Batch.objects.create(
        sku=SKU,
        ref="L-VENCE-HOJE",
        expiry_date=date.today(),
        nonconformity_percent=30,
    )
    quant = Quant.objects.create(
        sku=SKU, position=position, batch="L-VENCE-HOJE", _quantity=Decimal("5"),
    )
    return Hold.objects.create(
        sku=SKU,
        quant=quant,
        quantity=Decimal("1"),
        target_date=date.today(),
        status=HoldStatus.PENDING,
        expires_at=None,
        metadata={"reference": "SESS-X"},
    )


def test_the_lot_of_the_hold_is_found_through_the_stockman_id_format(lote):
    """``hold:<pk>`` é o formato que o Stockman devolve — e o único que chega aqui."""
    assert lot_pricing.batch_ref_for_hold(lote.hold_id) == "L-VENCE-HOJE"


def test_a_floating_hold_has_no_lot_and_says_so_quietly(db):
    """Reserva de demanda (``quant=None``) não tem lote — e não pode ter."""
    Product.objects.create(
        sku="CAFE-X", name="Café", base_price_q=600,
        is_published=True, is_sellable=True,
        availability_policy=AvailabilityPolicy.DEMAND_OK,
    )
    hold = Hold.objects.create(
        sku="CAFE-X",
        quant=None,
        quantity=Decimal("1"),
        target_date=date.today(),
        status=HoldStatus.PENDING,
        metadata={"reference": "SESS-Y"},
    )

    assert lot_pricing.batch_ref_for_hold(hold.hold_id) == ""


def test_an_unreadable_hold_id_shouts_instead_of_disabling_the_discount():
    """Falha de programação não pode virar feature desligada em silêncio.

    O ``except`` fica (preço não derruba a sacola), mas em WARNING: era o DEBUG
    que deixou um modificador inteiro morto sem ninguém notar.
    """
    from unittest.mock import patch

    with patch.object(lot_pricing.logger, "warning") as warned:
        assert lot_pricing.batch_ref_for_hold("isto-nao-e-um-hold") == ""

    assert warned.called
    assert "hold_id_unreadable" in warned.call_args[0][0]


def test_the_frozen_lot_discount_reaches_the_cart_line(channel, lote):
    """A ponta a ponta: reservar o lote põe ``batch_ref`` na linha da sacola.

    Sem ele o ``LotDiscountModifier`` não tem o que aplicar, e o desconto de
    validade some sem deixar rastro.
    """
    from shopman.shop.services import cart as cart_service

    _session, session_key = cart_service.add_item(
        session_key=None,
        channel_ref="web",
        origin_channel="web",
        sku=SKU,
        qty=1,
        unit_price_q=1000,
    )

    from shopman.orderman.models import Session

    session = Session.objects.get(session_key=session_key)
    line = next(item for item in (session.items or []) if item.get("sku") == SKU)

    assert (line.get("meta") or {}).get("batch_ref") == "L-VENCE-HOJE"
