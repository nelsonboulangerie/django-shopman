"""A via impressa da rota da casa, com o QR do link (#2406, DEV-2026-030, decisão 2 do dono).

O papel diz o que a página do link diz no balcão, aponta o QR para o MESMO link e nunca
leva o telefone do cliente. Sem impressora nesta estação, recusa antes de carimbar.
"""

from __future__ import annotations

import base64

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from shopman.orderman.models import Order

from shopman.backstage.services import house_route_slip
from shopman.backstage.tests.test_house_couriers import _courier, _manager, _order, casa, shop  # noqa: F401
from shopman.shop.services import courier, own_fleet

pytestmark = [pytest.mark.django_db]

SLIP = "api-backstage-house-ride-slip"
PRINTS = {"can_print": True, "agent_url": "http://127.0.0.1:9100", "token": "t", "reason": ""}


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    with override_settings(SHOPMAN_STOREFRONT_BASE_URL="https://loja.test"):
        yield


@pytest.fixture
def operator(client, shop):  # noqa: F811
    user = _manager()
    client.force_login(user)
    return user


@pytest.fixture
def ride(casa):  # noqa: F811
    diego = _courier(casa, "diego", "Diego")
    a47 = _order("WEB-A47")
    c03 = _order("WEB-C03", lat=-23.305, lng=-51.165, method="cash", status="pending", total_q=7400,
                 change_for_q=10000, collection="on_delivery")
    return own_fleet.assign([a47, c03], diego, actor="operator:marina", change_out={"WEB-C03": 0},
                            note="Interfone quebrado, ligue ao chegar.")


def _printer(monkeypatch, agent):
    from shopman.backstage.api import operations

    monkeypatch.setattr(operations, "_station_device_agent", lambda request: agent)


def _text(body) -> str:
    return base64.b64decode(body["payload_b64"]).decode("cp860", "replace")


def test_slip_carries_the_route_the_note_and_the_qr_of_the_same_link(client, operator, ride, monkeypatch):
    _printer(monkeypatch, PRINTS)
    response = client.post(reverse(SLIP, args=[ride.ride_ref]))
    assert response.status_code == 200, response.json()
    body = response.json()
    text = _text(body)
    letter = courier.ride_letter(courier.get_block(Order.objects.get(ref="WEB-A47"))["ride_number"])
    assert f"ROTA {letter}" in text and "Diego leva" in text and "Via do entregador da casa" in text
    assert "2 paradas, nesta ordem" in text
    assert own_fleet._order_label(Order.objects.get(ref="WEB-A47")) in text
    assert "Pago. Não cobre nada." in text  # A47 pago no Pix
    assert "Receber em dinheiro" in text and "Paga com" in text  # C03 em dinheiro, com troco
    assert "Recado da loja: Interfone quebrado, ligue ao chegar." in " ".join(text.split())
    assert f"https://loja.test/rota/{ride.link.token}" in text  # o QR é o mesmo link
    assert "NÃO É DOCUMENTO FISCAL" in text
    assert "88887777" not in text  # o telefone do cliente não sai no papel
    assert body["reprint"] is False and body["agent"] == PRINTS
    assert body["title"] == f"via-da-rota:{ride.ride_ref}"


def test_second_print_is_marked_as_second(client, operator, ride, monkeypatch):
    _printer(monkeypatch, PRINTS)
    client.post(reverse(SLIP, args=[ride.ride_ref]))
    again = client.post(reverse(SLIP, args=[ride.ride_ref])).json()
    assert again["reprint"] is True and "*** 2a VIA ***" in _text(again)
    for ref in ("WEB-A47", "WEB-C03"):
        assert courier.get_block(Order.objects.get(ref=ref))[house_route_slip.STAMP]


def test_station_without_printer_refuses_before_stamping(client, operator, ride, monkeypatch):
    _printer(monkeypatch, {"can_print": False, "agent_url": "", "reason": "Este dispositivo não tem impressora."})
    response = client.post(reverse(SLIP, args=[ride.ride_ref]))
    assert response.status_code == 409
    assert response.json()["detail"] == "Este dispositivo não tem impressora. A via sai no dispositivo que tem impressora."
    assert house_route_slip.STAMP not in courier.get_block(Order.objects.get(ref="WEB-A47"))


def test_closed_ride_has_no_slip(client, operator, ride, monkeypatch):
    _printer(monkeypatch, PRINTS)
    from shopman.shop.services import courier_links

    courier_links.close(ride.ride_ref)
    response = client.post(reverse(SLIP, args=[ride.ride_ref]))
    assert response.status_code == 409
    assert response.json()["detail"] == "Esta corrida não é mais da casa, ou já fechou. Atualize a tela."


def test_slip_requires_the_orders_permission(client, shop, ride, monkeypatch):  # noqa: F811
    _printer(monkeypatch, PRINTS)
    client.force_login(_manager("sem", allowed=False))
    assert client.post(reverse(SLIP, args=[ride.ride_ref])).status_code == 403
