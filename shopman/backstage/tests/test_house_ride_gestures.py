"""A corrida da casa na página Entregas (DEV-2026-030, frente M3b, #2898).

A projeção diz quem leva ("Diego leva", "Diego na rua · 1 de 2 entregues") e oferece os
gestos do balcão para quando o entregador está sem celular: "Saiu", "A47 entregue",
"Reenviar o link" e "Soltar o link". A corrida da TaOn não ganha nada disso.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from shopman.orderman.models import Order

from shopman.backstage.projections.deliveries import build_deliveries
from shopman.backstage.services import house_couriers
from shopman.backstage.tests.test_house_couriers import _courier, _manager, _order, casa, shop  # noqa: F401
from shopman.shop.adapters import courier_mock
from shopman.shop.models import CourierLink
from shopman.shop.services import courier, courier_links, own_fleet

pytestmark = [pytest.mark.django_db]

GESTURE = "api-backstage-house-ride-gesture"


@pytest.fixture(autouse=True)
def _mock_courier():
    courier_mock.reset()
    cache.clear()
    with override_settings(SHOPMAN_COURIER_ADAPTER="shopman.shop.adapters.courier_mock",
                           SHOPMAN_STOREFRONT_BASE_URL="https://loja.test"):
        yield
    courier_mock.reset()


@pytest.fixture
def operator(client, shop):  # noqa: F811
    user = _manager()
    client.force_login(user)
    return user


@pytest.fixture
def ride(casa):  # noqa: F811
    diego = _courier(casa, "diego", "Diego")
    a47, c03 = _order("WEB-A47"), _order("WEB-C03", lat=-23.305, lng=-51.165)
    assignment = own_fleet.assign([a47, c03], diego, actor="operator:marina")
    return assignment


def _house(user, ride_ref):
    row = next(item for item in build_deliveries(user=user).rides if item.key == ride_ref)
    return row.house


def _post(client, user, ride_ref, gesture, *, key, base=None, **body):
    base = base or house_couriers.ride_revision(house_couriers.live_link(ride_ref))
    payload = {"expected_actor_id": user.pk, "base_revision": base, **body}
    return client.post(reverse(GESTURE, args=[ride_ref, gesture]), payload, content_type="application/json",
                       HTTP_IDEMPOTENCY_KEY=key)


# ── a projeção ──────────────────────────────────────────────────────────────


def test_house_ride_says_who_takes_it_and_offers_the_counter_gestures(operator, ride):
    house = _house(operator, ride.ride_ref)
    assert house.courier_name == "Diego" and house.moment == "Diego leva"
    assert house.hint.startswith("Entregador da casa · R$ ") and house.hint.endswith("Ainda não abriu o link")
    assert house.depart_action is not None and house.depart_action.confirmation["required"] is True
    assert house.resend_action is not None and house.release_action is None  # ninguém prendeu o link
    assert house.deliver_actions == ()
    assert house.depart_action.payload_schema["base_revision"] == house_couriers.ride_revision(
        house_couriers.live_link(ride.ride_ref))


def test_taon_ride_has_no_house_block(operator, shop):  # noqa: F811
    from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler

    order = _order("WEB-T01")
    CourierDispatchHandler().handle(message=courier.request_dispatch(order, actor="operator:marina"), ctx={})
    rows = build_deliveries(user=operator).rides
    assert rows and all(row.house is None for row in rows)


def test_claimed_link_shows_the_hour_and_offers_release(operator, ride):
    courier_links.claim(ride.link.token, "c" * 32)
    house = _house(operator, ride.ride_ref)
    assert "Abriu o link às " in house.hint and house.link_claimed
    assert house.release_action is not None


# ── os gestos ──────────────────────────────────────────────────────────────


def test_depart_then_deliver_one_stop_by_the_counter(client, operator, ride):
    response = _post(client, operator, ride.ride_ref, "depart", key="d-1")
    assert response.status_code == 200, response.json()
    assert response.json()["detail"].endswith("Diego saiu para entrega.")
    for ref in ("WEB-A47", "WEB-C03"):
        order = Order.objects.get(ref=ref)
        assert courier.get_block(order)["status"] == "E" and order.status == Order.Status.DISPATCHED
    house = _house(operator, ride.ride_ref)
    assert house.moment == "Diego na rua · 0 de 2 entregues" and house.depart_action is None
    assert [item.code for item in house.deliver_actions] == [
        own_fleet._order_label(Order.objects.get(ref="WEB-A47")), own_fleet._order_label(Order.objects.get(ref="WEB-C03"))]

    delivered = _post(client, operator, ride.ride_ref, "deliver", key="e-1", ref="WEB-A47")
    assert delivered.status_code == 200, delivered.json()
    assert courier.get_block(Order.objects.get(ref="WEB-A47"))["status"] == "F"
    assert courier.get_block(Order.objects.get(ref="WEB-C03"))["status"] == "E"
    house = _house(operator, ride.ride_ref)
    assert house.moment == "Diego na rua · 1 de 2 entregues"
    assert [item.ref for item in house.deliver_actions] == ["WEB-C03"]


def test_deliver_before_leaving_is_refused_with_the_screen_text(client, operator, ride):
    response = _post(client, operator, ride.ride_ref, "deliver", key="e-2", ref="WEB-A47")
    assert response.status_code == 400
    assert response.json()["detail"] == "Toque em Saí da loja antes de entregar."


def test_depart_refuses_while_an_order_is_not_ready(client, operator, casa):  # noqa: F811
    diego = _courier(casa, "diego", "Diego")
    a47 = _order("WEB-A47")
    Order.objects.filter(pk=a47.pk).update(status=Order.Status.PREPARING)
    a47.refresh_from_db()
    assignment = own_fleet.assign([a47], diego, actor="operator:marina")
    response = _post(client, operator, assignment.ride_ref, "depart", key="d-2")
    assert response.status_code == 400 and response.json()["detail"].endswith("ficar pronto.")


def test_resend_gives_the_same_link_on_whatsapp(client, operator, ride):
    response = _post(client, operator, ride.ride_ref, "resend", key="r-1")
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["link_url"] == f"https://loja.test/rota/{ride.link.token}"
    assert body["detail"] == f"Rota {courier.ride_letter(courier.get_block(Order.objects.get(ref='WEB-A47'))['ride_number'])} reenviada para Diego."
    text = parse_qs(urlparse(body["whatsapp_url"]).query)["text"][0]
    assert text.endswith(f"Abra o link no seu celular: https://loja.test/rota/{ride.link.token}")
    assert CourierLink.objects.filter(ride_ref=ride.ride_ref, revoked_at__isnull=True).count() == 1


def test_release_unbinds_the_phone_and_is_refused_when_nothing_is_bound(client, operator, ride):
    refused = _post(client, operator, ride.ride_ref, "release", key="l-1")
    assert refused.status_code == 400 and refused.json()["detail"] == "O link ainda não está preso a nenhum celular."
    courier_links.claim(ride.link.token, "c" * 32)
    released = _post(client, operator, ride.ride_ref, "release", key="l-2")
    assert released.status_code == 200, released.json()
    ride.link.refresh_from_db()
    assert ride.link.device_hash == ""


def test_gesture_on_a_changed_ride_is_refused(client, operator, ride):
    response = _post(client, operator, ride.ride_ref, "depart", key="d-3", base="velha")
    assert response.status_code == 409
    assert courier.get_block(Order.objects.get(ref="WEB-A47"))["status"] == "A"


def test_gestures_require_the_orders_permission(client, shop, ride):  # noqa: F811
    user = _manager("sem", allowed=False)
    client.force_login(user)
    assert _post(client, user, ride.ride_ref, "depart", key="d-4").status_code == 403


def test_unknown_gesture_is_404(client, operator, ride):
    assert _post(client, operator, ride.ride_ref, "explode", key="x-1").status_code == 404
