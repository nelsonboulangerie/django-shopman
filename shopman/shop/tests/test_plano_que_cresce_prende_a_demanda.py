"""Plano que cresce prende primeiro a demanda sem fornada da data (#2701).

Medido em 18/11 (teste sobre o branch do #2703): Baguette de Tradition, 22
planejadas para amanhã, encomenda de 30. Depois da encomenda, 22 presas e 8 de
demanda, livre 0. A Produção planeja mais 8 (o aviso "Planeje mais 8" pede isso),
e o livre de amanhã virava 8: as unidades novas seguiam prometíveis a qualquer
outro pedido. Agora elas se prendem à encomenda que pediu o aumento.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.craftsman.signals import production_changed
from shopman.orderman.models import Order
from shopman.stockman import stock
from shopman.stockman.models import Hold, Position

from shopman.shop.services import demand_anchor
from shopman.shop.services import stock as stock_service
from shopman.shop.tests.test_sobra_de_hoje_nao_lastreia_encomenda import (
    BAGUETE,
    DAY,
    _available,
)
from shopman.shop.tests.test_sobra_de_hoje_nao_lastreia_encomenda import casa as _casa_medida  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def hoje(request):
    """A casa medida em 18/11 (``test_sobra_de_hoje_nao_lastreia_encomenda``): 22 planejadas para amanhã."""
    return request.getfixturevalue("_casa_medida")


def _encomenda(ref: str, qty: int, target, *, channel: str = "web") -> Order:
    data = {"delivery_date": target.isoformat()}
    order = Order.objects.create(
        ref=ref, channel_ref=channel, status=Order.Status.ACCEPTED, total_q=qty * 1600, data=data,
        snapshot={"items": [{"sku": BAGUETE, "name": "Baguette de Tradition", "qty": qty, "line_id": "l1", "meta": {}}],
                  "data": dict(data)},
    )
    stock_service.hold(order, require_all=False)
    order.save(update_fields=["data"])
    order.refresh_from_db()
    return order


def _holds(order) -> list[Hold]:
    pks = stock_service.hold_pks(order.data["hold_ids"])
    return list(Hold.objects.filter(pk__in=pks).active())


def _backed_and_demand(order) -> tuple[Decimal, Decimal]:
    holds = _holds(order)
    backed = sum((h.quantity for h in holds if h.quant_id is not None), Decimal("0"))
    demand = sum((h.quantity for h in holds if h.quant_id is None), Decimal("0"))
    return backed, demand


def _plan_more(qty: int, target) -> None:
    from shopman.offerman.models import Product

    stock.plan(quantity=Decimal(qty), product=Product.objects.get(sku=BAGUETE), target_date=target,
               position=Position.objects.get(ref="producao"), reason="fornada")


def test_o_plano_que_cresce_prende_a_demanda_da_encomenda_e_o_livre_fica_zero(hoje):
    amanha = hoje + DAY
    order = _encomenda("ENC-30", 30, amanha)
    assert _backed_and_demand(order) == (Decimal("22"), Decimal("8"))
    assert stock_service.alert_demand_over_plan(order) == 1

    _plan_more(8, amanha)
    # Antes do conserto, aqui o livre de amanhã era 8.
    assert demand_anchor.anchor_demand(BAGUETE, amanha) == ["ENC-30"]

    order.refresh_from_db()
    assert _backed_and_demand(order) == (Decimal("30"), Decimal("0"))
    assert _available(BAGUETE, "web", amanha) == Decimal("0")
    from shopman.backstage.models import OperatorAlert

    alert = OperatorAlert.objects.get(type="order_demand_over_plan", order_ref="ENC-30")
    assert alert.resolved_at is not None, "o aviso “Planeje mais 8” deixou de ser verdade"


def test_plano_menor_que_a_demanda_prende_o_que_cabe_e_o_resto_segue_demanda(hoje):
    amanha = hoje + DAY
    order = _encomenda("ENC-30", 30, amanha)

    _plan_more(5, amanha)
    demand_anchor.anchor_demand(BAGUETE, amanha)

    order.refresh_from_db()
    assert _backed_and_demand(order) == (Decimal("27"), Decimal("3"))
    assert _available(BAGUETE, "web", amanha) == Decimal("0")


def test_a_encomenda_mais_antiga_vem_primeiro(hoje):
    amanha = hoje + DAY
    primeira = _encomenda("ENC-A", 26, amanha)  # 22 presas + 4 de demanda
    segunda = _encomenda("ENC-B", 4, amanha)  # 0 presas + 4 de demanda
    assert _backed_and_demand(segunda) == (Decimal("0"), Decimal("4"))

    _plan_more(4, amanha)
    demand_anchor.anchor_demand(BAGUETE, amanha)

    primeira.refresh_from_db()
    segunda.refresh_from_db()
    assert _backed_and_demand(primeira) == (Decimal("26"), Decimal("0"))
    assert _backed_and_demand(segunda) == (Decimal("0"), Decimal("4"))


def test_o_sinal_da_producao_prende_depois_do_commit(hoje, django_capture_on_commit_callbacks):
    amanha = hoje + DAY
    order = _encomenda("ENC-30", 30, amanha)

    with django_capture_on_commit_callbacks(execute=True):
        _plan_more(8, amanha)
        production_changed.send(sender=None, product_ref=BAGUETE, date=amanha, action="adjusted", work_order=None)

    order.refresh_from_db()
    assert _backed_and_demand(order) == (Decimal("30"), Decimal("0"))
