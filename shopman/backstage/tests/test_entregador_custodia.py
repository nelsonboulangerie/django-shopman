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


def _open_ride(ref):
    order = Order.objects.get(ref=ref)
    CourierDispatchHandler().handle(message=Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=ref).latest("pk"), ctx={})
    order.refresh_from_db()
    return order


def _ride_ends(ref, status, *, source="poll"):
    order = _open_ride(ref)
    courier.apply_status(order, status, source=source)
    order.refresh_from_db()
    return order


def _returns(order):
    return Entry.objects.filter(kind=Entry.Kind.COURIER_IN, order_ref=order.ref, payload__custody_return=True)


def _assert_returned_once(order, *, change_q, device=None):
    order.refresh_from_db()
    assert [e.amount_q for e in _returns(order)] == ([change_q] if change_q else [])
    assert not operator_orders.courier_change(order).pending
    assert "custody_at" not in order.data["dispatch"]
    assert len(order.data["dispatch"]["custody_returns"]) == 1
    assert order.events.filter(type="partner_custody_returned").count() == 1
    if device is not None:
        device.refresh_from_db()
        assert device.current_order_id is None


@pytest.mark.parametrize("status", ["N", "C"])
def test_corrida_sem_coleta_devolve_troco_e_maquininha_uma_vez(client, operator, machines, status):
    azul, _ = machines
    _order("DLV-0420", method="mixed", total_q=7400, change_for_q=10000)
    Order.objects.filter(ref="DLV-0420").update(data={**Order.objects.get(ref="DLV-0420").data, "payment": {
        "method": "mixed", "collection": "on_delivery", "change_for_q": 5000,
        "tenders": [{"method": "cash", "amount_q": 3400}, {"method": "credit", "amount_q": 4000}]}})
    response = _call(client, "DLV-0420", change_out="16,00", equipment=[PREFIX + str(azul.ref)])
    assert response.status_code == 200, response.json()
    balance_after_call = cash.balance(operator.test_shift)

    order = _ride_ends("DLV-0420", status, source="webhook")
    courier.apply_status(order, status, source="poll")  # o fato repetido
    operator_orders.return_partner_custody(order, actor="teste", reason="replay")  # chamada direta repetida
    _assert_returned_once(order, change_q=1600, device=azul)
    assert cash.balance(operator.test_shift) == balance_after_call + 1600
    labels = [e["label"] for e in _detail(client, "DLV-0420")["timeline"]]
    assert "A corrida não coletou: o que ia com o entregador voltou" in labels

    # A chamada seguinte pergunta e registra de novo, sem herdar nem duplicar.
    assert _detail(client, "DLV-0420")["courier"]["custody"]["recorded"] is False
    assert _call(client, "DLV-0420", change_out="16,00", equipment=[PREFIX + str(azul.ref)]).status_code == 200
    order.refresh_from_db()
    change = operator_orders.courier_change(order)
    assert (change.out_q, change.back_q, change.pending) == (1600, None, True)
    azul.refresh_from_db()
    assert azul.current_order_id == order.pk


def test_pedido_cancelado_antes_da_coleta_devolve_pela_corrida_cancelada(client, operator):
    from shopman.shop.directives import COURIER_CANCEL
    from shopman.shop.handlers.courier_cancel import CourierCancelHandler
    from shopman.shop.lifecycle import dispatch

    _order("DLV-0450", method="cash", total_q=7400, change_for_q=10000)
    assert _call(client, "DLV-0450", change_out="26,00").status_code == 200
    order = _open_ride("DLV-0450")
    courier.apply_status(order, "A", source="poll")
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    order.refresh_from_db()
    dispatch(order, "on_cancelled")
    assert not _returns(order).exists()  # a corrida ainda está aberta: volta quando ela cancelar
    CourierCancelHandler().handle(message=Directive.objects.get(topic=COURIER_CANCEL), ctx={})
    _assert_returned_once(order, change_q=2600)


def test_pedido_cancelado_sem_corrida_aberta_devolve_na_hora(client, operator):
    from shopman.shop.lifecycle import dispatch

    _order("DLV-0460", method="cash", total_q=7400, change_for_q=10000)
    assert _call(client, "DLV-0460", change_out="26,00").status_code == 200
    order = Order.objects.get(ref="DLV-0460")  # a chamada ainda na fila: a central nunca soube
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    order.refresh_from_db()
    dispatch(order, "on_cancelled")
    courier.on_order_cancelled(order)  # replay da fase
    _assert_returned_once(order, change_q=2600)


