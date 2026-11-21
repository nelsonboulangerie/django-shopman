"""A "etapa travada" que o domínio já superou fecha sozinha, retroativamente (#3029).

Reproduz os alertas reais de 18 e 19/11/2026: oito pedidos de TESTE do iFood cuja
etapa do preparo chegou com o pedido já concluído, e o IFOOD-261118-3030 (pedido de
verdade, etapa do pronto com o pedido despachado), que segue aberto: aquele é
travamento, e quem decide é gente.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.shop import lifecycle
from shopman.shop.handlers.alert_resolution import resolve_superseded_phase_alerts
from shopman.shop.models import Shop
from shopman.shop.services.observability import create_operator_alert

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def shop(db):
    return Shop.objects.create(name="Loja")


def _order(ref, status, *, test=False, data=None):
    payload = {"ifood": {"is_test": True}} if test else {}
    return Order.objects.create(ref=ref, channel_ref="ifood", status=status, total_q=1000, data={**payload, **(data or {})})


def _stuck(ref, phase):
    create_operator_alert(
        type="lifecycle_phase_stuck", severity="critical", order_ref=ref,
        message=lifecycle.phase_stuck_message(ref, phase, "Phase cannot resume"),
        dedupe_key=f"lifecycle_phase_stuck:{ref}:{phase}",
    )
    return OperatorAlert.objects.get(type="lifecycle_phase_stuck", order_ref=ref)


def test_test_orders_with_superseded_preparation_close_with_the_reason():
    alerts = []
    for ref in ("IFOOD-261107-9197", "IFOOD-261109-1273"):
        _order(ref, "completed", test=True)
        alerts.append(_stuck(ref, "on_preparing"))

    assert resolve_superseded_phase_alerts() == 2

    for alert in alerts:
        alert.refresh_from_db()
        assert alert.resolved_at is not None
        assert alert.resolved_by == "sistema: pedido de teste"


def test_real_order_preparation_after_close_also_closes():
    _order("WEB-1", "completed")
    alert = _stuck("WEB-1", "on_preparing")
    resolve_superseded_phase_alerts()
    alert.refresh_from_db()
    assert alert.resolved_by == "sistema: pedido já completed, etapa superada"


def test_phase_that_completed_later_closes():
    _order("WEB-2", "completed", data={lifecycle.LIFECYCLE_DATA_KEY: {"on_ready": lifecycle.PHASE_DONE}})
    alert = _stuck("WEB-2", "on_ready")
    resolve_superseded_phase_alerts()
    alert.refresh_from_db()
    assert alert.resolved_by == "sistema: etapa concluída depois"


def test_real_stuck_phase_stays_open_for_people():
    _order("IFOOD-261118-3030", "completed")
    alert = _stuck("IFOOD-261118-3030", "on_ready")
    assert resolve_superseded_phase_alerts() == 0
    alert.refresh_from_db()
    assert alert.resolved_at is None


def test_the_domain_sweep_runs_it_every_cycle_and_dry_run_touches_nothing():
    _order("IFOOD-261109-8804", "completed", test=True)
    alert = _stuck("IFOOD-261109-8804", "on_preparing")
    call_command("sweep_stuck_orders", dry_run=True)
    alert.refresh_from_db()
    assert alert.resolved_at is None
    call_command("sweep_stuck_orders")
    alert.refresh_from_db()
    assert alert.resolved_at is not None
