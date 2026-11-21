"""Quem leva: os entregadores da casa no gesto de chamar (DEV-2026-030, frente M3, #2526).

Três portas do Gestor: ler quem da casa está na escala (com o valor da tabela para os
pedidos escolhidos), enviar a corrida a uma pessoa da casa (link + WhatsApp pronto, no
protocolo de intenção da corrida da TaOn) e ligar ou desligar a escala de hoje.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from shopman.cashman import Entry
from shopman.cashman import services as cash
from shopman.orderman.models import Order, OrderItem

from shopman.shop.models import Channel, Courier, CourierLink, CourierRate, DeliveryService, Shop
from shopman.shop.services import courier, own_fleet

pytestmark = [pytest.mark.django_db]

CREW = "api-backstage-house-couriers"
RIDE = "api-backstage-house-courier-ride"
SHIFT = "api-backstage-house-courier-shift"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield


@pytest.fixture
def shop(db):
    Channel.objects.get_or_create(ref="web", defaults={"name": "Loja", "is_active": True})
    return Shop.objects.create(name="Loja", route="Rua da Loja", street_number="10", city="Londrina",
                               state_code="PR", latitude=-23.3405, longitude=-51.1580)


@pytest.fixture
def casa(db):
    service = DeliveryService.objects.get(ref="casa")
    CourierRate.objects.create(service=service, max_km=Decimal("6"), value_q=1200, extra_stop_q=300)
    CourierRate.objects.create(service=service, max_km=None, value_q=2000, extra_stop_q=300)
    return service


def _courier(casa, ref, name, *, on_shift=True, phone="+5543999990000"):
    return Courier.objects.create(service=casa, ref=ref, name=name, phone=phone, vehicle="Moto prata",
                                  on_shift_on=timezone.localdate() if on_shift else None)


@pytest.fixture
def diego(casa):
    return _courier(casa, "diego", "Diego")


def _manager(username="marina", *, allowed=True) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    if allowed:
        user.user_permissions.add(Permission.objects.get(
            content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders"))
    return user


@pytest.fixture
def operator(client, shop):
    user = _manager()
    client.force_login(user)
    return user


def _order(ref, *, lat=-23.31, lng=-51.16, method="pix", status="captured", total_q=5800, change_for_q=None,
           collection=None):
    payment = {"method": method, "status": status}
    if collection:
        payment["collection"] = collection
    if change_for_q:
        payment["change_for_q"] = change_for_q
    order = Order.objects.create(ref=ref, channel_ref="web", status=Order.Status.READY, total_q=total_q, data={
        "customer": {"name": "Ana Souza", "phone": "5543988887777"}, "fulfillment_type": "delivery",
        "payment": payment,
        "delivery_address_structured": {"route": "Rua Caracas", "street_number": "420", "city": "Londrina",
                                        "state_code": "PR", "formatted_address": "Rua Caracas 420",
                                        "neighborhood": "Gleba Palhano", "latitude": lat, "longitude": lng}})
    OrderItem.objects.create(order=order, line_id="1", sku="PAO", name="Pão", qty=1, unit_price_q=total_q,
                             line_total_q=total_q)
    return order


def _send(client, operator, orders, who="diego", key="k-1", **extra):
    body = {
        "refs": [order.ref for order in orders], "courier": who, "expected_actor_id": operator.pk,
        "base_revisions": {order.ref: courier.dispatch_revision(order) for order in orders}, **extra,
    }
    return client.post(reverse(RIDE), body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)


# ── quem leva (leitura) ──────────────────────────────────────────────────────


def test_crew_lists_active_couriers_with_shift_state_and_the_default(client, operator, casa, diego):
    _courier(casa, "rui", "Rui", on_shift=False)
    Courier.objects.create(service=casa, ref="velho", name="Velho", phone="+5543999990001", is_active=False)
    body = client.get(reverse(CREW)).json()
    assert body["active"] is True
    assert body["default"] == {"ref": "taon", "name": "TaOn"}
    assert [(c["ref"], c["on_shift"], c["state_label"]) for c in body["couriers"]] == [
        ("diego", True, "Livre"), ("rui", False, "Livre")]
    assert body["couriers"][0]["value_q"] is None  # sem pedidos, sem valor


def test_crew_prices_the_route_by_the_table_for_couriers_on_shift(client, operator, casa, diego):
    _courier(casa, "rui", "Rui", on_shift=False)
    a47, c03 = _order("WEB-A47"), _order("WEB-C03", lat=-23.305, lng=-51.165)
    body = client.get(reverse(CREW), {"refs": [a47.ref, c03.ref]}).json()
    diego_row = body["couriers"][0]
    assert diego_row["value_q"] == 1500 and diego_row["value"] == "R$ 15,00"  # 12,00 + 3,00 da parada a mais
    assert body["couriers"][1]["value_q"] is None  # fora da escala não cota


def test_crew_says_na_rua_while_the_courier_holds_a_live_house_ride(client, operator, diego):
    own_fleet.assign([_order("WEB-A47")], diego, actor="operator:marina")
    row = client.get(reverse(CREW)).json()["couriers"][0]
    assert (row["state"], row["state_label"]) == ("busy", "Na rua")


def test_crew_is_inactive_when_the_house_service_is_off(client, operator, casa, diego):
    DeliveryService.objects.filter(pk=casa.pk).update(is_active=False)
    assert client.get(reverse(CREW)).json() == {"active": False, "service": None,
                                                "default": {"ref": "taon", "name": "TaOn"}, "couriers": []}


def test_crew_requires_the_orders_permission(client, shop, diego):
    client.force_login(_manager("sem", allowed=False))
    assert client.get(reverse(CREW)).status_code == 403


# ── enviar a corrida ─────────────────────────────────────────────────────────


@override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://loja.test")
def test_send_assigns_the_ride_and_returns_the_link_and_the_whatsapp(client, operator, diego):
    a47, c03 = _order("WEB-A47"), _order("WEB-C03", lat=-23.305, lng=-51.165)
    response = _send(client, operator, [a47, c03], ride_number=3)
    assert response.status_code == 200, response.json()
    body = response.json()
    link = CourierLink.objects.get(ride_ref=body["ride_ref"])
    assert link.courier == diego and link.order_refs == ["WEB-A47", "WEB-C03"]
    assert body["link_url"] == f"https://loja.test/rota/{link.token}"
    assert body["ride_letter"] == "C" and body["detail"] == "Rota C enviada para Diego."
    wa = urlparse(body["whatsapp_url"])
    assert (wa.netloc, wa.path) == ("wa.me", "/5543999990000")
    assert parse_qs(wa.query)["text"] == [
        f"Corrida para você: Rota C. Abra o link no seu celular: https://loja.test/rota/{link.token}"]
    for order in (a47, c03):
        order.refresh_from_db()
        block = courier.get_block(order)
        assert (block["service"], block["status"], block["courier_ref"]) == ("casa", "A", "diego")
        assert block["ride_number"] == 3


def test_single_order_is_named_by_its_code(client, operator, diego):
    body = _send(client, operator, [_order("WEB-A47")]).json()
    assert body["detail"].startswith("Pedido ") and body["detail"].endswith(" enviado para Diego.")
    text = parse_qs(urlparse(body["whatsapp_url"]).query)["text"][0]
    assert text.startswith("Corrida para você: Pedido ")


def test_send_replays_the_same_ride_for_the_same_key(client, operator, diego):
    a47 = _order("WEB-A47")
    first = _send(client, operator, [a47]).json()
    a47.refresh_from_db()
    again = client.post(reverse(RIDE), {
        "refs": [a47.ref], "courier": "diego", "expected_actor_id": operator.pk,
        "base_revisions": {a47.ref: "irrelevante-no-replay"}}, content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="k-1")
    # A mesma chave com outro "o que a tela leu" é outra intenção: recusa, nada novo.
    assert again.status_code == 409
    replay = client.get(reverse(RIDE), {"idempotency_key": "k-1"}).json()
    assert replay["ride_ref"] == first["ride_ref"] and replay["replayed"] is True
    assert CourierLink.objects.count() == 1


def test_send_refuses_when_an_order_changed_after_the_screen_read_it(client, operator, diego):
    a47 = _order("WEB-A47")
    body = {"refs": [a47.ref], "courier": "diego", "expected_actor_id": operator.pk,
            "base_revisions": {a47.ref: "velha"}}
    response = client.post(reverse(RIDE), body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="k-2")
    assert response.status_code == 409 and response.json()["code"] == "revision_changed"
    assert not CourierLink.objects.exists()


def test_send_refuses_without_the_observed_intention(client, operator, diego):
    a47 = _order("WEB-A47")
    response = client.post(reverse(RIDE), {"refs": [a47.ref], "courier": "diego", "expected_actor_id": operator.pk},
                           content_type="application/json", HTTP_IDEMPOTENCY_KEY="k-3")
    assert response.status_code == 400 and response.json()["code"] == "intention_required"


def test_send_refuses_a_courier_off_shift_with_the_screen_text(client, operator, casa):
    _courier(casa, "rui", "Rui", on_shift=False)
    response = _send(client, operator, [_order("WEB-A47")], who="rui")
    assert response.status_code == 400
    assert response.json()["detail"] == "Rui não está na escala de hoje. Ligue em Entregadores de hoje."
    assert response.json()["outcome"] == "not_applied"


def test_send_refuses_an_order_that_already_has_a_ride(client, operator, diego):
    a47 = _order("WEB-A47")
    own_fleet.assign([a47], diego, actor="operator:marina")
    a47.refresh_from_db()
    response = _send(client, operator, [a47])
    assert response.status_code == 400 and response.json()["detail"].endswith("já tem corrida.")


def test_send_asks_the_change_and_then_takes_it_from_the_drawer(client, operator, diego):
    shift = cash.open_shift(operator=operator, float_q=10000)
    a47 = _order("DLV-0418", method="cash", status="pending", total_q=7400, change_for_q=10000,
                 collection="on_delivery")
    refused = _send(client, operator, [a47], key="k-4")
    assert refused.status_code == 400 and refused.json()["code"] == "change_out_required"
    assert not CourierLink.objects.exists() and not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT).exists()

    assert _send(client, operator, [a47], key="k-5", change_out={a47.ref: "26,00"}).status_code == 200
    line = Entry.objects.get(kind=Entry.Kind.COURIER_OUT, order_ref=a47.ref)
    assert (line.amount_q, line.shift_id) == (-2600, shift.pk)


def test_send_requires_the_orders_permission(client, shop, diego):
    user = _manager("sem", allowed=False)
    client.force_login(user)
    a47 = _order("WEB-A47")
    assert _send(client, user, [a47]).status_code == 403
    assert not CourierLink.objects.exists()


# ── a escala de hoje ─────────────────────────────────────────────────────────


def test_shift_toggle_turns_today_on_and_off(client, operator, casa):
    rui = _courier(casa, "rui", "Rui", on_shift=False)
    on = client.post(reverse(SHIFT, args=["rui"]), {"on_shift": True}, content_type="application/json")
    assert on.status_code == 200 and on.json()["couriers"][0]["on_shift"] is True
    rui.refresh_from_db()
    assert rui.on_shift_on == timezone.localdate()
    off = client.post(reverse(SHIFT, args=["rui"]), {"on_shift": False}, content_type="application/json")
    assert off.json()["couriers"][0]["on_shift"] is False
    rui.refresh_from_db()
    assert rui.on_shift_on is None


def test_shift_toggle_refuses_unknown_courier_and_bad_input(client, operator, diego):
    assert client.post(reverse(SHIFT, args=["ninguem"]), {"on_shift": True},
                       content_type="application/json").status_code == 404
    bad = client.post(reverse(SHIFT, args=["diego"]), {"on_shift": "sim"}, content_type="application/json")
    assert bad.status_code == 400 and bad.json()["field"] == "on_shift"


def test_shift_toggle_requires_the_orders_permission(client, shop, diego):
    client.force_login(_manager("sem", allowed=False))
    assert client.post(reverse(SHIFT, args=["diego"]), {"on_shift": False},
                       content_type="application/json").status_code == 403
