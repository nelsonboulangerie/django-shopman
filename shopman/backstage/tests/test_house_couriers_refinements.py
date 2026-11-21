"""Quem leva, os refinamentos (DEV-2026-030, frente M3c, #2899).

A hora da volta no chip de quem está na rua, a observação da casa que chega à página do
link, e a página Entregas que funciona só com os entregadores da casa (TaOn desligada).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.backstage.projections.deliveries import build_deliveries
from shopman.backstage.services import house_couriers
from shopman.backstage.tests.test_house_couriers import (  # noqa: F401
    CREW,
    _courier,
    _manager,
    _order,
    _send,
    casa,
    shop,
)
from shopman.shop.models import CourierLink
from shopman.shop.services import courier, courier_links, own_fleet

pytestmark = [pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield


@pytest.fixture
def operator(client, shop):  # noqa: F811
    user = _manager()
    client.force_login(user)
    return user


def _link(ride_ref):
    return CourierLink.objects.get(ride_ref=ride_ref, revoked_at__isnull=True)


# ── a hora da volta ─────────────────────────────────────────────────────────


def test_courier_on_the_road_shows_when_he_is_back(client, operator, casa):  # noqa: F811
    diego = _courier(casa, "diego", "Diego")
    ride = own_fleet.assign([_order("WEB-A47")], diego, actor="operator:marina")
    row = client.get(reverse(CREW)).json()["couriers"][0]
    assert (row["state"], row["state_label"], row["back_at"]) == ("busy", "Na rua", None)  # ainda na loja

    own_fleet.depart(ride.link)
    row = client.get(reverse(CREW)).json()["couriers"][0]
    back = house_couriers.back_at([Order.objects.get(ref="WEB-A47")])
    assert back is not None and back > timezone.now()
    assert row["state_label"] == f"Volta {timezone.localtime(back).strftime('%Hh%M')}"
    assert row["back_at"] == back.isoformat()


def test_back_label_when_the_hour_passed_and_without_hour():
    assert house_couriers.busy_label(None) == "Na rua"
    assert house_couriers.busy_label(timezone.now() - timedelta(minutes=1)) == "Voltando"
    later = timezone.now() + timedelta(minutes=20)
    assert house_couriers.busy_label(later) == f"Volta {timezone.localtime(later).strftime('%Hh%M')}"


# ── a observação para o entregador ──────────────────────────────────────────


def test_note_goes_with_the_ride_to_the_link_page(client, operator, casa):  # noqa: F811
    _courier(casa, "diego", "Diego")
    a47 = _order("WEB-A47")
    response = _send(client, operator, [a47], note="  Interfone quebrado, ligue ao chegar.  ")
    assert response.status_code == 200, response.json()
    a47.refresh_from_db()
    assert courier.get_block(a47)["note"] == "Interfone quebrado, ligue ao chegar."
    link = _link(response.json()["ride_ref"])
    courier_links.claim(link.token, "c" * 32)
    view = own_fleet.ride_view(_link(link.ride_ref))
    assert view["note"] == "Interfone quebrado, ligue ao chegar."


def test_ride_without_note_has_no_note_key(client, operator, casa):  # noqa: F811
    _courier(casa, "diego", "Diego")
    a47 = _order("WEB-A47")
    ride_ref = _send(client, operator, [a47]).json()["ride_ref"]
    a47.refresh_from_db()
    assert "note" not in courier.get_block(a47)
    assert "note" not in own_fleet.ride_view(_link(ride_ref))


def test_note_too_long_is_refused_with_the_field(client, operator, casa):  # noqa: F811
    _courier(casa, "diego", "Diego")
    response = _send(client, operator, [_order("WEB-A47")], note="x" * 201)
    assert response.status_code == 400 and response.json()["field"] == "note"
    assert response.json()["detail"] == "A observação cabe em até 200 caracteres."


# ── a página só com a casa ──────────────────────────────────────────────────


def test_deliveries_work_with_the_house_alone(operator, casa):  # noqa: F811
    _order("WEB-A47")
    projection = build_deliveries(user=operator)
    assert projection.courier_on is False  # TaOn não configurada nos testes
    assert projection.house_on is True
    stop = next(item for item in projection.waiting if item.ref == "WEB-A47")
    assert stop.dispatch_action is not None and stop.dispatch_action.payload_schema["base_revision"]


def test_without_house_nor_taon_the_page_only_informs(operator, casa):  # noqa: F811
    casa.is_active = False
    casa.save(update_fields=["is_active"])
    _order("WEB-A47")
    projection = build_deliveries(user=operator)
    assert projection.courier_on is False and projection.house_on is False
    assert all(stop.dispatch_action is None for stop in projection.waiting)
