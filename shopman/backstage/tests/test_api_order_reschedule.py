"""POST /api/v1/backstage/orders/<ref>/reschedule/ — reagendar pela API do operador.

A regra mora em ``shop.services.reschedule`` (testada em ``shop/tests/test_reschedule.py``);
aqui só a porta: permissão ``shop.manage_orders``, intenção idempotente como as outras
ações de pedido, revisão da data lida e recusa no dialeto ``{detail, field, errors}``.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Channel, Shop
from shopman.shop.services.operator_orders import operational_revision

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(db):
    Channel.objects.create(ref="web", name="Loja", config={"payment": {"timing": "external", "method": "cash"}})
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(shop):
    user = User.objects.create_user("reschedule-op", password="pw", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders")
    )
    return user


@pytest.fixture
def plain_staff(shop):
    return User.objects.create_user("reschedule-plain", password="pw", is_staff=True)


def _day(offset: int):
    return timezone.localdate() + timedelta(days=offset)


@pytest.fixture
def order(shop):
    # Item fora do Stockman: sem reserva a mover — a porta é o que está em teste.
    order = Order.objects.create(
        ref="ORD-RESCHED-1", channel_ref="web", status="accepted", total_q=1500,
        data={"customer": {"name": "Ana"}, "payment": {"method": "cash"}, "fulfillment_type": "pickup",
              "delivery_date": _day(3).isoformat(), "delivery_time_slot": "slot-09", "is_preorder": True},
    )
    OrderItem.objects.create(order=order, line_id="1", sku="SKU", name="Produto", qty=1, unit_price_q=1500, line_total_q=1500)
    return order


def _body(operator, order, **inputs):
    return {
        "expected_actor_id": operator.pk,
        "base_revision": operational_revision(order, field="schedule"),
        "idempotency_key": str(uuid4()),
        **inputs,
    }


def test_sem_permissao_e_403(client, plain_staff, order):
    client.force_login(plain_staff)
    url = reverse("api-backstage-order-reschedule", args=[order.ref])
    response = client.post(url, data={"date": _day(5).isoformat()}, content_type="application/json")
    assert response.status_code == 403


def test_reagenda_e_aparece_no_historico(client, operator, order):
    client.force_login(operator)
    url = reverse("api-backstage-order-reschedule", args=[order.ref])

    response = client.post(
        url, data=_body(operator, order, date=_day(5).isoformat(), slot="slot-12", reason="cliente pediu"),
        content_type="application/json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["outcome"] == "applied"
    assert body["changed"] is True and body["to_date"] == _day(5).isoformat() and body["to_slot"] == "slot-12"
    order.refresh_from_db()
    assert order.data["delivery_date"] == _day(5).isoformat()
    assert order.data["reschedule_history"][0]["actor"]
    assert "schedule" in body["order"]["revisions"]
    timeline = [e for e in body["order"]["timeline"] if e["event_type"] == "order_rescheduled"]
    assert timeline and timeline[0]["label"] == "Data combinada alterada"
    assert timeline[0]["detail"] == f"{_day(3):%d/%m} → {_day(5):%d/%m} — cliente pediu"


def test_recusa_sai_no_dialeto_de_campo(client, operator, order):
    client.force_login(operator)
    url = reverse("api-backstage-order-reschedule", args=[order.ref])

    response = client.post(url, data=_body(operator, order, date=_day(-1).isoformat()), content_type="application/json")

    assert response.status_code == 400
    body = response.json()
    assert body["detail"] == "Não é possível encomendar para uma data passada."
    assert body["field"] == "date"
    assert body["errors"] == {"date": [body["detail"]]}
    assert body["outcome"] == "not_applied"
    order.refresh_from_db()
    assert order.data["delivery_date"] == _day(3).isoformat()


def test_revisao_velha_e_conflito(client, operator, order):
    client.force_login(operator)
    url = reverse("api-backstage-order-reschedule", args=[order.ref])
    stale = _body(operator, order, date=_day(5).isoformat())
    order.data = {**order.data, "delivery_time_slot": "slot-15"}
    order.save(update_fields=["data"])

    response = client.post(url, data=stale, content_type="application/json")

    assert response.status_code == 409
    order.refresh_from_db()
    assert order.data["delivery_date"] == _day(3).isoformat()


def test_data_ausente_e_400(client, operator, order):
    client.force_login(operator)
    url = reverse("api-backstage-order-reschedule", args=[order.ref])
    response = client.post(url, data=_body(operator, order), content_type="application/json")
    assert response.status_code == 400
    assert response.json()["field"] == "date"