def test_coletado_nao_devolve_nada(client, operator):
    _order("DLV-0470", method="cash", total_q=7400, change_for_q=10000)
    assert _call(client, "DLV-0470", change_out="26,00").status_code == 200
    order = _collect("DLV-0470")
    courier.apply_status(order, "C", source="webhook")
    order.refresh_from_db()
    assert not _returns(order).exists()
    assert operator_orders.courier_change(order).pending


def test_chamar_de_novo_leva_a_mesma_custodia_sem_duplicar(client, operator):
    """"Chamar de novo" libera a tentativa e chama no mesmo gesto: o troco segue separado."""
    _order("DLV-0480", method="cash", total_q=7400, change_for_q=10000)
    assert _call(client, "DLV-0480", change_out="26,00").status_code == 200
    task = Directive.objects.get(topic=COURIER_DISPATCH, payload__order_ref="DLV-0480")
    task.payload = {**task.payload, "dispatch_attempt": {"state": "unknown"}}
    task.save(update_fields=["payload"])
    order = Order.objects.get(ref="DLV-0480")
    courier.release_unresolved_dispatch(order, actor="marina")
    order.refresh_from_db()
    assert not _returns(order).exists()
    assert Entry.objects.filter(kind=Entry.Kind.COURIER_OUT, order_ref=order.ref).count() == 1
    assert order.data["dispatch"]["custody_at"]


def test_turno_do_troco_fechado_avisa_e_a_maquininha_volta(client, operator, machines):
    from shopman.backstage.models import OperatorAlert

    azul, _ = machines
    _order("DLV-0490", method="mixed", total_q=7400)
    Order.objects.filter(ref="DLV-0490").update(data={**Order.objects.get(ref="DLV-0490").data, "payment": {
        "method": "mixed", "collection": "on_delivery", "change_for_q": 5000,
        "tenders": [{"method": "cash", "amount_q": 3400}, {"method": "credit", "amount_q": 4000}]}})
    assert _call(client, "DLV-0490", change_out="16,00", equipment=[PREFIX + str(azul.ref)]).status_code == 200
    cash.close_shift(operator.test_shift, counted_q=cash.balance(operator.test_shift), actor=operator)
    order = _ride_ends("DLV-0490", "N")
    assert not _returns(order).exists()
    alert = OperatorAlert.objects.get(order_ref="DLV-0490", type="integration_failed")
    assert "R$ 16,00" in alert.message and "devolva o dinheiro pelo caixa" in alert.message
    azul.refresh_from_db()
    assert azul.current_order_id is None


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


# ── Uma corrida para vários pedidos: a corrida é uma saída ─────────────────


def _ride(client, refs, **body):
    return client.post(reverse("api-backstage-order-courier-ride"), {"refs": refs, **body},
        content_type="application/json")


def test_corrida_conjunta_leva_troco_de_cada_pedido_e_uma_maquininha_so(client, operator, machines):
    _order("RIDE-A", method="credit")
    _order("RIDE-B", method="cash", total_q=7400, change_for_q=10000)
    _order("RIDE-C", method="debit")
    azul = machines[0]

    response = _ride(client, ["RIDE-A", "RIDE-B", "RIDE-C"],
        change_out={"RIDE-B": "26,00"}, machine=f"{PREFIX}{azul.ref}")
    assert response.status_code == 200, response.json()

    # Uma solicitação, que pede retorno: a maquininha e o dinheiro voltam à loja.
    CourierDispatchHandler().handle(message=Directive.objects.get(topic=COURIER_DISPATCH), ctx={})
    (ride,) = courier_mock.rides().values()
    assert ride["payload"]["retorno"] is True
    assert len(ride["payload"]["paradas"]) == 3

    # O troco sai da gaveta só pelo pedido que pede, no turno de quem chamou.
    (line,) = Entry.objects.filter(kind=Entry.Kind.COURIER_OUT)
    assert (line.order_ref, line.amount_q) == ("RIDE-B", -2600)
    # Uma maquininha para a corrida: o primeiro pedido de cartão a reserva, o
    # outro entra nela. Os três pedidos são a mesma saída.
    a, b, c = (Order.objects.get(ref=ref) for ref in ("RIDE-A", "RIDE-B", "RIDE-C"))
    azul.refresh_from_db()
    assert azul.current_order_id == a.pk
    assert a.data["dispatch"]["device_ref"] == c.data["dispatch"]["device_ref"] == str(azul.ref)
    assert "equipment" not in b.data["dispatch"]
    assert {operator_orders.trip_id(order) for order in (a, b, c)} == {"RIDE-A"}

    # A TaOn coleta: os três saem, sem lançar nada de novo.
    for order in (a, b, c):
        courier.apply_status(order, "E", source="webhook")
        order.refresh_from_db()
        assert order.status == "dispatched"
    assert Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).count() == 1

    # A maquininha volta uma vez, para os dois pedidos de cartão.
    operator_orders.mark_equipment_returned(c, actor="operator:marina")
    azul.refresh_from_db()
    assert azul.current_order_id is None
    for order in (a, c):
        order.refresh_from_db()
        assert operator_orders.equipment_custody(order).pending is False


