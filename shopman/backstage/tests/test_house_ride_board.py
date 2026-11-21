"""A corrida da casa na coluna Saída dos Pedidos (DEV-2026-030, frente M3d, #2937).

A coluna lê as corridas pela mesma API da página Entregas, sem o plano das corridas
(``?plan=0``: o plano pergunta à central, e a coluna só quer saber das corridas da casa).
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.urls import reverse

from shopman.backstage.tests.test_house_couriers import _courier, _manager, _order, casa, shop  # noqa: F401
from shopman.shop.services import own_fleet

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


def test_board_reads_house_rides_without_the_plan(client, operator, casa, monkeypatch):  # noqa: F811
    diego = _courier(casa, "diego", "Diego")
    ride = own_fleet.assign([_order("WEB-A47"), _order("WEB-C03", lat=-23.305, lng=-51.165)], diego,
                            actor="operator:marina")

    from shopman.backstage.projections import deliveries

    asked = []
    monkeypatch.setattr(deliveries, "_ride_plan", lambda *args, **kwargs: asked.append(1) or None)
    body = client.get(reverse("api-backstage-deliveries"), {"plan": "0"}).json()
    assert body["ride_plan"] is None and asked == []  # sem perguntar à central
    row = next(item for item in body["rides"] if item["key"] == ride.ride_ref)
    assert row["house"]["courier_name"] == "Diego" and row["house"]["moment"] == "Diego leva"
    assert [stop["ref"] for stop in row["stops"]] == ["WEB-A47", "WEB-C03"]
    assert row["driver"]["phone"]  # o "Ligar para Diego" do cartão


def test_deliveries_page_still_reads_the_plan_by_default(client, operator, casa, monkeypatch):  # noqa: F811
    from shopman.backstage.projections import deliveries

    asked = []
    monkeypatch.setattr(deliveries, "_ride_plan", lambda *args, **kwargs: asked.append(1) or None)
    client.get(reverse("api-backstage-deliveries"))
    assert asked == [1]
