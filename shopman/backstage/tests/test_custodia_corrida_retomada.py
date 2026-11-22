""""Separar de novo": a custódia da corrida que a TaOn retomou (#2500).

A chamada registra o troco e a maquininha; o encerramento sem coleta (N ou C) os
devolve à casa. Quando a TaOn retoma a corrida encerrada, ela volta viva SEM a
custódia: o pedido diz o que separar, e o gesto ``courier-custody`` registra pelas
mesmas peças da chamada. Só o adapter mock: nenhuma corrida de verdade.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from shopman.cashman import Entry
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services.delivery_devices import PREFIX
from shopman.backstage.tests._order_intent import context_payload
from shopman.backstage.tests.test_entregador_custodia import (  # noqa: F401 (fixtures)
    _call,
    _detail,
    _mock_courier,
    _order,
    machines,
    operator,
)
from shopman.shop.directives import COURIER_DISPATCH
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.services import courier

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_mock_courier")]


def _open_then_resume(ref):
    """Chamada aberta na TaOn, encerrada sem ninguém (N) e retomada pela central."""
    order = Order.objects.get(ref=ref)
    task = Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=ref).latest("pk")
    CourierDispatchHandler().handle(message=task, ctx={})
    Directive.objects.filter(pk=task.pk).update(status=Directive.Status.DONE)
    order.refresh_from_db()
    ride = courier.get_block(order)["ride_ref"]
    courier.apply_status(order, "N", source="webhook")
    order.refresh_from_db()
    assert courier.restore_archived_ride(order, ride, source="webhook") == "restored"
    order.refresh_from_db()
    return order


def _separate(client, ref, **body):
    return client.post(reverse("api-backstage-order-courier-custody", args=[ref]),
        context_payload(client, ref, "courier-custody", **body), content_type="application/json")


def _action(detail, ref="courier-custody"):
    return next(action for action in detail["actions"] if action["ref"] == ref)


def test_a_chamada_normal_nao_pede_para_separar(client, operator):
    _order("DLV-0501", method="cash", total_q=7400, change_for_q=10000)
    assert _call(client, "DLV-0501", change_out="26,00").status_code == 200
    detail = _detail(client, "DLV-0501")
    assert detail["courier"]["custody_to_separate"] is None
    assert _action(detail)["enabled"] is False


def test_corrida_retomada_pede_o_troco_de_novo_e_separa_uma_vez(client, operator):
    _order("DLV-0502", method="cash", total_q=7400, change_for_q=10000)
    assert _call(client, "DLV-0502", change_out="26,00").status_code == 200
    order = _open_then_resume("DLV-0502")
    # O encerramento devolveu o troco à gaveta: saiu e voltou.
    assert sum(e.amount_q for e in Entry.objects.filter(order_ref=order.ref)) == 0

    detail = _detail(client, order.ref)
    assert detail["courier"]["custody_to_separate"] == {"change_out_suggested_q": 2600, "needs_machine": False}
    assert _action(detail)["enabled"] is True
    alert = OperatorAlert.objects.get(type="integration_failed", order_ref=order.ref)
    assert "O troco voltou para a casa: separe de novo no pedido antes de entregar a sacola." in alert.message

    # Sem dizer o troco, o servidor pergunta e nada sai da gaveta.
    response = _separate(client, order.ref)
    assert response.status_code == 400
    assert response.json()["code"] == "change_out_required"

    assert _separate(client, order.ref, change_out="26,00").status_code == 200
    outs = Entry.objects.filter(kind=Entry.Kind.COURIER_OUT, order_ref=order.ref).order_by("pk")
    assert [entry.amount_q for entry in outs] == [-2600, -2600]
    detail = _detail(client, order.ref)
    assert detail["courier"]["custody_to_separate"] is None
    assert detail["courier"]["custody"]["recorded"] is True
    assert _action(detail)["enabled"] is False
    assert order.events.filter(type="courier_custody_separated").count() == 1

    # Repetir não tira da gaveta de novo: a corrida já não pede nada.
    assert _separate(client, order.ref, change_out="26,00").status_code == 400
    assert Entry.objects.filter(kind=Entry.Kind.COURIER_OUT, order_ref=order.ref).count() == 2


def test_corrida_retomada_no_cartao_reserva_a_maquininha_de_novo(client, operator, machines):
    azul, _ = machines
    _order("DLV-0503", method="credit")
    assert _call(client, "DLV-0503", equipment=[PREFIX + str(azul.ref)]).status_code == 200
    order = _open_then_resume("DLV-0503")
    assert not (order.data.get("dispatch") or {}).get("device_ref")  # a maquininha voltou
    detail = _detail(client, order.ref)
    assert detail["courier"]["custody_to_separate"] == {"change_out_suggested_q": 0, "needs_machine": True}
    alert = OperatorAlert.objects.get(type="integration_failed", order_ref=order.ref)
    assert "A maquininha voltou para a casa" in alert.message

    assert _separate(client, order.ref, equipment=[PREFIX + str(azul.ref)]).status_code == 200
    order.refresh_from_db()
    assert order.data["dispatch"]["device_ref"]
    assert _detail(client, order.ref)["courier"]["custody_to_separate"] is None


def test_depois_da_coleta_nao_se_separa(client, operator):
    _order("DLV-0504", method="cash", total_q=7400, change_for_q=10000)
    assert _call(client, "DLV-0504", change_out="26,00").status_code == 200
    order = _open_then_resume("DLV-0504")
    # Sem separar, a TaOn diz que coletou: o gesto some (a sacola já saiu).
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    assert courier.custody_to_separate(order) is None
    assert _action(_detail(client, order.ref))["enabled"] is False
