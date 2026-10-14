"""Loja: na entrega o cliente escolhe a janela, e o servidor confere contra a grade.

Decisão do dono (14/10/2026, P2-30a): a grade é a MESMA da concierge do
WhatsApp (meia hora para hoje, turno para encomenda), lida de
``fulfillment_window.delivery_windows_for``. A projeção do checkout entrega a
grade da data pedida; o commit recusa janela que a grade não oferece. Antes, o
site gravava sozinho o primeiro turno de retirada em toda entrega.

O relógio fica de fora daqui (os testes rodam a qualquer hora): a encomenda de
amanhã tem grade estável. A janela de HOJE que já passou está provada com o
relógio parado em ``shop/tests/test_delivery_window_grid.py``.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import DeliveryZone, Shop
from shopman.shop.services import fiscal
from shopman.shop.services.fulfillment_window import DELIVERY_WINDOW_UNKNOWN, delivery_windows_for
from shopman.storefront.tests._checkout_auth import authenticate_checkout
from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

ADDRESS = {
    "formatted_address": "Rua das Flores, 1 - Centro, Londrina - PR",
    "route": "Rua das Flores",
    "street_number": "1",
    "neighborhood": "Centro",
    "city": "Londrina",
    "state_code": "PR",
    "postal_code": "86050-270",
}
EVERY_DAY = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@pytest.fixture
def entrega(client, monkeypatch):
    from django.core.cache import cache

    cache.clear()  # o limite de checkouts/min é por IP e vaza entre testes
    monkeypatch.setattr(fiscal.fiscal_pool, "get_backend", lambda: Mock())
    _seed_surface()
    shop = Shop.objects.first()
    shop.opening_hours = {day: {"open": "07:00", "close": "19:00"} for day in EVERY_DAY}
    shop.save()
    authenticate_checkout(client)
    DeliveryZone.objects.create(
        shop=shop, name="Centro", zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX, match_value="860", fee_q=600,
    )
    add = client.put("/api/v1/cart/skus/PAO-FRANCES/", data={"qty": 2}, content_type="application/json")
    assert add.status_code == 200, add.content
    yield
    cache.clear()


def _tomorrow():
    return timezone.localdate() + timedelta(days=1)


def _post(client, **over):
    payload = {
        "name": "Ana",
        "phone": "+5543999990001",
        "fulfillment_type": "delivery",
        "delivery_address": ADDRESS["formatted_address"],
        "delivery_address_structured": ADDRESS,
        "delivery_date": _tomorrow().isoformat(),
        "payment_method": "cash",
    }
    payload.update(over)
    return client.post("/api/v1/checkout/", data=with_baseline(client, payload), content_type="application/json")


def test_projecao_entrega_a_grade_de_entrega_da_data_pedida(client, entrega):
    checkout = client.get(
        "/api/v1/storefront/checkout/", {"delivery_date": _tomorrow().isoformat()}
    ).json()["checkout"]

    expected = [w["ref"] for w in delivery_windows_for(_tomorrow())]
    assert expected == ["slot-09", "slot-12", "slot-15"]
    assert [w["ref"] for w in checkout["delivery_windows"]] == expected
    assert all(w["enabled"] for w in checkout["delivery_windows"])
    assert checkout["earliest_delivery_window_ref"] == "slot-09"


def test_entrega_com_janela_da_grade_vira_pedido_com_a_janela(client, entrega):
    resp = _post(client, delivery_time_slot="slot-12")

    assert resp.status_code == 201, resp.content
    order = Order.objects.get(ref=resp.json()["order_ref"])
    assert order.data["delivery_time_slot"] == "slot-12"


def test_entrega_com_janela_fora_da_grade_e_recusada_no_campo(client, entrega):
    # Meia hora numa encomenda: a grade de amanhã é de turnos.
    resp = _post(client, delivery_time_slot="14:00-14:30")

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["field"] == "delivery_time_slot"
    assert body["detail"] == DELIVERY_WINDOW_UNKNOWN
    assert not Order.objects.exists()


def test_turno_de_retirada_numa_entrega_de_hoje_e_recusado(client, entrega):
    """O que o site gravava sozinho antes: "slot-09" numa entrega de hoje."""
    resp = _post(client, delivery_date=timezone.localdate().isoformat(), delivery_time_slot="slot-09")

    assert resp.status_code == 400, resp.content
    assert resp.json()["field"] in {"delivery_time_slot", "delivery_date"}
    assert not Order.objects.exists()
