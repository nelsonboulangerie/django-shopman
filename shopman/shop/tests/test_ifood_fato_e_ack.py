"""ACK é "armazenei", não "apliquei".

Homologação de 21/09/2026: o iFood concluiu três pedidos (CON) às 14:54:56 com
eles ainda em "aceito"/"em preparo" aqui. O processamento recusava o evento até o
pedido local sair para entrega, deixava sem ACK, e o iFood reentregava a cada 30s
por quatro minutos — o Firefly Audit mediu isso (8/10). No Gestor, o pedido 1416
continuava "Em preparo" um minuto depois de encerrado lá.

A doc do polling pede ACK "após armazenar o evento". Estes testes travam a regra:
o fato do iFood é gravado e reconhecido na hora; a aplicação local segue as
mesmas regras de sempre (não inventa preparo, não pula a custódia do entregador)
e acontece quando o pedido local chega ao ponto certo — sem aviso ecoar ao iFood.
"""
from unittest.mock import patch

import pytest
from django.test import override_settings
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.ifood_status import on_order_status_changed
from shopman.shop.services import ifood_events

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_ifood_config():
    with override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"}):
        yield


def _event(code, event_id, created_at=""):
    event = {"id": event_id, "code": code, "orderId": "order-1", "merchantId": "test-store"}
    if created_at:
        event["createdAt"] = created_at
    return event


def _order(status, delivered_by="MERCHANT", fulfillment_type="delivery"):
    return Order.objects.create(
        ref="IFOOD-260921-1416", channel_ref="ifood", external_ref="order-1", status=status,
        data={
            "fulfillment_type": fulfillment_type,
            "payment": {"method": "external", "status": "paid"},
            "ifood": {"delivered_by": delivered_by},
        },
    )


def _operator_moves(order, status):
    """O operador avança no Gestor; o signal (conectado só com client_id) roda."""
    order.transition_status(status, actor="operator:admin")
    on_order_status_changed(sender=None, order=order, event_type="status_changed", actor="operator:admin")
    order.refresh_from_db()


def _callbacks_for(*statuses):
    return Directive.objects.filter(topic="ifood.status_callback", payload__status__in=list(statuses))


def test_pedido_concluido_no_ifood_com_cozinha_em_preparo_fecha_quando_sai():
    """O caso do 1416: entrega própria, CON chega com o pedido em preparo."""
    order = _order(Order.Status.PREPARING)
    with patch.object(ifood_events, "acknowledge", return_value=True) as ack:
        assert ifood_events.process_events([_event("CON", "con-1416")])["ingested"] == 1
    ack.assert_called_once_with(["con-1416"])
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING  # a custódia do entregador não é pulada

    _operator_moves(order, Order.Status.READY)
    _operator_moves(order, Order.Status.DISPATCHED)

    assert order.status == Order.Status.COMPLETED
    # Nenhum aviso de progresso saiu para um pedido que o iFood já encerrou.
    assert not _callbacks_for("ready", "dispatched").exists()


def test_entregador_do_ifood_retira_antes_de_a_cozinha_marcar_pronto():
    """Logística do iFood: DSP chega com o pedido em preparo. Quando a cozinha
    marca "Pronto", o pedido sai sozinho (o fato já dizia), sem ecoar despacho."""
    order = _order(Order.Status.PREPARING, delivered_by="IFOOD")
    with patch.object(ifood_events, "acknowledge", return_value=True):
        assert ifood_events.process_events([_event("DSP", "dsp-1")])["ingested"] == 1
    order.refresh_from_db()
    assert order.status == Order.Status.PREPARING

    _operator_moves(order, Order.Status.READY)

    assert order.status == Order.Status.DISPATCHED
    actors = list(order.events.filter(type="status_changed").values_list("actor", flat=True))
    assert actors[-1] == "system:ifood:DSP"
    assert not _callbacks_for("dispatched").exists()


def test_retirada_adiantada_e_concluida_fecha_a_cadeia_inteira():
    """DSP e CON gravados com a cozinha atrasada: marcar "Pronto" fecha tudo."""
    order = _order(Order.Status.PREPARING, delivered_by="IFOOD")
    with patch.object(ifood_events, "acknowledge", return_value=True):
        ifood_events.process_events([_event("DSP", "dsp-1"), _event("CON", "con-1")])

    _operator_moves(order, Order.Status.READY)

    assert order.status == Order.Status.COMPLETED


def test_eventos_fora_de_ordem_sao_aplicados_na_ordem_em_que_aconteceram():
    """A API entrega fora de ordem; a doc manda ordenar por createdAt. O CON que
    chega primeiro no lote, mas aconteceu depois, não pode esperar o DSP."""
    order = _order(Order.Status.READY, delivered_by="IFOOD")
    batch = [
        _event("CON", "con-1", created_at="2026-09-21T14:55:00.000Z"),
        _event("DSP", "dsp-1", created_at="2026-09-21T14:54:00.000Z"),
    ]
    with patch.object(ifood_events, "acknowledge", return_value=True) as ack:
        summary = ifood_events.process_events(batch)
    assert summary["failed"] == 0
    ack.assert_called_once()
    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED


def test_operador_sem_fato_do_ifood_nao_dispara_reconciliacao():
    """Pedido sem nenhum fato remoto segue o fluxo normal, com o aviso de sempre."""
    order = _order(Order.Status.ACCEPTED)
    with override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store", "client_id": "x"}):
        _operator_moves(order, Order.Status.PREPARING)
    assert order.status == Order.Status.PREPARING
    assert _callbacks_for("preparing").exists()


# ── A linha do card ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status,facts,expected", [
    ("preparing", {"remote_concluded": {"event_id": "c"}}, "Concluído no iFood · Finalize aqui"),
    ("ready", {"remote_concluded": {"event_id": "c"}}, "Concluído no iFood · Finalize aqui"),
    ("preparing", {"remote_dispatched": {"event_id": "d"}}, "Retirado pelo entregador do iFood · Marque Pronto"),
    ("dispatched", {"remote_dispatched": {"event_id": "d"}}, ""),   # local já alcançou
    ("completed", {"remote_concluded": {"event_id": "c"}}, ""),     # terminal não pede nada
    ("preparing", {}, ""),                                          # caso normal: nada
])
def test_card_diz_quando_o_ifood_esta_a_frente(status, facts, expected):
    from types import SimpleNamespace

    from shopman.backstage.projections.ifood import remote_ahead_label

    order = SimpleNamespace(channel_ref="ifood", status=status, data={"ifood": facts})
    assert remote_ahead_label(order) == expected
