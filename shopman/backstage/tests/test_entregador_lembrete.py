"""Lembrete TEMPORÁRIO de chamar o entregador (WP-ENTREGADOR-CHAMADA-ANTECIPADA).

X minutos (padrão 10) depois do início do preparo de uma entrega da casa sem
corrida pedida, o Gestor cobra o operador. Um aviso por pedido, lido (não gravado);
some quando a corrida é pedida, quando o pedido sai do preparo ou quando alguém
dispensa. iFood nunca. E o "Chamar entregador" passa a valer desde o preparo.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Directive, Order, OrderItem

from shopman.backstage.projections.order_queue import build_order_card
from shopman.backstage.services import courier_reminder
from shopman.shop.adapters import courier_mock
from shopman.shop.directives import COURIER_DISPATCH
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop(db):
    return Shop.objects.create(
        name="Loja", route="Rua da Loja", street_number="10", city="Londrina", state_code="PR",
        latitude=-23.34, longitude=-51.15,
    )


@pytest.fixture
def operator(db, shop):
    perm = Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders",
    )
    user = User.objects.create_user("lembrete-op", password="pw", is_staff=True)
    user.user_permissions.add(perm)
    return user


def _order(ref="NB-261013-0042", *, status=Order.Status.PREPARING, minutes_ago=12, channel="web", **extra):
    data = {
        "fulfillment_type": "delivery",
        "customer": {"name": "Ana", "phone": "5543999990000"},
        "payment": {"method": "pix"},
        "delivery_address_structured": {
            "route": "Rua das Flores", "street_number": "123", "city": "Londrina", "state_code": "PR",
            "formatted_address": "Rua das Flores 123", "latitude": -23.31, "longitude": -51.16,
        },
        **extra,
    }
    order = Order.objects.create(
        ref=ref, channel_ref=channel, session_key=f"S-{ref}", status=status, snapshot={"items": []},
        total_q=1500, data=data, preparing_at=timezone.now() - timedelta(minutes=minutes_ago),
    )
    OrderItem.objects.create(order=order, line_id="1", sku="SKU", name="Produto", qty=1,
                             unit_price_q=1500, line_total_q=1500)
    return order


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_card_carries_the_reminder_from_the_start_of_prep(shop):
    order = _order()
    card = build_order_card(order)
    reminder = card.courier_reminder
    assert reminder is not None
    assert reminder.short_ref == "0042"
    assert reminder.since_basis == "preparing"
    since = datetime.fromisoformat(reminder.since_iso)
    assert datetime.fromisoformat(reminder.due_at_iso) - since == timedelta(minutes=10)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_first_kitchen_start_wins_over_preparing_at(shop):
    first = timezone.now() - timedelta(minutes=20)
    order = _order(kds_started={"7": {"at": first.isoformat(), "by": "rafael"},
                                "8": {"at": (first + timedelta(minutes=3)).isoformat(), "by": "bia"}})
    reminder = courier_reminder.courier_reminder(order)
    assert reminder.since_basis == "kds"
    assert datetime.fromisoformat(reminder.since_iso) == first


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_minutes_and_switch_come_from_the_shop(shop):
    order = _order()
    shop.defaults = {"delivery": {"courier_reminder": {"minutes": 4}}}
    shop.save()
    cache.clear()
    reminder = courier_reminder.courier_reminder(order)
    assert datetime.fromisoformat(reminder.due_at_iso) - datetime.fromisoformat(reminder.since_iso) == timedelta(minutes=4)

    shop.defaults = {"delivery": {"courier_reminder": {"enabled": False}}}
    shop.save()
    cache.clear()
    assert courier_reminder.courier_reminder(order) is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
@pytest.mark.parametrize("case", ["ready", "pickup", "ifood", "ride", "failed_ride"])
def test_no_reminder_where_it_does_not_fit(shop, case):
    kwargs = {}
    if case == "ready":
        kwargs["status"] = Order.Status.READY
    if case == "pickup":
        kwargs["fulfillment_type"] = "pickup"
    if case == "ifood":
        kwargs.update(channel="ifood", ifood={"delivered_by": "IFOOD"})
    if case == "ride":
        kwargs["courier"] = {"id_mch": "M1", "status": "D"}
    if case == "failed_ride":
        kwargs["courier"] = {"attempts": [{"id_mch": "M1", "status": "N"}]}
    assert courier_reminder.courier_reminder(_order(**kwargs)) is None


def test_no_reminder_without_the_central(shop):
    """Sem a central configurada não há "Chamar entregador": o aviso não teria gesto."""
    assert courier_reminder.courier_reminder(_order()) is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_calling_during_prep_queues_the_ride_and_ends_the_reminder(client, operator, shop):
    order = _order()
    client.force_login(operator)
    detail = client.get(reverse("api-backstage-order-detail", args=[order.ref])).json()["order"]
    assert detail["courier"]["can_dispatch"] is True
    assert detail["courier"]["reminder"]["short_ref"] == "0042"
    action = next(a for a in detail["actions"] if a["ref"] == "courier-dispatch")
    assert action["enabled"] is True

    resp = client.post(reverse("api-backstage-order-courier-dispatch", args=[order.ref]),
        {"expected_actor_id": operator.pk, "base_revision": action["payload_schema"]["base_revision"]},
        content_type="application/json", HTTP_IDEMPOTENCY_KEY="lembrete-chamar")
    assert resp.status_code == 200, resp.content
    order.refresh_from_db()
    assert order.data["courier"]["called_at"]
    assert order.data["courier"]["called_by"]
    assert Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=order.ref).exists()
    assert courier_reminder.courier_reminder(order) is None

    # O worker abre a corrida com o pedido ainda em preparo.
    from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler

    task = Directive.objects.get(topic=COURIER_DISPATCH, payload__order_ref=order.ref)
    CourierDispatchHandler().handle(message=task, ctx={})
    order.refresh_from_db()
    assert order.data["courier"]["id_mch"]
    assert order.data["courier"]["called_at"]  # a primeira chamada sobrevive à abertura


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dismiss_is_for_every_device_and_idempotent(client, operator, shop):
    order = _order()
    client.force_login(operator)
    url = reverse("api-backstage-order-courier-reminder-dismiss", args=[order.ref])
    assert client.post(url, content_type="application/json").status_code == 200
    order.refresh_from_db()
    record = order.data["courier_reminder"]
    assert record["dismissed_by"]
    assert courier_reminder.courier_reminder(order) is None
    assert build_order_card(order).courier_reminder is None
    # De novo: sucesso, sem sobrescrever quem dispensou primeiro.
    assert client.post(url, content_type="application/json").status_code == 200
    order.refresh_from_db()
    assert order.data["courier_reminder"] == record
    assert order.events.filter(type="courier_reminder_dismissed").count() == 1


def test_dismiss_needs_who_manages_orders(client, shop):
    order = _order()
    user = User.objects.create_user("sem-perm", password="pw", is_staff=True)
    client.force_login(user)
    url = reverse("api-backstage-order-courier-reminder-dismiss", args=[order.ref])
    assert client.post(url, content_type="application/json").status_code == 403


def test_admin_saves_only_what_differs_from_the_default(shop):
    from shopman.shop.admin.shop import _ORDERING_FIELDSETS, ShopForm
    from shopman.shop.tests.test_admin import _shop_form_data

    fields = [f for _, opts in _ORDERING_FIELDSETS for row in opts["fields"]
              for f in (row if isinstance(row, tuple) else (row,))]
    assert {"defaults_delivery_courier_reminder_enabled", "defaults_delivery_courier_reminder_minutes"} <= set(fields)
    assert ShopForm(instance=shop).fields["defaults_delivery_courier_reminder_enabled"].initial is True

    data = _shop_form_data(shop)
    data.pop("defaults_delivery_courier_reminder_enabled", None)  # switch desligado não vai no POST
    data["defaults_delivery_courier_reminder_minutes"] = "15"
    form = ShopForm(data=data, instance=shop)
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.defaults["delivery"]["courier_reminder"] == {"enabled": False, "minutes": 15}

    data = _shop_form_data(saved)
    data["defaults_delivery_courier_reminder_enabled"] = "on"
    data["defaults_delivery_courier_reminder_minutes"] = ""
    form = ShopForm(data=data, instance=saved)
    assert form.is_valid(), form.errors
    assert "delivery" not in form.save().defaults
