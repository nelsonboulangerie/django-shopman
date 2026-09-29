"""A maquininha embutida nos dois gestos do Gestor: a saída e a volta.

"Saiu com a maquininha" (o sistema escolhe a livre; vários pedidos na mesma
saída compartilham UMA) e "Entregador voltou" (fecha a saída inteira: entrega,
dinheiro, troco e maquininha). Sem indicador fixo: só alerta quando passa do tempo.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from shopman.cashman import services as cash
from shopman.orderman.models import Order, OrderItem

from shopman.backstage.models import DeliveryDevice, OperatorAlert
from shopman.backstage.services.delivery_devices import PREFIX
from shopman.backstage.tests._order_intent import advance_payload, context_payload
from shopman.shop.models import Channel, Shop
from shopman.shop.services import operator_orders

pytestmark = pytest.mark.django_db


@pytest.fixture
def operator(client):
    Shop.objects.create(name="Loja")
    Channel.objects.create(ref="web", name="Loja", is_active=True, config={"fulfillment": {"equipment": ["card_machine"]}})
    user = User.objects.create_user("marina", password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders"))
    client.force_login(user)
    user.test_shift = cash.open_shift(operator=user, float_q=10000)
    return user


@pytest.fixture
def machines(db):
    return (DeliveryDevice.objects.create(label="Azul", identification="AZ"),
            DeliveryDevice.objects.create(label="Preta", identification="PR"))


def _order(ref, *, method="credit", total_q=3800, change_for_q=None, status="ready"):
    payment = {"method": method, "collection": "on_delivery"}
    if change_for_q:
        payment["change_for_q"] = change_for_q
    order = Order.objects.create(ref=ref, channel_ref="web", status=status, total_q=total_q, data={
        "customer": {"name": "Ana"}, "fulfillment_type": "delivery", "payment": payment})
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=total_q, line_total_q=total_q)
    return order


def _action(client, ref, action):
    detail = client.get(reverse("api-backstage-order-detail", args=[ref])).json()["order"]
    return next((a for a in detail["actions"] if a["ref"] == action), None)


def _card(client, ref):
    queue = client.get(reverse("api-backstage-orders")).json()["queue"]
    for zone in queue.values():
        for card in zone if isinstance(zone, list) else []:
            if isinstance(card, dict) and card.get("ref") == ref:
                return card
    raise AssertionError(ref)


def _dispatch(client, ref, **body):
    return client.post(reverse("api-backstage-order-advance", args=[ref]), advance_payload(client, ref, **body), content_type="application/json")


def test_botao_de_saida_diz_a_maquininha_so_quando_o_pagamento_na_porta_pede(client, operator, machines):
    _order("DLV-CARD")
    _order("DLV-CASH", method="cash")
    assert _action(client, "DLV-CARD", "advance")["label"] == "Saiu com a maquininha"
    assert _action(client, "DLV-CASH", "advance")["label"] == "Marcar saída para entrega"
    card = _card(client, "DLV-CARD")
    assert card["dispatch_needs_machine"] is True
    assert _card(client, "DLV-CASH")["dispatch_needs_machine"] is False


def test_sem_maquininha_livre_o_botao_continua_vivo_e_o_dialogo_sabe_onde_ela_esta(client, operator, machines):
    azul, preta = machines
    preta.active = False
    preta.save()
    first, _ = _order("DLV-0415"), _order("DLV-0418")
    assert _dispatch(client, "DLV-0415", equipment=[PREFIX + str(azul.ref)]).status_code == 200
    action = _action(client, "DLV-0418", "advance")
    assert (action["label"], action["enabled"]) == ("Saiu com a maquininha", True)
    options = _card(client, "DLV-0418")["equipment_options"]
    assert [(o["label"], o["enabled"], o["order_ref"], o["reason"]) for o in options] == [
        ("Azul", False, "DLV-0415", "Na rua com o pedido 0415")]
    # O KDS, que não tem o diálogo, continua barrado.
    assert operator_orders.advance_block(Order.objects.get(ref="DLV-0418")) == operator_orders.AdvanceBlock.DEVICE_UNAVAILABLE
    # E o servidor não deixa sair sem maquininha.
    assert _dispatch(client, "DLV-0418").status_code == 400
    first.refresh_from_db()
    assert first.status == "dispatched"


def test_dois_pedidos_na_mesma_saida_compartilham_uma_maquininha(client, operator, machines):
    azul, preta = machines
    _order("DLV-0415")
    _order("DLV-0418")
    assert _dispatch(client, "DLV-0415", equipment=[PREFIX + str(azul.ref)]).status_code == 200
    # O segundo entra na saída do primeiro: sem escolher maquininha, leva a mesma.
    response = _dispatch(client, "DLV-0418", trip_ref="DLV-0415")
    assert response.status_code == 200, response.json()
    second = Order.objects.get(ref="DLV-0418")
    assert second.data["dispatch"]["trip_ref"] == "DLV-0415"
    assert second.data["dispatch"]["device_ref"] == str(azul.ref)
    azul.refresh_from_db()
    preta.refresh_from_db()
    assert azul.current_order.ref == "DLV-0415"
    assert preta.current_order_id is None  # a Preta continua livre
    card = _card(client, "DLV-0418")
    assert card["equipment_label"] == "Saiu com a maquininha Azul"
    assert card["trip_with"] == ["DLV-0415"]
    assert card["courier_return_orders"] == ["DLV-0415", "DLV-0418"]


def test_entregador_voltou_fecha_a_saida_inteira_e_diz_o_que_confere(client, operator, machines):
    azul, _ = machines
    _order("DLV-0415")  # cartão, R$ 38
    _order("DLV-0418", method="cash", total_q=7400, change_for_q=10000)  # dinheiro, troco de R$ 26
    assert _dispatch(client, "DLV-0415", equipment=[PREFIX + str(azul.ref)]).status_code == 200
    assert _dispatch(client, "DLV-0418", trip_ref="DLV-0415", change_out="26,00").status_code == 200

    card = _card(client, "DLV-0418")
    assert card["courier_return_lines"] == ["Maquininha Azul", "R$ 100,00 em dinheiro: R$ 74,00 do pedido 0418 + R$ 26,00 de troco"]
    back = _action(client, "DLV-0418", "courier-back")
    assert (back["label"], back["enabled"]) == ("Entregador voltou", True)

    # Um gesto, em qualquer pedido da saída, fecha os dois.
    response = client.post(reverse("api-backstage-order-courier-back", args=["DLV-0418"]),
        context_payload(client, "DLV-0418", "courier-back"), content_type="application/json")
    assert response.status_code == 200, response.json()
    assert sorted(response.json()["closed"]) == ["DLV-0415", "DLV-0418"]
    for ref in ("DLV-0415", "DLV-0418"):
        order = Order.objects.get(ref=ref)
        assert order.status == "completed"
        assert order.data["payment"]["cod_settled_at"]
        assert order.data["dispatch"]["courier_back_at"]
    # A maquininha saiu no pedido de cartão; o de dinheiro não a levou.
    assert Order.objects.get(ref="DLV-0415").data["dispatch"]["equipment_back_at"]
    assert "equipment" not in Order.objects.get(ref="DLV-0418").data["dispatch"]
    azul.refresh_from_db()
    assert azul.current_order_id is None
    assert operator_orders.courier_change(Order.objects.get(ref="DLV-0418")).back_q == 2600
    assert _action(client, "DLV-0418", "courier-back") is None


def test_registro_antigo_sem_maquininha_identificada_se_resolve_com_o_mesmo_gesto(client, operator):
    legacy = _order("DLV-NARUA", method="cash", total_q=7400, status="dispatched")
    legacy.data = {**legacy.data, "dispatch": {"equipment": ["card_machine"], "equipment_out_at": "2026-09-10T12:00:00+00:00"}}
    legacy.save(update_fields=["data"])
    card = _card(client, "DLV-NARUA")
    assert card["equipment_label"] == "Saiu com a maquininha"
    assert card["courier_return_lines"] == ["Maquininha", "R$ 74,00 em dinheiro"]
    response = client.post(reverse("api-backstage-order-courier-back", args=["DLV-NARUA"]),
        context_payload(client, "DLV-NARUA", "courier-back"), content_type="application/json")
    assert response.status_code == 200, response.json()
    legacy.refresh_from_db()
    assert legacy.status == "completed"
    assert legacy.data["dispatch"]["equipment_back_at"]


def test_pedido_pago_online_sem_nada_a_devolver_nao_ganha_o_gesto(client, operator):
    online = Order.objects.create(ref="DLV-PIX", channel_ref="web", status="dispatched", total_q=1000, data={
        "fulfillment_type": "delivery", "payment": {"method": "pix", "captured_at": "2026-09-22T10:00:00+00:00"}})
    assert _action(client, online.ref, "courier-back") is None


def test_maquininha_fora_alem_do_limite_vira_alerta_uma_vez(operator, machines):
    azul, _ = machines
    order = _order("DLV-0415")
    operator_orders.advance_order(order, actor="lab", equipment=[PREFIX + str(azul.ref)])
    call_command("check_card_machines_out")
    assert not OperatorAlert.objects.filter(type="card_machine_overdue").exists()
    order.refresh_from_db()
    order.data["dispatch"]["equipment_out_at"] = (timezone.now() - timedelta(minutes=125)).isoformat()
    order.save(update_fields=["data"])
    call_command("check_card_machines_out")
    call_command("check_card_machines_out")
    alerts = OperatorAlert.objects.filter(type="card_machine_overdue")
    assert [a.message for a in alerts] == ["Maquininha Azul fora há 2 h 5 min: pedido 0415"]
    assert alerts[0].audience == "orders"
    shop = Shop.load()
    shop.defaults = {**(shop.defaults or {}), "delivery": {"card_machine_alert_minutes": 0}}
    shop.save()
    alerts.delete()
    call_command("check_card_machines_out")
    assert not OperatorAlert.objects.filter(type="card_machine_overdue").exists()


def test_dois_pedidos_de_cartao_na_mesma_saida_devolvem_a_maquininha_juntos(client, operator, machines):
    azul, _ = machines
    _order("DLV-0415")
    _order("DLV-0418")
    assert _dispatch(client, "DLV-0415", equipment=[PREFIX + str(azul.ref)]).status_code == 200
    assert _dispatch(client, "DLV-0418", trip_ref="DLV-0415").status_code == 200
    # A volta pela ação avulsa, no pedido que COMPARTILHA, também fecha quem segura.
    response = client.post(reverse("api-backstage-order-equipment-back", args=["DLV-0418"]),
        context_payload(client, "DLV-0418", "equipment-back"), content_type="application/json")
    assert response.status_code == 200, response.json()
    azul.refresh_from_db()
    assert azul.current_order_id is None
    for ref in ("DLV-0415", "DLV-0418"):
        assert Order.objects.get(ref=ref).data["dispatch"]["equipment_back_at"]


def test_nao_entra_numa_saida_que_ja_voltou(client, operator, machines):
    azul, _ = machines
    first = _order("DLV-0415")
    _order("DLV-0418")
    assert _dispatch(client, "DLV-0415", equipment=[PREFIX + str(azul.ref)]).status_code == 200
    operator_orders.courier_returned(first, actor="marina", cash_shift=operator.test_shift)
    response = _dispatch(client, "DLV-0418", trip_ref="DLV-0415")
    assert response.status_code == 400
    assert "não está mais na rua" in response.json()["detail"]
