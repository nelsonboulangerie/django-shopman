"""A custódia que sai com o entregador da TaOn, registrada no "Chamar entregador".

A confirmação da chamada leva o troco da gaveta e a maquininha da casa quando a
cobrança na porta pede, pelas mesmas peças do despacho do Gestor. A coleta (E)
depois não lança nada de novo, e "Entregador voltou" fecha o acerto. Pedido pago
não pergunta nada. Só o adapter mock: nenhuma corrida de verdade.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from shopman.cashman import Entry
from shopman.cashman import services as cash
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.backstage.models import DeliveryDevice
from shopman.backstage.services.delivery_devices import PREFIX
from shopman.backstage.tests._order_intent import context_payload
from shopman.shop.adapters import courier_mock
from shopman.shop.directives import COURIER_DISPATCH
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.models import Channel, Shop
from shopman.shop.services import courier, operator_orders

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("_mock_courier")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"


@pytest.fixture
def _mock_courier():
    courier_mock.reset()
    cache.clear()
    with override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER):
        yield
    courier_mock.reset()


@pytest.fixture
def operator(client):
    Shop.objects.create(name="Loja", route="Rua da Loja", street_number="10", city="Londrina", state_code="PR",
        latitude=-23.34, longitude=-51.15)
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


def _order(ref, *, method="credit", total_q=3800, change_for_q=None, collection="on_delivery"):
    payment = {"method": method, "collection": collection}
    if change_for_q:
        payment["change_for_q"] = change_for_q
    order = Order.objects.create(ref=ref, channel_ref="web", status="ready", total_q=total_q, data={
        "customer": {"name": "Ana", "phone": "5543999990000"}, "fulfillment_type": "delivery", "payment": payment,
        "delivery_address_structured": {"route": "Rua das Flores", "street_number": "123", "city": "Londrina",
            "state_code": "PR", "formatted_address": "Rua das Flores 123", "latitude": -23.31, "longitude": -51.16}})
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=total_q, line_total_q=total_q)
    return order


def _detail(client, ref):
    return client.get(reverse("api-backstage-order-detail", args=[ref])).json()["order"]


def _call(client, ref, **body):
    return client.post(reverse("api-backstage-order-courier-dispatch", args=[ref]),
        context_payload(client, ref, "courier-dispatch", **body), content_type="application/json")


def _collect(ref):
    """A TaOn aceita e coleta (mock): o worker abre a corrida e o E chega."""
    order = Order.objects.get(ref=ref)
    CourierDispatchHandler().handle(message=Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=ref).latest("pk"), ctx={})
    order.refresh_from_db()
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    return order


def test_chamar_com_troco_leva_da_gaveta_e_a_coleta_nao_duplica(client, operator):
    _order("DLV-0418", method="cash", total_q=7400, change_for_q=10000)
    assert _detail(client, "DLV-0418")["courier"]["custody"] == {
        "change_out_suggested_q": 2600, "needs_machine": False, "recorded": False}

    # Sem dizer o troco: o servidor pergunta, nada sai da gaveta, nenhuma corrida.
    response = _call(client, "DLV-0418")
    assert response.status_code == 400
    assert response.json()["code"] == "change_out_required"
    assert not Directive.objects.filter(topic=COURIER_DISPATCH).exists()
    assert not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).exists()

    assert _call(client, "DLV-0418", change_out="26,00").status_code == 200
    line = Entry.objects.get(kind=Entry.Kind.COURIER_OUT, order_ref="DLV-0418")
    assert (line.amount_q, line.shift_id) == (-2600, operator.test_shift.pk)
    order = Order.objects.get(ref="DLV-0418")
    assert order.status == "ready"
    assert order.data["dispatch"]["collector"] == "courier_partner"
    assert _detail(client, "DLV-0418")["courier"]["custody"]["recorded"] is True

    order = _collect("DLV-0418")
    courier.apply_status(order, "E", source="poll")  # o fato repetido
    assert order.status == "dispatched"
    assert Entry.objects.filter(kind=Entry.Kind.COURIER_OUT, order_ref="DLV-0418").count() == 1

    # "Entregador voltou" fecha o acerto: venda + o troco de volta.
    response = client.post(reverse("api-backstage-order-courier-back", args=["DLV-0418"]),
        context_payload(client, "DLV-0418", "courier-back"), content_type="application/json")
    assert response.status_code == 200, response.json()
    order.refresh_from_db()
    assert order.data["payment"]["cod_settled_at"]
    assert operator_orders.courier_change(order).back_q == 2600


def test_chamar_com_cartao_reserva_a_maquininha_e_a_volta_libera(client, operator, machines):
    azul, _ = machines
    _order("DLV-0415")
    assert _detail(client, "DLV-0415")["courier"]["custody"]["needs_machine"] is True

    response = _call(client, "DLV-0415", equipment=[PREFIX + str(azul.ref)])
    assert response.status_code == 200, response.json()
    azul.refresh_from_db()
    order = Order.objects.get(ref="DLV-0415")
    assert azul.current_order_id == order.pk
    assert order.data["dispatch"]["device_label"] == "Azul"

    order = _collect("DLV-0415")
    assert order.status == "dispatched"
    azul.refresh_from_db()
    assert azul.current_order_id == order.pk  # a coleta não troca nem duplica a reserva

    response = client.post(reverse("api-backstage-order-courier-back", args=["DLV-0415"]),
        context_payload(client, "DLV-0415", "courier-back"), content_type="application/json")
    assert response.status_code == 200, response.json()
    azul.refresh_from_db()
    assert azul.current_order_id is None


def test_chamar_de_novo_depois_de_corrida_nao_aceita_nao_lanca_outra_vez(client, operator):
    _order("DLV-0420", method="cash", total_q=7400, change_for_q=10000)
    assert _call(client, "DLV-0420", change_out="26,00").status_code == 200
    order = _collect_not_attended("DLV-0420")
    assert _call(client, "DLV-0420").status_code == 200  # nada a perguntar: a custódia já saiu
    assert Entry.objects.filter(kind=Entry.Kind.COURIER_OUT, order_ref=order.ref).count() == 1


def _collect_not_attended(ref):
    order = Order.objects.get(ref=ref)
    CourierDispatchHandler().handle(message=Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=ref).latest("pk"), ctx={})
    order.refresh_from_db()
    courier.apply_status(order, "N", source="poll")
    order.refresh_from_db()
    return order


def test_pedido_pago_nao_pergunta_nada(client, operator):
    _order("DLV-0430", method="pix", collection="")
    assert _detail(client, "DLV-0430")["courier"]["custody"] == {
        "change_out_suggested_q": 0, "needs_machine": False, "recorded": False}
    assert _call(client, "DLV-0430").status_code == 200
    order = Order.objects.get(ref="DLV-0430")
    assert "dispatch" not in order.data
    assert not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).exists()


def test_corrida_recusada_nao_tira_nada_da_gaveta(client, operator):
    _order("DLV-0440", method="cash", total_q=7400, change_for_q=10000)
    Order.objects.filter(ref="DLV-0440").update(channel_ref="ifood",
        data={**Order.objects.get(ref="DLV-0440").data, "ifood": {"delivered_by": "IFOOD"}})
    from shopman.backstage.services import orders as orders_service
    from shopman.backstage.services.exceptions import OrderError

    with pytest.raises(OrderError, match="iFood"):
        orders_service.courier_dispatch(Order.objects.get(ref="DLV-0440"), actor="marina",
            operator=operator, change_out_raw="26,00")
    assert not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).exists()