def test_corrida_conjunta_sem_maquininha_ou_sem_troco_nao_chama_nem_tira_da_gaveta(client, operator, machines):
    _order("RIDE-A", method="credit")
    _order("RIDE-B", method="cash", total_q=7400, change_for_q=10000)

    response = _ride(client, ["RIDE-A", "RIDE-B"], change_out={"RIDE-B": "26,00"})
    assert response.status_code == 409
    assert "Pedido A" in response.json()["detail"]

    response = _ride(client, ["RIDE-A", "RIDE-B"], machine=f"{PREFIX}{machines[0].ref}")
    assert response.status_code == 409
    assert response.json()["code"] == "change_out_required"
    assert "O pedido B pede troco" in response.json()["detail"]

    assert not Directive.objects.filter(topic=COURIER_DISPATCH).exists()
    assert not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).exists()
    machines[0].refresh_from_db()
    assert machines[0].current_order_id is None


def test_fila_diz_o_que_cada_entrega_da_corrida_pergunta(client, operator):
    _order("RIDE-A", method="credit")
    _order("RIDE-B", method="cash", total_q=7400, change_for_q=10000)
    queue = client.get(reverse("api-backstage-orders")).json()["queue"]
    asks = [(row["ref"], row["change_out_suggested_q"], row["needs_machine"], row["stage"])
            for row in queue["ride_candidates"]]
    assert asks == [("RIDE-A", 0, True, "Pronto"), ("RIDE-B", 2600, False, "Pronto")]
    assert queue["ride_candidates"][0]["label"] == "Pedido A · Ana"


def test_chamar_entregador_oferece_quem_pode_ir_junto_o_mais_perto_primeiro(client, operator):
    _order("RIDE-A", method="pix", collection="")
    near = _order("RIDE-B", method="cash", total_q=7400, change_for_q=10000)
    far = _order("RIDE-C", method="pix", collection="")
    far.status = "preparing"
    far.data = {**far.data, "delivery_address_structured": {**far.data["delivery_address_structured"],
        "neighborhood": "Gleba Palhano", "latitude": -23.40, "longitude": -51.20}}
    far.save(update_fields=["status", "data"])
    offer = _detail(client, "RIDE-A")["courier"]["ride_offer"]
    assert [row["ref"] for row in offer] == [near.ref, far.ref]
    assert offer[0]["distance_label"] == "a 0,0 km"
    assert (offer[1]["stage"], offer[1]["place"]) == ("Em preparo", "Gleba Palhano")
    assert offer[0]["change_out_suggested_q"] == 2600


# ── A corrida conjunta que não anda: a custódia volta, de todos ─────────────


def _ride_with_custody(client, machines):
    _order("RIDE-A", method="credit")
    _order("RIDE-B", method="cash", total_q=7400, change_for_q=10000)
    response = _ride(client, ["RIDE-A", "RIDE-B"], change_out={"RIDE-B": "26,00"},
        machine=f"{PREFIX}{machines[0].ref}")
    assert response.status_code == 200, response.json()
    return Directive.objects.get(topic=COURIER_DISPATCH)


def _cancel(ref):
    """O pedido cancelado (o lifecycle de cancelamento é de outro teste): só o status."""
    Order.objects.filter(ref=ref).update(status="cancelled")
    return Order.objects.get(ref=ref)


def _drawer_balance():
    return sum(entry.amount_q for entry in Entry.objects.filter(kind__in=[Entry.Kind.COURIER_OUT, Entry.Kind.COURIER_IN]))


def test_corrida_conjunta_nao_atendida_pela_leitura_devolve_a_custodia_de_todos(client, operator, machines):
    from shopman.shop.handlers.courier_sync import CourierSyncHandler

    CourierDispatchHandler().handle(message=_ride_with_custody(client, machines), ctx={})
    (ride_id,) = courier_mock.rides()
    courier_mock.set_status(ride_id, "N")
    CourierSyncHandler().handle(message=Directive.objects.filter(topic="courier.sync").latest("pk"), ctx={})

    for ref in ("RIDE-A", "RIDE-B"):
        order = Order.objects.get(ref=ref)
        assert not courier.has_active_ride(order)
        assert "trip_ref" not in (order.data.get("dispatch") or {})
    assert _drawer_balance() == 0
    machines[0].refresh_from_db()
    assert machines[0].current_order_id is None


