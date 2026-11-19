"""Toda divergência com o iFood vira aviso no Gestor (16/11/2026, DEV-2026-030).

Medido na produção: etapas que esgotaram as tentativas, cancelamento que não
chegou, CAN que não pôde ser aplicado e fatos do iFood parados no pedido ficavam
só no log. O Gestor mostrava uma coisa e a loja real no iFood outra.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.config import ChannelConfig
from shopman.shop.handlers.ifood_status import STATUS_NOT_DELIVERED_ALERT, IFoodStatusCallbackHandler
from shopman.shop.services import ifood_cancellation, ifood_events

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def external_channel():
    config = ChannelConfig(
        payment=ChannelConfig.Payment(method="external", timing="external"),
        fulfillment=ChannelConfig.Fulfillment(prep_start="operator"),
    )
    with (
        override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"}),
        patch.object(ChannelConfig, "for_channel", return_value=config),
    ):
        yield


def _order(status="preparing", *, ifood=None, data=None):
    return Order.objects.create(
        ref="IFOOD-SYNC", channel_ref="ifood", external_ref="remote-order", status=status,
        data={
            "fulfillment_type": "delivery",
            "ifood": {"delivered_by": "IFOOD", "display_id": "3417", **(ifood or {})},
            "payment": {"method": "external", "gateway": "ifood", "status": "paid"},
            **(data or {}),
        },
    )


def _alerts(type_):
    from shopman.backstage.models import OperatorAlert

    return list(OperatorAlert.objects.filter(type=type_))


# ── Etapa que esgotou as tentativas ──────────────────────────────────────────


@pytest.mark.parametrize("status,copy", [
    ("preparing", "o início do preparo"), ("ready", "o pedido pronto"), ("dispatched", "a saída para entrega"),
])
def test_etapa_que_nao_chegou_ao_ifood_vira_aviso_no_pedido(status, copy):
    order = _order(status)
    directive = Directive(
        topic="ifood.status_callback", last_error="HTTP 500",
        payload={"order_ref": order.ref, "ifood_order_id": "remote-order", "status": status},
    )

    IFoodStatusCallbackHandler().on_terminal_failure(message=directive)

    (alert,) = _alerts(STATUS_NOT_DELIVERED_ALERT)
    assert alert.order_ref == order.ref
    assert copy in alert.message and "#3417" in alert.message


def test_aceite_tem_aviso_proprio_e_nao_duplica():
    order = _order("accepted")
    directive = Directive(
        topic="ifood.status_callback",
        payload={"order_ref": order.ref, "ifood_order_id": "remote-order", "status": "accepted"},
    )

    IFoodStatusCallbackHandler().on_terminal_failure(message=directive)

    assert _alerts(STATUS_NOT_DELIVERED_ALERT) == []


# ── Cancelamento da loja que não chegou ──────────────────────────────────────


def test_cancelamento_que_nao_chegou_destrava_o_pedido_e_avisa():
    order = _order("accepted", data={ifood_cancellation.KEY: {
        "id": "req-1", "state": "error", "retryable": True, "reason": "Loja cheia", "code": "501",
    }})
    assert ifood_cancellation.is_pending(order)

    IFoodStatusCallbackHandler().on_terminal_failure(message=Directive(
        topic="ifood.status_callback", last_error="HTTP 502",
        payload={"order_ref": order.ref, "ifood_order_id": "remote-order", "status": "cancelled",
                 "cancellation_request_id": "req-1"},
    ))

    order.refresh_from_db()
    assert not ifood_cancellation.is_pending(order)  # antes: travado para sempre
    (alert,) = _alerts(ifood_cancellation.NOT_DELIVERED_ALERT_TYPE)
    assert "não chegou ao iFood" in alert.message


# ── CAN do iFood: motivo guardado; pedido adiantado demais avisa ─────────────


def _can(metadata=None, event_id="can-1"):
    return {"id": event_id, "code": "CAN", "orderId": "remote-order", "merchantId": "test-store",
            "metadata": metadata or {}}


def test_cancelamento_do_ifood_guarda_origem_e_motivo():
    order = _order("new")
    with patch.object(ifood_events, "acknowledge", return_value=True):
        ifood_events.process_events([_can({
            "CANCEL_ORIGIN": "CONSUMER", "CANCEL_CODE": "506", "CANCEL_REASON": "Desisti do pedido",
        })])

    order.refresh_from_db()
    assert order.status == "cancelled"
    facts = order.data["ifood"]["remote_cancelled"]
    assert (facts["origin"], facts["code"], facts["reason"]) == ("CONSUMER", "506", "Desisti do pedido")
    assert order.data["cancellation_reason"] == "Cancelado no iFood por o cliente: Desisti do pedido"


def test_cancelamento_do_ifood_sem_metadata_mantem_a_frase_de_sempre():
    order = _order("new")
    with patch.object(ifood_events, "acknowledge", return_value=True):
        ifood_events.process_events([_can()])

    order.refresh_from_db()
    assert order.data["cancellation_reason"] == "Cancelamento confirmado pelo iFood"


def test_ifood_cancelou_pedido_que_aqui_ja_saiu_avisa_para_nao_entregar():
    order = _order("dispatched")
    with patch.object(ifood_events, "acknowledge", return_value=True) as ack:
        summary = ifood_events.process_events([_can({"CANCEL_ORIGIN": "IFOOD"})])

    assert summary["failed"] == 1
    ack.assert_not_called()
    (alert,) = _alerts(ifood_events.CANCELLED_NOT_APPLIED_ALERT)
    assert alert.severity == "critical" and "Não entregue" in alert.message
    order.refresh_from_db()
    assert order.status == "dispatched"


# ── Fatos do iFood parados no pedido ─────────────────────────────────────────


def _fact(minutes_ago):
    return {"event_id": "e", "observed_at": (timezone.now() - timedelta(minutes=minutes_ago)).isoformat()}


def test_fato_recente_parado_e_aplicado_pela_varredura():
    order = _order("preparing", ifood={"remote_dispatched": _fact(10), "remote_concluded": _fact(5)})

    call_command("reconcile_ifood_orders", stdout=StringIO())

    order.refresh_from_db()
    assert order.status == "completed"


def test_fato_velho_nao_anda_sozinho_vira_aviso():
    """O 3417: concluído no iFood em 12/11 e "Em preparo" aqui quatro dias depois."""
    order = _order("preparing", ifood={"remote_dispatched": _fact(4 * 24 * 60), "remote_concluded": _fact(4 * 24 * 60)})

    call_command("reconcile_ifood_orders", stdout=StringIO())

    order.refresh_from_db()
    assert order.status == "preparing"
    (alert,) = _alerts("ifood_order_behind")
    assert "o iFood já concluiu" in alert.message and alert.order_ref == order.ref
