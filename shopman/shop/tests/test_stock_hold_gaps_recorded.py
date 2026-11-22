"""O pedido guarda o que o estoque não conseguiu reservar (#2721, item 2).

O aviso ``stock_hold_gap`` saía e o pedido ficava sem rastro: a "Promessa em
risco" lê só ``hold_ids``, e o item que nunca reservou não tinha entrada ali.
Agora ``Order.data["hold_gaps"]`` guarda o componente e quanto faltou, escrito
por quem escreve ``hold_ids`` (a reserva do pedido e a reconciliação da edição),
e some quando nada falta.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from shopman.offerman.models import Product
from shopman.stockman import PositionKind
from shopman.stockman.models import Position, Quant

from shopman.shop.models import Channel
from shopman.shop.services import stock as stock_service

pytestmark = pytest.mark.django_db

SKU = "GAP-BAGUETE"
EXTERNAL = {"payment": {"method": "cash", "timing": "external"}, "stock": {"check_on_commit": False}}


@pytest.fixture
def vitrine():
    Channel.objects.create(ref="pdv", name="PDV", is_active=True, config=EXTERNAL)
    Product.objects.create(sku=SKU, name="Baguete", base_price_q=1000, is_published=True, is_sellable=True)
    position, _ = Position.objects.get_or_create(
        ref="vitrine", defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return position


def _order(qty: int, *, ref: str = "GAP-1"):
    return SimpleNamespace(
        ref=ref,
        channel_ref="pdv",
        session_key=None,
        snapshot={"items": [{"sku": SKU, "qty": qty, "name": "Baguete"}]},
        data={},
        save=lambda update_fields=None: None,
    )


def test_o_que_nao_coube_fica_gravado_no_pedido(vitrine):
    Quant.objects.create(sku=SKU, position=vitrine, _quantity=Decimal("1"))
    order = _order(3)

    stock_service.hold(order)

    assert order.data["hold_gaps"] == [{"sku": SKU, "qty": 2.0, "target_date": ""}]
    assert [entry["qty"] for entry in order.data["hold_ids"]] == [1.0]


def test_sem_falta_a_chave_nao_nasce(vitrine):
    Quant.objects.create(sku=SKU, position=vitrine, _quantity=Decimal("5"))
    order = _order(3)

    stock_service.hold(order)

    assert "hold_gaps" not in order.data


def test_a_edicao_que_consegue_reservar_apaga_a_falta(vitrine):
    from shopman.stockman import stock

    Quant.objects.create(sku=SKU, position=vitrine, _quantity=Decimal("1"))
    order = _order(3)
    stock_service.hold(order)
    stock.receive(quantity=Decimal("5"), sku=SKU, position=vitrine, reason="fornada que chegou")

    stock_service.reconcile_to_items(order, items=[{"sku": SKU, "qty": 3}], reference="edicao:GAP-1")

    assert "hold_gaps" not in order.data
    assert sum(entry["qty"] for entry in order.data["hold_ids"]) == 3.0


def test_a_edicao_que_ainda_nao_cabe_reescreve_a_falta(vitrine):
    Quant.objects.create(sku=SKU, position=vitrine, _quantity=Decimal("1"))
    order = _order(3)
    stock_service.hold(order)

    stock_service.reconcile_to_items(order, items=[{"sku": SKU, "qty": 5}], reference="edicao:GAP-1")

    assert order.data["hold_gaps"] == [{"sku": SKU, "qty": 4.0, "target_date": ""}]
