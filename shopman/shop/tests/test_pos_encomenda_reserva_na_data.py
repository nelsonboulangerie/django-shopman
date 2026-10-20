"""PDV: a encomenda reserva contra a data dela, não contra hoje.

O balcão não reserva enquanto monta a comanda; a reserva nasce no commit
(``services/stock.hold``), na data do pedido. Estes testes prendem as duas
pontas: o pronto de hoje esgotado não impede a encomenda de amanhã quando a
fornada de amanhã existe, e o pronto de hoje (pão do dia) não serve a quem
encomendou para amanhã.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Order
from shopman.stockman import stock
from shopman.stockman.models import Batch, Hold, Position, PositionKind

from shopman.shop.tests.test_pos_scheduled_order import _close, _payload, balcao  # noqa: F401

pytestmark = pytest.mark.django_db


def _position():
    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


def _croissant_do_dia():
    product = Product.objects.get(sku="CR")
    product.shelf_life_days = 0
    product.save(update_fields=["shelf_life_days"])
    return product


def _pronto(qty: str):
    stock.receive(quantity=Decimal(qty), sku="CR", position=_position(), target_date=None, reason="pronto")
    # Produto com validade ganha lote; só lote classificado é vendável.
    Batch.objects.filter(sku="CR", quality_grade_ref="").update(quality_grade_ref="standard")


def _amanha():
    return timezone.localdate() + timedelta(days=1)


def _holds_do_pedido(order):
    ids = [int(str(entry["hold_id"]).split(":")[1]) for entry in order.data.get("hold_ids", [])]
    return list(Hold.objects.filter(pk__in=ids))


def test_pronto_de_hoje_esgotado_nao_impede_encomenda_da_fornada_de_amanha(balcao, django_capture_on_commit_callbacks):  # noqa: F811
    operator, shift = balcao
    product = _croissant_do_dia()
    _pronto("2")
    stock.hold(Decimal("2"), product, target_date=timezone.localdate(), reference="outra-venda")
    stock.plan(quantity=Decimal("4"), product=product, target_date=_amanha(), position=_position(), reason="fornada")

    with django_capture_on_commit_callbacks(execute=True):
        result = _close(operator, _payload(
            shift, client_request_id="enc-amanha", delivery_date=_amanha().isoformat(),
            items=[{"sku": "CR", "name": "Croissant", "qty": 3, "unit_price_q": 900}],
        ))

    order = Order.objects.get(ref=result.order_ref)
    holds = _holds_do_pedido(order)
    assert sum(h.quantity for h in holds) == Decimal("3")
    assert {h.target_date for h in holds} == {_amanha()}
    assert {h.quant.target_date for h in holds if h.quant} == {_amanha()}, "sai da fornada de amanhã"


def test_pronto_de_hoje_nao_serve_encomenda_de_amanha(balcao, django_capture_on_commit_callbacks):  # noqa: F811
    operator, shift = balcao
    _croissant_do_dia()
    _pronto("5")

    with django_capture_on_commit_callbacks(execute=True):
        result = _close(operator, _payload(
            shift, client_request_id="enc-sem-fornada", delivery_date=_amanha().isoformat(),
        ))

    order = Order.objects.get(ref=result.order_ref)
    holds = _holds_do_pedido(order)
    assert holds, "a encomenda registra a demanda da data"
    assert all(h.quant is None for h in holds), "o pão do dia de hoje não é reservado para amanhã"
    assert {h.target_date for h in holds} == {_amanha()}
