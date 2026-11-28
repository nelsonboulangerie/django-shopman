"""As travas de encomenda medem só a data do lote (#3682).

Abrir o Croissant de 30/11 era recusado com "Encomendado: 162" quando a data tinha 60:
a trava dava ao lote medido capacidade sem fim e o alocador aceita lote de data
anterior, então ele absorvia as encomendas de 01/12, 10/12 e 12/12, até a que tinha
lote próprio. Encomenda se mede só contra a fornada da data (dono, 18/11/2026, #2679).
As três travas usam a mesma conta: abrir, fechar (WP-F06) e reduzir o plano.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from itertools import count

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.services.production import (
    ProductionOrderShortError,
)
from shopman.backstage.services.production import (
    apply_finish as _raw_apply_finish,
)
from shopman.backstage.services.production import (
    apply_planned as _raw_apply_planned,
)
from shopman.backstage.services.production import (
    apply_start as _raw_apply_start,
)
from shopman.shop.handlers.production_order_sync import (
    ORDER_AWAITING_WO_REFS_KEY,
    link_order_to_work_orders,
    linked_order_refs,
)

_keys = count(1)

TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)
LATER_WITH_LOT = TODAY + timedelta(days=10)
LATER_WITHOUT_LOT = TODAY + timedelta(days=12)


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="trava-data-croissant",
        name="Croissant Manteiga",
        output_sku="CROISSANT-DATA",
        batch_size=Decimal("10"),
    )


def _order(ref: str, qty: int, day: date) -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status="accepted",
        total_q=1000,
        data={"delivery_date": day.isoformat()},
    )
    OrderItem.objects.create(
        order=order,
        line_id=f"{ref}-1",
        sku="CROISSANT-DATA",
        name="Croissant Manteiga",
        qty=qty,
        unit_price_q=500,
        line_total_q=qty * 500,
    )
    link_order_to_work_orders(order=order, event_type="status_changed")
    return order


@pytest.fixture
def scenario(recipe):
    """O caso medido no #3682, em escala: 6 para hoje e 15 em outras datas."""
    today_lot = craft.plan(recipe, 6, date=TODAY, position_ref="")
    later_lot = craft.plan(recipe, 3, date=LATER_WITH_LOT, position_ref="")
    orders = {
        "today": _order("DATA-HOJE", 6, TODAY),
        "tomorrow": _order("DATA-AMANHA", 6, TOMORROW),
        "later_with_lot": _order("DATA-COM-LOTE", 3, LATER_WITH_LOT),
        "later_without_lot": _order("DATA-SEM-LOTE", 2, LATER_WITHOUT_LOT),
    }
    today_lot.refresh_from_db()
    later_lot.refresh_from_db()
    return today_lot, later_lot, orders


def _start(work_order, quantity: str):
    work_order.refresh_from_db()
    return _raw_apply_start(
        work_order_id=work_order.pk,
        quantity=quantity,
        actor="production:test",
        expected_rev=work_order.rev,
        idempotency_key=f"trava-data-start-{next(_keys)}",
    )


@pytest.mark.django_db
def test_abrir_o_lote_do_dia_conta_so_as_encomendas_da_data(scenario):
    today_lot, _, _ = scenario

    _start(today_lot, "6")

    today_lot.refresh_from_db()
    assert today_lot.status == WorkOrder.Status.STARTED


@pytest.mark.django_db
def test_abrir_abaixo_da_data_recusa_com_o_numero_da_data(scenario):
    today_lot, _, orders = scenario

    with pytest.raises(ProductionOrderShortError) as exc_info:
        _start(today_lot, "5")

    assert exc_info.value.required == Decimal("6")
    assert exc_info.value.order_refs == (orders["today"].ref,)


@pytest.mark.django_db
def test_abrir_nao_rouba_a_encomenda_de_outra_data(scenario):
    """A gravação do vínculo depois da trava não traz para hoje a encomenda de outro dia."""
    today_lot, later_lot, orders = scenario

    _start(today_lot, "6")

    today_lot.refresh_from_db()
    later_lot.refresh_from_db()
    assert linked_order_refs(today_lot) == (orders["today"].ref,)
    assert orders["later_with_lot"].ref in linked_order_refs(later_lot)
    for key in ("tomorrow", "later_with_lot", "later_without_lot"):
        orders[key].refresh_from_db()
        assert today_lot.ref not in (orders[key].data.get(ORDER_AWAITING_WO_REFS_KEY) or ())


@pytest.mark.django_db
def test_fechar_abaixo_mede_so_as_encomendas_da_data(scenario):
    """A trava de fechar (WP-F06) mostra o encomendado da data, não o de todas as datas."""
    today_lot, _, orders = scenario
    _start(today_lot, "6")
    today_lot.refresh_from_db()

    with pytest.raises(ProductionOrderShortError) as exc_info:
        _raw_apply_finish(
            work_order_id=today_lot.pk,
            quantity="5",
            yield_deviation_confirmed=True,
            yield_deviation_reason="massa rendeu menos",
            actor="production:test",
            expected_rev=today_lot.rev,
            idempotency_key=f"trava-data-finish-{next(_keys)}",
        )

    assert exc_info.value.required == Decimal("6")
    assert exc_info.value.order_refs == (orders["today"].ref,)


@pytest.mark.django_db
def test_reduzir_o_plano_do_dia_conta_so_as_encomendas_da_data(recipe, scenario):
    today_lot, _, orders = scenario

    _, work_order_ref, quantity, _ = _raw_apply_planned(
        recipe_id=recipe.pk,
        work_order_id=today_lot.pk,
        quantity="6",
        target_date_value=TODAY.isoformat(),
        actor="test",
        expected_rev=today_lot.rev,
        idempotency_key=f"trava-data-plan-{next(_keys)}",
    )
    assert work_order_ref == today_lot.ref
    assert quantity == Decimal("6")

    today_lot.refresh_from_db()
    with pytest.raises(ProductionOrderShortError) as exc_info:
        _raw_apply_planned(
            recipe_id=recipe.pk,
            work_order_id=today_lot.pk,
            quantity="5",
            target_date_value=TODAY.isoformat(),
            actor="test",
            expected_rev=today_lot.rev,
            idempotency_key=f"trava-data-plan-{next(_keys)}",
        )
    assert exc_info.value.required == Decimal("6")
    assert exc_info.value.order_refs == (orders["today"].ref,)
