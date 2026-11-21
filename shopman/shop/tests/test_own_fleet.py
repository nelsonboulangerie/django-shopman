"""A corrida do entregador da casa, de ponta a ponta (DEV-2026-030, frente M2).

Designar a rota a uma pessoa da casa, ela confirmar o link, sair, entregar por parada e
relatar problema, tudo pela API pública do link. As transições entram pelo funil de sempre
(``courier.apply_status``); estes testes conferem o efeito no pedido.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.cache import cache
from django.urls import reverse
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import courier_own_fleet
from shopman.shop.models import Courier, CourierRate, DeliveryService, Shop
from shopman.shop.services import courier, delivery_services, own_fleet

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web")]

PHONE = "p" * 32
OTHER_PHONE = "q" * 32


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Nelson Boulangerie", route="Av. Madre Leônia Milito", street_number="446",
        neighborhood="Bela Suíça", city="Londrina", state_code="PR", latitude=-23.3405, longitude=-51.1580,
    )


@pytest.fixture
def casa():
    service = DeliveryService.objects.get(ref="casa")
    CourierRate.objects.create(service=service, max_km=Decimal("6"), value_q=1200, extra_stop_q=300)
    CourierRate.objects.create(service=service, max_km=None, value_q=2000, extra_stop_q=300)
    return service


@pytest.fixture
def diego(casa):
    return Courier.objects.create(service=casa, ref="diego", name="Diego", phone="+5543999990000",
                                  vehicle="Moto prata · ABC1D23")


def _order(ref, *, name="Marina Souza", lat=-23.31, lng=-51.16, status=Order.Status.READY, **extra) -> Order:
    data = {
        "fulfillment_type": "delivery",
        "customer": {"name": name, "phone": "5543988887777"},
        "delivery_address_structured": {
            "route": "Rua Caracas", "street_number": "420", "complement": "Torre 2 · Apto 41",
            "neighborhood": "Gleba Palhano", "city": "Londrina", "state_code": "PR",
            "formatted_address": "Rua Caracas 420", "delivery_instructions": "O interfone não funciona",
            "latitude": lat, "longitude": lng,
        },
        "payment": {"method": "card", "status": "captured"},
        "volumes": 2,
    }
    data.update(extra)
    return Order.objects.create(ref=ref, channel_ref="web", session_key=f"S-{ref}", status=status,
                                snapshot={"items": []}, data=data, total_q=5800)


def _get(client, token, device=PHONE):
    return client.get(reverse("courier-ride-link", args=[token]), HTTP_X_COURIER_DEVICE=device)


def _post(client, name, token, body=None, device=PHONE):
    return client.post(reverse(name, args=[token]), body or {}, content_type="application/json",
                       HTTP_X_COURIER_DEVICE=device)


# ── o serviço da casa no contrato ────────────────────────────────────────────


def test_the_house_ride_resolves_the_house_module(casa):
    assert delivery_services.courier_backend({"service": "casa"}) is courier_own_fleet
    caps = delivery_services.capabilities({"service": "casa"})
    assert caps.assign and not caps.customer_tracking and not caps.push_status


def test_house_quote_comes_from_the_table(shop, casa):
    estimate = courier_own_fleet.estimate(
        pickup={"lat": -23.3405, "lng": -51.1580}, dropoff={"lat": -23.31, "lng": -51.16})
    assert estimate is not None and estimate.value_q == 1200 and estimate.km > 0


# ── designar ────────────────────────────────────────────────────────────────


def test_assign_writes_the_house_ride_and_issues_the_link(shop, diego):
    a47, c03 = _order("WEB-A47"), _order("WEB-C03", name="Paulo Lima", lat=-23.305, lng=-51.165)
    result = own_fleet.assign([a47, c03], diego, actor="operator:ana")
    for order in (a47, c03):
        order.refresh_from_db()
        block = courier.get_block(order)
        assert block["service"] == "casa" and block["provider"] == "own_fleet"
        assert block["status"] == "A" and block["ride_ref"] == result.ride_ref
        assert block["driver"]["name"] == "Diego" and block["ride_orders"] == ["WEB-A47", "WEB-C03"]
        assert block["estimate"]["value_q"] >= 1200
    assert result.link.order_refs == ["WEB-A47", "WEB-C03"]
    assert courier.has_active_ride(a47)


def test_assign_refuses_order_with_a_live_ride(shop, diego):
    a47 = _order("WEB-A47")
    own_fleet.assign([a47], diego, actor="operator:ana")
    with pytest.raises(own_fleet.OwnFleetRefused):
        own_fleet.assign([a47], diego, actor="operator:ana")


# ── o link pela API ─────────────────────────────────────────────────────────


def test_unconfirmed_link_shows_only_who_the_ride_is_for(client, shop, diego):
    token = own_fleet.assign([_order("WEB-A47")], diego, actor="operator:ana").link.token
    body = _get(client, token).json()
    assert body == {"moment": "confirm", "courier": "Diego"}  # nada da rota antes de confirmar


def test_full_ride_through_the_link(client, shop, diego):
    a47, c03 = _order("WEB-A47"), _order("WEB-C03", name="Paulo Lima", lat=-23.305, lng=-51.165)
    token = own_fleet.assign([a47, c03], diego, actor="operator:ana").link.token

    pickup = _post(client, "courier-ride-link-claim", token).json()
    assert pickup["moment"] == "pickup" and pickup["label"].startswith("Rota ")
    assert [s["code"] for s in pickup["stops"]] == [own_fleet._order_label(a47),
                                                   own_fleet._order_label(c03)]
    assert "phone" not in pickup["stops"][0]  # telefone só com a rota na rua
    assert _get(client, token, device=OTHER_PHONE).status_code == 403

    route = _post(client, "courier-ride-link-events", token, {"action": "depart"}).json()
    assert route["moment"] == "route" and route["stops"][0]["phone"]
    a47.refresh_from_db()
    assert a47.status == Order.Status.DISPATCHED

    after = _post(client, "courier-ride-link-events", token, {"action": "deliver", "order_ref": "WEB-A47"}).json()
    a47.refresh_from_db()
    c03.refresh_from_db()
    assert a47.status == Order.Status.DELIVERED and c03.status == Order.Status.DISPATCHED
    assert [s["state"] for s in after["stops"]] == ["done", "open"]

    _post(client, "courier-ride-link-events", token, {"action": "deliver", "order_ref": "WEB-C03"})
    c03.refresh_from_db()
    assert c03.status == Order.Status.DELIVERED
    # Pago e sem custódia: nada a acertar na volta, a rota fecha e o endereço some.
    closed = _get(client, token).json()
    assert closed["moment"] == "closed" and "stops" not in closed


def test_depart_waits_for_every_order_to_be_ready(client, shop, diego):
    a47, c03 = _order("WEB-A47"), _order("WEB-C03", status=Order.Status.PREPARING)
    token = own_fleet.assign([a47, c03], diego, actor="operator:ana").link.token
    assert _post(client, "courier-ride-link-claim", token).json()["moment"] == "pickup_wait"
    refused = _post(client, "courier-ride-link-events", token, {"action": "depart"})
    assert refused.status_code == 409 and "ficar pronto" in refused.json()["detail"]


def test_events_need_the_confirmation_first(client, shop, diego):
    token = own_fleet.assign([_order("WEB-A47")], diego, actor="operator:ana").link.token
    assert _post(client, "courier-ride-link-events", token, {"action": "depart"}).status_code == 409


def test_problem_is_recorded_and_alerts_the_counter_without_changing_the_order(client, shop, diego):
    a47 = _order("WEB-A47")
    token = own_fleet.assign([a47], diego, actor="operator:ana").link.token
    _post(client, "courier-ride-link-claim", token)
    _post(client, "courier-ride-link-events", token, {"action": "depart"})
    body = _post(client, "courier-ride-link-events", token,
                 {"action": "problem", "order_ref": "WEB-A47", "kind": own_fleet.NO_ANSWER}).json()
    a47.refresh_from_db()
    assert a47.status == Order.Status.DISPATCHED
    assert courier.get_block(a47)["problems"][0]["kind"] == own_fleet.NO_ANSWER
    assert OperatorAlert.objects.filter(type="courier_stop_problem", order_ref="WEB-A47").exists()
    assert body["moment"] == "route"


def test_other_payment_needs_the_method(client, shop, diego):
    token = own_fleet.assign([_order("WEB-A47")], diego, actor="operator:ana").link.token
    _post(client, "courier-ride-link-claim", token)
    refused = _post(client, "courier-ride-link-events", token,
                    {"action": "problem", "order_ref": "WEB-A47", "kind": own_fleet.OTHER_PAYMENT})
    assert refused.status_code == 409


def test_cancelling_the_house_ride_revokes_the_link(client, shop, diego):
    a47 = _order("WEB-A47")
    result = own_fleet.assign([a47], diego, actor="operator:ana")
    assert courier_own_fleet.cancel(result.ride_ref) is True
    assert _get(client, result.link.token).json()["moment"] == "cancelled"


def test_unknown_link(client):
    assert _get(client, "nao-existe").status_code == 404


def test_api_answers_are_private(client, shop, diego):
    token = own_fleet.assign([_order("WEB-A47")], diego, actor="operator:ana").link.token
    response = _get(client, token)
    assert response["Cache-Control"] == "no-store" and "noindex" in response["X-Robots-Tag"]
