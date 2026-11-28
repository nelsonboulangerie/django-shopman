"""A Via Pedido no Gestor (P2-19 do mapa de cenários de pedido).

O Gestor imprime a mesma Via Pedido do PDV, pela mesma rota
(``api-backstage-order-ticket-escpos``) e pela impressora da estação. O quadro já
recebia ``device_agent``; o detalhe do pedido também precisa recebê-lo, senão o
"Imprimir Via Pedido" do detalhe não teria por onde sair.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Shop

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]


@pytest.fixture
def gestor(db):
    Shop.objects.create(name="Nelson Boulangerie")
    user = User.objects.create_user("gestor-via", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"),
            codename="manage_orders",
        )
    )
    return user


@pytest.fixture
def pedido(db):
    order = Order.objects.create(
        ref="WEB-19", channel_ref="web", status=Order.Status.NEW, total_q=1800,
        data={"customer": {"name": "Ana"}, "fulfillment_type": "pickup"},
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=1800, line_total_q=1800,
    )
    return order


def test_o_detalhe_do_pedido_diz_se_esta_estacao_imprime(client, gestor, pedido):
    client.force_login(gestor)
    response = client.get(reverse("api-backstage-order-detail", args=[pedido.ref]))
    assert response.status_code == 200
    agent = response.json()["device_agent"]
    # Sem estação confiável não há impressora: o bloco diz que não imprime e por quê.
    assert agent["can_print"] is False
    assert agent["reason"]


def test_o_gestor_imprime_a_via_pedido_pela_rota_do_pdv(client, gestor, pedido):
    client.force_login(gestor)
    first = client.post(reverse("api-backstage-order-ticket-escpos", args=[pedido.ref]))
    second = client.post(reverse("api-backstage-order-ticket-escpos", args=[pedido.ref]))
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["payload_b64"]
    assert first.json()["reprint"] is False
    assert second.json()["reprint"] is True
