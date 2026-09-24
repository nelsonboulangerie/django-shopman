"""Fornada fechada direto do planejado não debita o forno da OUTRA fornada.

A fornada que vai de PLANNED a FINISHED (a avulsa do quiosque, ou qualquer uma
fechada sem "Iniciar") ganha um início IMPLÍCITO no Craftsman, que não emite o
sinal ``started``: a contribuição dela continua no quant planejado sem lote.
O ``realize`` procurava primeiro o quant ``started`` da data — que era o da
outra fornada, ainda no forno — e debitava dele. A contribuição da avulsa
ficava no planejado e, quando a outra fechava, sobrava como "estoque
fantasma" prometível até o fim do dia.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.service import CraftService as craft
from shopman.stockman import stock
from shopman.stockman.models import Quant

pytestmark = pytest.mark.django_db


def _production_supply(sku, day) -> dict[str, Decimal]:
    return {
        q.batch or "planned": q.quantity
        for q in Quant.objects.filter(sku=sku, target_date=day)
    }


def test_quick_batch_closed_while_another_is_in_the_oven_leaves_no_phantom(
    recipe, ingredient, croissant, position_producao, position_loja, today,
):
    import shopman.craftsman.contrib.stockman.handlers  # noqa: F401

    stock.receive(quantity=Decimal("100"), sku=ingredient.sku, position=position_producao, reason="insumo")

    in_oven = craft.plan(recipe, quantity=Decimal("10"), date=today)
    craft.start(in_oven, quantity=Decimal("10"), actor="test")

    quick = craft.plan(recipe, quantity=Decimal("5"), date=today)
    craft.finish(quick, finished=Decimal("5"), actor="test")

    # A avulsa saiu do planejado; o forno da outra segue com 10.
    supply = _production_supply(croissant.sku, today)
    assert supply.get("planned", Decimal("0")) == Decimal("0")
    assert supply.get("started") == Decimal("10")

    craft.finish(in_oven, finished=Decimal("10"), actor="test")

    # Nada de produção prometível sobrando: tudo virou vitrine.
    assert sum(_production_supply(croissant.sku, today).values(), Decimal("0")) == Decimal("0")
    assert stock.available(croissant, position=position_loja) == Decimal("15")
