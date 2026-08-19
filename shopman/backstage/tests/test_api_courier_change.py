"""O troco da entrega no gestor de pedidos, pela API crua (WP-9 do CASHMAN-PLAN).

O contrato independe da superfície: é o servidor que exige o valor do troco no
despacho (409 ``change_out_required`` com a sugestão) e o que voltou no acerto;
o card do quadro carrega os campos que a tela usa para perguntar antes.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.cashman import Entry
from shopman.cashman import services as cash
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _no_active_operator(settings):
    settings.SHOPMAN_REQUIRE_ACTIVE_OPERATOR = False


@pytest.fixture
def operator():
    Shop.objects.create(name="Loja")
    user = User.objects.create_user("marina", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders"
        )
    )
    return user


def _delivery_cash_order(ref: str, *, change_for_q: int | None = None, status: str = "ready") -> Order:
    payment = {"method": "cash", "collection": "on_delivery", "amount_q": 3000}
    if change_for_q is not None:
        payment["change_for_q"] = change_for_q
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=status,
        total_q=3000,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "delivery", "payment": payment},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=3000, line_total_q=3000)
    return order


def _card(client, ref: str) -> dict:
    body = client.get(reverse("api-backstage-orders")).json()
    zones = body["queue"] if "queue" in body else body
    for zone in zones.values():
        if isinstance(zone, list):
            for card in zone:
                if isinstance(card, dict) and card.get("ref") == ref:
                    return card
    raise AssertionError(f"card {ref} não está no quadro: {list(zones)}")


def test_despacho_pergunta_o_troco_leva_da_gaveta_e_o_acerto_diz_o_que_voltou(client, operator):
    client.force_login(operator)
    shift = cash.open_shift(operator=operator, float_q=10000)
    order = _delivery_cash_order("DLV-1", change_for_q=5000)

    card = _card(client, "DLV-1")
    assert (card["change_for_q"], card["change_out_suggested_q"], card["change_out_q"]) == (5000, 2000, 0)
    assert card["change_label"] == "Cliente paga com R$ 50,00 · levar R$ 20,00 de troco"
    assert card["change_back_pending"] is False

    # Avançar sem dizer o troco: o servidor recusa com a sugestão.
    response = client.post(reverse("api-backstage-order-advance", args=["DLV-1"]))
    assert response.status_code == 409
    assert response.json()["code"] == "change_out_required"
    assert response.json()["suggested_q"] == 2000
    order.refresh_from_db()
    assert order.status == "ready"

    response = client.post(
        reverse("api-backstage-order-advance", args=["DLV-1"]), {"change_out": "20,00"}, content_type="application/json"
    )
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == "dispatched"
    line = Entry.objects.get(kind=Entry.Kind.COURIER_OUT, order_ref="DLV-1")
    assert (line.amount_q, line.shift_id, line.operator) == (-2000, shift.pk, operator)
    assert cash.balance(shift) == 8000

    card = _card(client, "DLV-1")
    assert (card["change_out_q"], card["change_back_pending"]) == (2000, True)
    assert card["change_label"] == "Entregador levou R$ 20,00 de troco"
    assert card["can_settle_delivery_cash"] is True

    # Acertar sem dizer quanto voltou: recusado.
    response = client.post(reverse("api-backstage-order-settle-delivery-cash", args=["DLV-1"]))
    assert response.status_code == 400
    assert "voltou" in response.json()["detail"]

    response = client.post(
        reverse("api-backstage-order-settle-delivery-cash", args=["DLV-1"]),
        {"change_back": "5,00"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["amount_q"] == 3000
    back = Entry.objects.get(kind=Entry.Kind.COURIER_IN, order_ref="DLV-1")
    assert (back.amount_q, back.parent_id) == (500, line.pk)
    assert cash.balance(shift) == 8000 + 3000 + 500

    card = _card(client, "DLV-1")
    assert (card["change_back_pending"], card["change_back_q"]) == (False, 500)
    assert card["change_label"] == "Voltou R$ 5,00 de troco"

    detail = client.get(reverse("api-backstage-order-detail", args=["DLV-1"])).json()["order"]
    assert detail["change_out_q"] == 2000 and detail["change_back_q"] == 500


def test_sem_pedido_de_troco_o_despacho_segue_direto_e_sem_turno_nao_leva(client, operator):
    client.force_login(operator)
    plain = _delivery_cash_order("DLV-2")
    assert _card(client, "DLV-2")["change_label"] == ""
    assert client.post(reverse("api-backstage-order-advance", args=["DLV-2"])).status_code == 200

    asks = _delivery_cash_order("DLV-3", change_for_q=5000)
    response = client.post(
        reverse("api-backstage-order-advance", args=["DLV-3"]), {"change_out": "20,00"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "turno" in response.json()["detail"]
    asks.refresh_from_db()
    assert asks.status == "ready"
    # "Levou sem troco" é resposta: zero despacha sem linha, mesmo sem turno.
    response = client.post(
        reverse("api-backstage-order-advance", args=["DLV-3"]), {"change_out": "0"}, content_type="application/json"
    )
    assert response.status_code == 200
    assert not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).exists()
    plain.refresh_from_db()
    assert plain.status == "dispatched"
