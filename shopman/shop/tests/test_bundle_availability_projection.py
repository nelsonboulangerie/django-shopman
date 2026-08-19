"""A vitrine tem de saber quantos bundles dá para montar.

O stockman conta quant por SKU, e bundle não tem quant — então a projection
lia **zero** para todo bundle. O combo não parecia quebrado porque a política
`demand_ok` deixa pedir sem estoque, e isso mascarava o número.

Pacote de pão não pode se apoiar nisso: ele é limitado pelo pão que o compõe, e
pão acaba todo dia. Vender pacote sem pão é prometer o que não existe.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.offerman.models import Product, ProductComponent
from shopman.stockman.models import Position, Quant
from shopman.stockman.services.movements import StockMovements

from shopman.shop.projections import catalog_context as cc


@pytest.fixture
def pacote(db):
    vitrine = Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)
    unidade = Product.objects.create(
        sku="PHO", name="Pão para Hot Dog", base_price_q=700, is_sellable=True
    )
    # Estoque entra pelo ledger; `_quantity` é cache de Σ(moves) e o model
    # recusa escrita direta, com razão.
    StockMovements.receive(Decimal("48"), sku="PHO", position=vitrine)
    pack = Product.objects.create(
        sku="PHO4", name="Pão para Hot Dog (pc. 4un.)", base_price_q=2800, is_sellable=True
    )
    ProductComponent.objects.create(parent=pack, component=unidade, qty=Decimal("4"))
    return pack


@pytest.mark.django_db
def test_o_pacote_vale_o_que_o_pao_permite(pacote):
    bruto = cc.availability_for_sku("PHO4", channel_ref="web")
    visao = cc.storefront_availability(bruto, is_sellable=True)

    # 48 pães ÷ 4 por pacote = 12 pacotes. Sem a expansão, seria zero.
    assert visao["available_qty"] == 12
    assert visao["can_order"] is True


@pytest.mark.django_db
def test_sem_pao_nao_ha_pacote(pacote):
    StockMovements.issue(Decimal("48"), quant=Quant.objects.get(sku="PHO"))

    visao = cc.storefront_availability(
        cc.availability_for_sku("PHO4", channel_ref="web"), is_sellable=True
    )

    assert visao["available_qty"] == 0
    assert visao["can_order"] is False


@pytest.mark.django_db
def test_sobra_de_pao_nao_vira_pacote_quebrado(pacote):
    # 10 pães dão 2 pacotes de 4, não 2,5 — a divisão é inteira de propósito.
    StockMovements.issue(Decimal("38"), quant=Quant.objects.get(sku="PHO"))

    visao = cc.storefront_availability(
        cc.availability_for_sku("PHO4", channel_ref="web"), is_sellable=True
    )

    assert visao["available_qty"] == 2


@pytest.mark.django_db
def test_produto_simples_segue_igual(pacote):
    visao = cc.storefront_availability(
        cc.availability_for_sku("PHO", channel_ref="web"), is_sellable=True
    )

    assert visao["available_qty"] == Decimal("48")
