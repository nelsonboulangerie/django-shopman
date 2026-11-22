"""Aviso que um fato já encerrou fecha sozinho, retroativamente (#3079, #3080 e vizinhas).

A primeira rodada da ponte de incidentes (21/11/2026) achou dezenas de avisos
abertos desde setembro sobre pedido de teste, lote do seed e tipo que o código não
cria mais, e 42 "pedido sem reserva" de pedidos já entregues. Nenhum gesto de gente
os fecharia: o fato fecha, com o motivo. O que não tem fato (pedido de verdade em
curso, lote real esquecido) segue aberto.
"""

from __future__ import annotations

import pytest
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.handlers.alert_resolution import on_order_changed, resolve_alerts_ended_by_fact
from shopman.shop.models import Shop
from shopman.shop.services.observability import create_operator_alert

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def recipe():
    return Recipe.objects.create(ref="ensaio", name="Ensaio", output_sku="ENSAIO", batch_size=1)


def _alert(alert_type, ref, *, severity="warning"):
    create_operator_alert(
        type=alert_type, severity=severity, order_ref=ref, message=f"Aviso de {ref}",
        dedupe_key=f"{alert_type}:{ref}",
    )
    return OperatorAlert.objects.get(type=alert_type, order_ref=ref)


def _work_order(recipe, *, status="planned", source_ref="", meta=None):
    return WorkOrder.objects.create(
        recipe=recipe, output_sku=recipe.output_sku, quantity=3, status=status,
        source_ref=source_ref, meta=meta or {},
    )


def _closed_by(alert):
    alert.refresh_from_db()
    return alert.resolved_by if alert.resolved_at else None


def test_seed_lot_alerts_close_with_the_reason(recipe):
    by_source = _work_order(recipe, source_ref="seed:production:today:ENSAIO")
    by_meta = _work_order(recipe, meta={"seed": True, "scope": "qa-stuck"})
    forgotten = _alert("production_forgotten", by_source.ref)
    late = _alert("production_late", by_meta.ref)

    assert resolve_alerts_ended_by_fact() == 2
    assert _closed_by(forgotten) == "sistema: lote do seed"
    assert _closed_by(late) == "sistema: lote do seed"


def test_real_lot_left_open_stays_with_people(recipe):
    real = _work_order(recipe, source_ref="production:gerente")
    alert = _alert("production_forgotten", real.ref)
    assert resolve_alerts_ended_by_fact() == 0
    assert _closed_by(alert) is None


def test_real_lot_that_already_closed_ends_the_alerts_its_close_ends(recipe):
    finished = _work_order(recipe, status="finished", source_ref="production:gerente")
    unfinished = _alert("production_unfinished", finished.ref)
    shortfall = _alert("production_stock_shortfall", finished.ref, severity="error")

    resolve_alerts_ended_by_fact()
    assert _closed_by(unfinished) == "sistema: lote já fechado"
    # Baixa menor que a ficha é sobre o lote FECHADO: fechar o lote não a desmente.
    assert _closed_by(shortfall) is None


def test_lot_that_no_longer_exists_closes():
    alert = _alert("production_late", "WO-2026-00077")
    resolve_alerts_ended_by_fact()
    assert _closed_by(alert) == "sistema: lote que não existe mais"


def test_test_and_seed_orders_close_real_and_missing_orders_stay():
    Order.objects.create(ref="IFOOD-T1", channel_ref="ifood", status="completed", total_q=1000,
                         data={"ifood": {"is_test": True}})
    Order.objects.create(ref="PDV-S1", channel_ref="pdv", status="completed", total_q=1000,
                         session_key="seed-PDV-S1")
    Order.objects.create(ref="PDV-S2", channel_ref="pdv", status="completed", total_q=1000,
                         snapshot={"seed": "nelson"})
    Order.objects.create(ref="WEB-R1", channel_ref="web", status="completed", total_q=1000)
    test = _alert("ifood_order_behind", "IFOOD-T1")
    seed_session = _alert("notification_failed", "PDV-S1", severity="error")
    seed_snapshot = _alert("stock_fulfill_failed", "PDV-S2", severity="critical")
    real = _alert("payment_failed", "WEB-R1", severity="error")
    missing = _alert("payment_failed", "WEB-GONE", severity="error")

    assert resolve_alerts_ended_by_fact() == 3
    assert _closed_by(test) == "sistema: pedido de teste"
    assert _closed_by(seed_session) == "sistema: pedido do seed"
    assert _closed_by(seed_snapshot) == "sistema: pedido do seed"
    assert _closed_by(real) is None
    assert _closed_by(missing) is None, "ref que não acha pedido pode não ser de pedido: fica com gente"


def test_retired_type_closes_and_alert_without_object_stays():
    retired = _alert("customer_cancellation_requested", "")
    no_object = _alert("unhandled_exception", "", severity="error")
    resolve_alerts_ended_by_fact()
    assert _closed_by(retired) == "sistema: tipo que o código não cria mais"
    assert _closed_by(no_object) is None


def test_hold_gap_of_a_delivered_order_closes_and_of_an_open_order_stays():
    Order.objects.create(ref="PDV-D1", channel_ref="pdv", status="completed", total_q=1000)
    Order.objects.create(ref="IFOOD-C1", channel_ref="ifood", status="cancelled", total_q=1000)
    Order.objects.create(ref="PDV-P1", channel_ref="pdv", status="preparing", total_q=1000)
    delivered = _alert("stock_hold_gap", "PDV-D1")
    cancelled = _alert("stock_hold_gap", "IFOOD-C1")
    preparing = _alert("stock_hold_gap", "PDV-P1")

    assert resolve_alerts_ended_by_fact() == 2
    assert _closed_by(delivered) == "sistema: pedido já entregue"
    assert _closed_by(cancelled) == "sistema: pedido já desfeito"
    assert _closed_by(preparing) is None, "ainda vai separar: o aviso vale"


def test_hold_gap_closes_live_when_the_order_is_delivered(django_capture_on_commit_callbacks):
    order = Order.objects.create(ref="PDV-L1", channel_ref="pdv", status="completed", total_q=1000)
    alert = _alert("stock_hold_gap", "PDV-L1")
    with django_capture_on_commit_callbacks(execute=True):
        on_order_changed(None, order=order, event_type="status_changed", actor="caixa")
    assert _closed_by(alert) == "order-status:caixa"
