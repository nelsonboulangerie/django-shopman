"""Cancelar UMA fornada solta só as reservas que ela deixou sem lastro.

Antes, ``on_production_voided`` soltava TODA reserva ativa do SKU na data
(filtro só ``sku`` + ``target_date``). Como toda reserva sem data recebe hoje,
isso pegava a reserva de pedido pago sobre a VITRINE e as cobertas pelas
outras fornadas do dia: a unidade voltava à venda e era vendida de novo, e o
``stock.fulfill`` do pedido falhava depois.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.service import CraftService as craft
from shopman.stockman import stock
from shopman.stockman.models import Hold, HoldStatus

pytestmark = pytest.mark.django_db


def _hold(product, qty, *, reference, target_date=None, confirm=False):
    hold_id = stock.hold(
        quantity=Decimal(qty),
        product=product,
        target_date=target_date,
        reference=reference,
    )
    if confirm:
        stock.confirm(hold_id)
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


def _status(hold):
    hold.refresh_from_db()
    return hold.status


def test_void_does_not_touch_a_paid_order_reserved_on_the_shelf(
    recipe, croissant, position_loja, today,
):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    stock.receive(quantity=Decimal("3"), sku=croissant.sku, position=position_loja, reason="vitrine")
    paid = _hold(croissant, "2", reference="order:PAGO-1", confirm=True)
    assert paid.quant.target_date is None  # reserva sobre o físico, com target_date=hoje

    wo = craft.plan(recipe, quantity=Decimal("10"), date=today)
    craft.void(wo, reason="Cancelada")

    assert _status(paid) == HoldStatus.CONFIRMED


def test_void_keeps_holds_still_covered_by_the_other_batch(
    recipe, croissant, position_loja, tomorrow,
):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    wo_a = craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)

    order = _hold(croissant, "8", reference="order:ENC-1", target_date=tomorrow, confirm=True)
    cart = _hold(croissant, "5", reference="sessao-da-sacola", target_date=tomorrow)
    assert order.quant_id == cart.quant_id  # quant planejado compartilhado (20)

    craft.void(wo_a, reason="Cancelada")

    # Sobram 10 planejados para 13 reservados: sai a sacola (3 de excesso),
    # e a encomenda, que cabe na outra fornada, fica.
    assert _status(cart) == HoldStatus.RELEASED
    assert _status(order) == HoldStatus.CONFIRMED


def test_void_of_the_only_batch_releases_what_lost_its_backing(
    recipe, croissant, position_loja, tomorrow,
):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    wo = craft.plan(recipe, quantity=Decimal("10"), date=tomorrow)
    order = _hold(croissant, "4", reference="order:ENC-2", target_date=tomorrow, confirm=True)
    cart = _hold(croissant, "3", reference="sessao-2", target_date=tomorrow)

    craft.void(wo, reason="Cancelada")

    assert _status(cart) == HoldStatus.RELEASED
    assert _status(order) == HoldStatus.RELEASED
    order.refresh_from_db()
    assert order.metadata.get("release_reason") == "Produção cancelada"