def test_corrida_conjunta_que_falha_na_taon_devolve_a_custodia_e_avisa(client, operator, machines, monkeypatch):
    from shopman.orderman.exceptions import DirectiveTerminalError

    from shopman.backstage.models import OperatorAlert
    from shopman.shop.adapters.courier_machine import CourierError

    def refuse(payload):
        raise CourierError("[12] Parada fora da área", transient=False)

    monkeypatch.setattr(courier_mock, "dispatch", refuse)
    task = _ride_with_custody(client, machines)
    with pytest.raises(DirectiveTerminalError):
        CourierDispatchHandler().handle(message=task, ctx={})

    assert _drawer_balance() == 0
    machines[0].refresh_from_db()
    assert machines[0].current_order_id is None
    # A próxima chamada pergunta a custódia de novo, pedido a pedido.
    assert operator_orders.partner_custody_asks(Order.objects.get(ref="RIDE-A"))["needs_machine"] is True
    assert set(OperatorAlert.objects.filter(type="courier_dispatch_failed").values_list("order_ref", flat=True)) == {
        "RIDE-A", "RIDE-B"}


def test_pedido_cancelado_antes_de_o_trabalho_rodar_nao_prende_a_custodia_do_outro(client, operator, machines):
    from shopman.backstage.models import OperatorAlert

    task = _ride_with_custody(client, machines)
    b = _cancel("RIDE-B")
    courier.on_order_cancelled(b)
    CourierDispatchHandler().handle(message=task, ctx={})

    assert not courier_mock.rides()
    assert _drawer_balance() == 0
    machines[0].refresh_from_db()
    assert machines[0].current_order_id is None
    assert OperatorAlert.objects.filter(type="courier_dispatch_failed", order_ref="RIDE-A").exists()


def test_pedido_cancelado_antes_da_coleta_devolve_o_troco_e_a_maquininha_segue_com_a_corrida(client, operator, machines):
    _order("RIDE-A", method="credit")
    _order("RIDE-B", method="cash", total_q=7400, change_for_q=10000)
    _order("RIDE-C", method="debit")
    assert _ride(client, ["RIDE-A", "RIDE-B", "RIDE-C"], change_out={"RIDE-B": "26,00"},
        machine=f"{PREFIX}{machines[0].ref}").status_code == 200
    CourierDispatchHandler().handle(message=Directive.objects.get(topic=COURIER_DISPATCH), ctx={})

    # B (o troco) e A (quem segura a maquininha) são cancelados antes da coleta.
    for ref in ("RIDE-B", "RIDE-A"):
        courier.on_order_cancelled(_cancel(ref))

    assert _drawer_balance() == 0
    machines[0].refresh_from_db()
    c = Order.objects.get(ref="RIDE-C")
    assert machines[0].current_order_id == c.pk
    assert operator_orders.equipment_custody(c).pending is True
    assert courier.has_active_ride(c)


def test_chamar_de_novo_uma_corrida_conjunta_chama_a_mesma_corrida(client, operator, machines):
    task = _ride_with_custody(client, machines)
    task.payload = {**task.payload, "dispatch_attempt": {"state": "unknown"}}
    task.status = "failed"
    task.save(update_fields=["payload", "status"])

    again = courier.release_unresolved_dispatch(Order.objects.get(ref="RIDE-A"), actor="operator:marina")
    assert again.payload["order_refs"] == ["RIDE-A", "RIDE-B"]
    # A custódia que já saiu segue a mesma: nada sai de novo da gaveta.
    assert Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).count() == 1


def test_maquininha_da_corrida_nunca_fica_com_o_pedido_em_dinheiro(client, operator, machines):
    _order("RIDE-B", method="cash", total_q=7400, change_for_q=10000)
    _order("RIDE-A", method="credit")
    assert _ride(client, ["RIDE-B", "RIDE-A"], change_out={"RIDE-B": "26,00"},
        machine=f"{PREFIX}{machines[0].ref}").status_code == 200
    machines[0].refresh_from_db()
    assert machines[0].current_order_id == Order.objects.get(ref="RIDE-A").pk
    assert "equipment" not in Order.objects.get(ref="RIDE-B").data["dispatch"]


def test_cotacao_da_corrida_conjunta_diz_valor_ordem_e_retorno(client, operator):
    _order("RIDE-A", method="credit")
    _order("RIDE-B", method="pix", collection="")
    url = reverse("api-backstage-order-courier-ride-quote")
    body = client.get(url, {"refs": ["RIDE-A", "RIDE-B"]}).json()["estimate"]
    assert body["display"] == "R$ 16,50 · 24 min · 5,7 km · ida e volta"
    assert body["route"] == "A → B"
    assert client.get(url, {"refs": ["RIDE-A"]}).status_code == 400
