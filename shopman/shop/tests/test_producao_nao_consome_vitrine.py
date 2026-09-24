"""A ficha não consome o pote da vitrine.

A coisa comprada que também se vende (manteiga, geleia, queijo) tem UM SKU e UM
estoque — o ledger indexa por SKU. Sem régua de posição, a receita do croissant
tirava a manteiga que estava exposta para o cliente levar. A régua: o consumo
sai das posições de produção e estoque; a vitrine (``Position.is_saleable``) só
com ``CRAFTSMAN["CONSUME_FROM_SALEABLE_POSITIONS"]``, e mesmo assim por último.

E o guardrail de disponibilidade (``InventoryAvailabilityBackend``) conta pela
mesma régua — senão ele aprovaria o que o consumo depois não acha.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.craftsman.contrib.stockman.handlers import _consume_materials
from shopman.craftsman.models import Recipe, WorkOrder, WorkOrderItem
from shopman.craftsman.protocols.inventory import MaterialNeed
from shopman.stockman import stock
from shopman.stockman.models import Position, Quant
from shopman.stockman.models.enums import PositionKind

from shopman.shop.adapters.inventory import InventoryAvailabilityBackend

pytestmark = pytest.mark.django_db

MANTEIGA = "MANTEIGA-SAL-PRESIDENT-200"


@pytest.fixture
def posicoes(db):
    deposito = Position.objects.create(ref="deposito", name="Depósito", kind=PositionKind.PHYSICAL, is_saleable=False)
    vitrine = Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)
    return deposito, vitrine


def _ordem_que_consome(quantidade: str) -> WorkOrder:
    recipe = Recipe.objects.create(ref="croissant", name="Croissant", output_sku="CRO", batch_size=1)
    work_order = WorkOrder.objects.create(recipe=recipe, output_sku="CRO", quantity=10)
    WorkOrderItem.objects.create(
        work_order=work_order, kind=WorkOrderItem.Kind.CONSUMPTION, item_ref=MANTEIGA,
        quantity=Decimal(quantidade), unit="un", recorded_at=timezone.now(),
    )
    return work_order


def _saldo(position) -> Decimal:
    return sum((q.quantity for q in Quant.objects.filter(sku=MANTEIGA, position=position)), Decimal("0"))


def test_pote_na_vitrine_nao_e_consumido_pela_receita(posicoes):
    deposito, vitrine = posicoes
    stock.receive(quantity=Decimal("3"), sku=MANTEIGA, position=deposito, reason="compra")
    stock.receive(quantity=Decimal("4"), sku=MANTEIGA, position=vitrine, reason="exposição")

    shortfalls = _consume_materials(_ordem_que_consome("5"), fail_closed=False)

    # Tirou os 3 do depósito e PAROU: faltaram 2, e a vitrine ficou intacta.
    assert _saldo(deposito) == Decimal("0")
    assert _saldo(vitrine) == Decimal("4")
    assert [(s["sku"], Decimal(str(s["short"]))) for s in shortfalls] == [(MANTEIGA, Decimal("2"))]


@override_settings(CRAFTSMAN_CONSUME_FROM_SALEABLE_POSITIONS=True)
def test_com_a_chave_ligada_a_vitrine_entra_por_ultimo(posicoes):
    deposito, vitrine = posicoes
    stock.receive(quantity=Decimal("3"), sku=MANTEIGA, position=deposito, reason="compra")
    stock.receive(quantity=Decimal("4"), sku=MANTEIGA, position=vitrine, reason="exposição")

    _consume_materials(_ordem_que_consome("5"), fail_closed=True)

    assert _saldo(deposito) == Decimal("0")
    assert _saldo(vitrine) == Decimal("2")


def test_o_guardrail_conta_pela_mesma_regua(posicoes):
    deposito, vitrine = posicoes
    stock.receive(quantity=Decimal("3"), sku=MANTEIGA, position=deposito, reason="compra")
    stock.receive(quantity=Decimal("4"), sku=MANTEIGA, position=vitrine, reason="exposição")

    result = InventoryAvailabilityBackend().available([MaterialNeed(sku=MANTEIGA, quantity=Decimal("5"))])

    assert result.all_available is False
    assert result.materials[0].available == Decimal("3")
