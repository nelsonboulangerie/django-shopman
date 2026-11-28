"""Uma régua só (WP-F08): a Produção lê o prometido das reservas, por produto e data.

Plano da Produção, seção 4.1: a projeção publica, por SKU e data, o planejado,
o encomendado, o livre e os pedidos, pela mesma leitura do PDV
(``adapters/stock.planned_on_date``) e pelas reservas dos pedidos abertos da
data. A encomenda de amanhã aparece no lote de AMANHÃ, nunca no de hoje; a data
sem lote traz a demanda.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.orderman.models import Order
from shopman.stockman.models import Hold, HoldStatus, Quant

from shopman.backstage.projections.production import build_production_board, build_qc_kiosk, build_work_order_card

pytestmark = pytest.mark.django_db

SKU = "CROISSANT"


def _today():
    return timezone.localdate()


def _tomorrow():
    return _today() + timedelta(days=1)


@pytest.fixture
def recipe():
    return Recipe.objects.create(
        ref="croissant-v1",
        name="Croissant",
        output_sku=SKU,
        batch_size=Decimal("10"),
        steps=["Laminação", "Forno"],
    )


def _plan(recipe, qty: int, day):
    """O lote planejado; o saldo planejado da data nasce com ele (o receiver do plano)."""
    wo = craft.plan(recipe, qty, date=day, position_ref="forno")
    assert Quant.objects.filter(sku=SKU, target_date=day).exists()
    return wo


def _order(ref: str, *, day, qty: str, status: str = "accepted", name: str = "Clara Souza", slot: str = "", held: bool = True, fulfillment: str = "pickup") -> Order:
    """Uma encomenda aberta para ``day``, com a reserva presa ao lote da data (ou sem lote)."""
    quant = Quant.objects.filter(sku=SKU, target_date=day).first()
    hold = Hold.objects.create(
        sku=SKU,
        quant=quant if held else None,
        quantity=Decimal(qty),
        target_date=day,
        status=HoldStatus.CONFIRMED,
        metadata={"reference": f"order:{ref}"},
    )
    data = {
        "customer": {"name": name},
        "fulfillment_type": fulfillment,
        "delivery_date": day.isoformat(),
        "hold_ids": [{"sku": SKU, "hold_id": hold.hold_id, "qty": qty}],
    }
    if slot:
        data["delivery_time_slot"] = slot
    return Order.objects.create(ref=ref, channel_ref="web", status=status, total_q=1000, data=data)


def _row(board):
    return next(row for row in board.matrix_rows if row.output_sku == SKU)


def test_a_encomenda_de_amanha_aparece_no_lote_de_amanha_e_nao_no_de_hoje(recipe):
    today_lot = _plan(recipe, 20, _today())
    tomorrow_lot = _plan(recipe, 10, _tomorrow())
    _order("ENC-1", day=_tomorrow(), qty="1", fulfillment="pickup")

    tomorrow = build_production_board(selected_date=_tomorrow())
    promised = _row(tomorrow).promised
    assert promised is not None
    assert promised.date == _tomorrow().isoformat()
    assert (promised.planned_qty, promised.ordered_qty, promised.free_qty, promised.over_plan_qty) == ("10", "1", "9", "0")
    [order] = promised.orders
    assert (order.ref, order.customer_first_name, order.fulfillment_type, order.qty) == ("ENC-1", "Clara", "pickup", "1")
    card = next(card for card in tomorrow.work_orders if card.ref == tomorrow_lot.ref)
    assert card.promised == promised

    today = build_production_board(selected_date=_today())
    today_promised = _row(today).promised
    assert today_promised is not None
    assert today_promised.ordered_qty == "0"
    assert today_promised.orders == ()
    assert build_work_order_card(today_lot.ref).promised.orders == ()
    assert build_work_order_card(tomorrow_lot.ref).promised.orders[0].ref == "ENC-1"


def test_data_sem_lote_traz_a_demanda(recipe):
    _order("ENC-2", day=_tomorrow(), qty="12", held=False, name="Bruno")

    promised = _row(build_production_board(selected_date=_tomorrow())).promised

    assert promised is not None
    assert (promised.planned_qty, promised.ordered_qty, promised.free_qty, promised.over_plan_qty) == ("0", "12", "0", "12")
    assert [order.ref for order in promised.orders] == ["ENC-2"]


def test_encomenda_acima_do_plano_diz_quanto_o_plano_nao_cobre(recipe):
    _plan(recipe, 10, _tomorrow())
    _order("ENC-3", day=_tomorrow(), qty="10", slot="09:00-09:30")
    gap = _order("ENC-4", day=_tomorrow(), qty="4", held=False, name="Dora")

    promised = _row(build_production_board(selected_date=_tomorrow())).promised

    assert (promised.planned_qty, promised.ordered_qty, promised.free_qty, promised.over_plan_qty) == ("10", "14", "0", "4")
    assert {order.ref for order in promised.orders} == {"ENC-3", gap.ref}


def test_encomenda_paga_ainda_nao_aceita_conta_no_prometido(recipe):
    _plan(recipe, 10, _tomorrow())
    _order("ENC-5", day=_tomorrow(), qty="3", status="new")

    [order] = _row(build_production_board(selected_date=_tomorrow())).promised.orders

    assert order.status == "new"
    assert order.status_label


def test_pedido_cancelado_e_de_outra_data_nao_entram(recipe):
    _plan(recipe, 10, _tomorrow())
    after = _tomorrow() + timedelta(days=1)
    _plan(recipe, 10, after)
    _order("ENC-6", day=_tomorrow(), qty="2", status="cancelled")
    _order("ENC-7", day=after, qty="5")

    promised = _row(build_production_board(selected_date=_tomorrow())).promised

    assert promised.ordered_qty == "0"
    assert promised.orders == ()


def test_pedidos_vem_pela_hora_e_o_telefone_nao_vira_nome(recipe):
    _plan(recipe, 20, _tomorrow())
    _order("ENC-8", day=_tomorrow(), qty="2", slot="11:00-11:30", name="Elisa")
    _order("ENC-9", day=_tomorrow(), qty="1", slot="08:00-08:30", name="+5543999990001", fulfillment="delivery")

    orders = _row(build_production_board(selected_date=_tomorrow())).promised.orders

    assert [order.ref for order in orders] == ["ENC-9", "ENC-8"]
    assert orders[0].customer_first_name == ""
    assert orders[0].fulfillment_type == "delivery"
    assert orders[0].due_time == "08:00"


def test_sem_plano_nem_pedido_nao_ha_prometido(recipe):
    assert _row(build_production_board(selected_date=_tomorrow())).promised is None


def test_finalizacao_le_o_encomendado_da_data_pela_mesma_regua(recipe):
    """WP-F10: o "N encomendadas" da Finalização sai da régua das reservas: o
    lote de amanhã traz a encomenda de amanhã, o de hoje não traz nada."""
    _plan(recipe, 20, _today())
    _plan(recipe, 10, _tomorrow())
    _order("ENC-QC", day=_tomorrow(), qty="1")

    [today_card] = build_qc_kiosk(selected_date=_today()).orders
    assert today_card.promised is not None
    assert today_card.promised.ordered_qty == "0"
    [tomorrow_card] = build_qc_kiosk(selected_date=_tomorrow()).orders
    assert tomorrow_card.promised.ordered_qty == "1"
    assert [order.customer_first_name for order in tomorrow_card.promised.orders] == ["Clara"]
