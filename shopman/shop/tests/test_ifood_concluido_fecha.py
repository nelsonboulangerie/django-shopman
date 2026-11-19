"""CON do iFood fecha o pedido aqui quando o andamento é do iFood.

Medido em produção em 19/11/2026: oito pedidos de TESTE de 07 e 09/11 seguiam
"Aceito" no Gestor, com "Concluído no iFood" na linha do tempo, poluindo as
Entregas. Pedido de teste e entrega com entregador do iFood fecham pelos passos
de sempre; entregador da casa e retirada continuam esperando a custódia daqui.
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.services import ifood_events

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_ifood_config():
    with override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"}):
        yield


def _event(event_id="con-1"):
    return {"id": event_id, "code": "CON", "orderId": "order-1", "merchantId": "test-store"}


def _order(status, *, is_test=False, delivered_by="MERCHANT", fulfillment_type="delivery", facts=None):
    ifood = {"is_test": is_test, "delivered_by": delivered_by, **(facts or {})}
    return Order.objects.create(
        ref="IFOOD-FECHA", channel_ref="ifood", external_ref="order-1", status=status,
        data={"fulfillment_type": fulfillment_type, "payment": {"method": "external", "status": "paid"}, "ifood": ifood},
    )


def _statuses(order):
    return [e["new_status"] for e in order.events.filter(type="status_changed").values_list("payload", flat=True)]


@pytest.mark.parametrize("status", [Order.Status.ACCEPTED, Order.Status.PREPARING, Order.Status.READY])
@pytest.mark.parametrize(("is_test", "delivered_by"), [(True, "MERCHANT"), (False, "IFOOD")])
def test_con_fecha_pedido_cujo_andamento_e_do_ifood(status, is_test, delivered_by):
    order = _order(status, is_test=is_test, delivered_by=delivered_by)
    with patch.object(ifood_events, "acknowledge", return_value=True):
        assert ifood_events.process_events([_event()])["ingested"] == 1
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED
    assert _statuses(order)[-3:] == ["dispatched", "delivered", "completed"]
    # Nenhum aviso ecoa ao iFood: ele já encerrou.
    assert not Directive.objects.filter(topic="ifood.status_callback").exists()


def test_pedido_de_teste_concluido_nao_emite_nota_nem_avisa():
    """Sem mock no fiscal nem na notificação: o caminho real fica inerte."""
    order = _order(Order.Status.ACCEPTED, is_test=True)
    with patch.object(ifood_events, "acknowledge", return_value=True):
        ifood_events.process_events([_event()])
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED
    topics = set(Directive.objects.values_list("topic", flat=True))
    assert not {t for t in topics if t.startswith(("fiscal", "notification", "ifood.status"))}


@pytest.mark.parametrize(("delivered_by", "fulfillment_type"), [("MERCHANT", "delivery"), ("", "pickup")])
def test_pedido_real_com_custodia_da_casa_continua_esperando(delivered_by, fulfillment_type):
    order = _order(Order.Status.ACCEPTED, delivered_by=delivered_by, fulfillment_type=fulfillment_type)
    with patch.object(ifood_events, "acknowledge", return_value=True):
        assert ifood_events.process_events([_event()])["ingested"] == 1
    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED
    assert order.data["ifood"]["remote_concluded"]["event_id"] == "con-1"


def _stale_fact(days=12):
    return {"remote_concluded": {"event_id": "old", "observed_at": (timezone.now() - timedelta(days=days)).isoformat()}}


def test_manutencao_recupera_pedido_de_teste_preso_e_e_idempotente():
    order = _order(Order.Status.ACCEPTED, is_test=True, facts=_stale_fact())
    out = StringIO()
    call_command("reconcile_ifood_orders", stdout=out)
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED
    assert "IFOOD-FECHA accepted → completed" in out.getvalue()
    events = order.events.count()
    call_command("reconcile_ifood_orders", stdout=StringIO())
    order.refresh_from_db()
    assert order.events.count() == events
    assert not Directive.objects.filter(topic__startswith="fiscal").exists()


def test_manutencao_nao_fecha_pedido_real_antigo_so_avisa():
    """Pedido real fora da janela fecharia com nota e aviso atrasados: o operador decide."""
    from shopman.backstage.models import OperatorAlert

    order = _order(Order.Status.PREPARING, delivered_by="IFOOD", facts=_stale_fact())
    call_command("reconcile_ifood_orders", stdout=StringIO())
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING
    assert OperatorAlert.objects.filter(type="ifood_order_behind", order_ref=order.ref).exists()


def test_manutencao_nao_mexe_em_pedido_de_teste_sem_conclusao():
    order = _order(Order.Status.ACCEPTED, is_test=True, facts={
        "remote_dispatched": {"event_id": "old", "observed_at": (timezone.now() - timedelta(days=12)).isoformat()},
    })
    call_command("reconcile_ifood_orders", stdout=StringIO())
    order.refresh_from_db()
    assert order.status == Order.Status.ACCEPTED
