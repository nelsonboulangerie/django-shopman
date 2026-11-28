"""O plano das corridas (``ride_plan``): quem a casa sugere juntar, e quando já vem marcado.

A régua é a do desenho do juiz (revisão das Entregas, seção 4) com os parâmetros do dono
(16/11/2026): desvio de até 2,5 km (e 40% da maior perna), o último cliente espera no
máximo 10 min a mais, e só vem marcada com tudo cotado e economia de R$ 3,00 e de 15%.
"""

from __future__ import annotations

from unittest import mock

import pytest
from django.core.cache import cache
from django.test import override_settings
from shopman.orderman.models import Order

from shopman.shop.adapters import courier_mock
from shopman.shop.models import Shop
from shopman.shop.models.delivery_service import DeliveryService
from shopman.shop.services import courier, ride_plan
from shopman.shop.services.ride_plan import Candidate, plan_groups
from shopman.shop.tests.test_courier_service import _delivery_order

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
STORE = (-23.3405, -51.1580)
SETTINGS = {"detour_km": 2.5, "saving_min_q": 300, "saving_min_percent": 15, "extra_wait_minutes": 10}
PAID = {"method": "pix", "status": "captured"}


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Loja", route="Av. Central", street_number="446", neighborhood="Centro", city="Londrina",
        state_code="PR", formatted_address="Av. Central, 446", latitude=STORE[0], longitude=STORE[1],
    )


def _at(ref, lat, lng, *, neighborhood="Centro", **data):
    order = _delivery_order(ref=ref, payment=data.pop("payment", PAID), **data)
    address = dict(order.data["delivery_address_structured"], latitude=lat, longitude=lng, neighborhood=neighborhood)
    order.data = {**order.data, "delivery_address_structured": address}
    order.save(update_fields=["data"])
    return order


# ── a régua pura ─────────────────────────────────────────────────────────


def test_neighbours_ride_together_and_the_opposite_side_does_not():
    # A e B a ~0,5 km um do outro, ao norte; C do outro lado da loja, ao sul.
    a = Candidate("A", -23.310, -51.160, ready_key=1)
    b = Candidate("B", -23.305, -51.160, ready_key=2)
    c = Candidate("C", -23.370, -51.158, ready_key=3)

    groups = plan_groups(STORE, [a, b, c], SETTINGS, max_stops=4)

    assert [group.refs for group in groups] == [("A", "B")]
    # B fica por último na rota, e espera só o trecho a mais e a parada de A.
    assert groups[0].late_ref == "B"
    assert 1 <= groups[0].late_minutes <= 10


def test_detour_over_the_limit_is_not_suggested():
    # Dois pedidos à mesma distância da loja, mas a 3 km um do outro.
    a = Candidate("A", -23.310, -51.145, ready_key=1)
    b = Candidate("B", -23.310, -51.175, ready_key=2)
    assert plan_groups(STORE, [a, b], SETTINGS, max_stops=4) == []
    # Com o desvio do Admin mais largo, o par passa pelo desvio, e a espera ainda segura.
    assert plan_groups(STORE, [a, b], {**SETTINGS, "detour_km": 10}, max_stops=4) == []
    loose = {**SETTINGS, "detour_km": 10, "extra_wait_minutes": 60}
    assert plan_groups(STORE, [a, b], loose, max_stops=4) == []  # 40% da maior perna ainda segura


def test_the_oldest_ready_pulls_its_neighbours_up_to_the_stop_limit():
    stops = [Candidate(ref, -23.310 + k * 0.001, -51.160, ready_key=k) for k, ref in enumerate("ABCDE")]
    groups = plan_groups(STORE, stops, {**SETTINGS, "extra_wait_minutes": 30}, max_stops=4)
    assert len(groups[0].refs) == 4
    assert "A" in groups[0].refs
    # O quinto fica para a próxima sugestão, e sozinho não é sugestão.
    assert all("E" not in group.refs for group in groups)


def test_a_pair_that_would_land_after_the_window_is_not_suggested():
    # A e B vizinhos (o par cabe no desvio e na espera). B fica por último na rota.
    a = Candidate("A", -23.310, -51.160, ready_key=1)
    b = Candidate("B", -23.305, -51.160, ready_key=2)
    alone = ride_plan.km_between(STORE, (b.latitude, b.longitude)) / ride_plan.SPEED_KMH * 3600
    # A janela de B fecha 30 s depois de ele chegar sozinho: junto, com o trecho a mais e
    # a parada de A, passaria do fim. O par não vira sugestão.
    tight = Candidate("B", b.latitude, b.longitude, ready_key=2, deadline=alone + 30)
    assert plan_groups(STORE, [a, tight], SETTINGS, max_stops=4, now=0) == []
    # Com folga para os dois minutos da parada e o desvio, junta.
    roomy = Candidate("B", b.latitude, b.longitude, ready_key=2, deadline=alone + 20 * 60)
    assert [group.refs for group in plan_groups(STORE, [a, roomy], SETTINGS, max_stops=4, now=0)] == [("A", "B")]
    # Sem relógio (a régua pura), o prazo não é medido.
    assert [group.refs for group in plan_groups(STORE, [a, tight], SETTINGS, max_stops=4)] == [("A", "B")]


def test_who_is_late_even_alone_does_not_block_the_pair():
    a = Candidate("A", -23.310, -51.160, ready_key=1)
    late = Candidate("B", -23.305, -51.160, ready_key=2, deadline=-60)
    assert [group.refs for group in plan_groups(STORE, [a, late], SETTINGS, max_stops=4, now=0)] == [("A", "B")]


def test_params_come_from_the_admin_over_the_owner_guesses(shop):
    assert ride_plan.params(shop) == SETTINGS
    shop.defaults = {"delivery": {"ride_suggestion": {"detour_km": 1.5, "saving_min_q": 500, "extra_wait_minutes": "x"}}}
    assert ride_plan.params(shop) == {**SETTINGS, "detour_km": 1.5, "saving_min_q": 500}


# ── o plano, com a central ────────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_quoted_and_cheaper_together_comes_marked(shop):
    a = _at("CR-A", -23.310, -51.160)
    b = _at("CR-B", -23.305, -51.160)

    plan = ride_plan.ride_plan([a, b])

    [suggestion] = plan["suggestions"]
    assert suggestion["refs"] == ["CR-A", "CR-B"]
    assert suggestion["codes"] == ["A", "B"]
    assert suggestion["quoted"] is True
    assert suggestion["suggested"] is True
    # O mock cota R$ 12,50 sozinho e +R$ 4,00 por parada a mais.
    assert suggestion["together"]["value_q"] == 1650
    assert suggestion["separate_q"] == 2500
    assert suggestion["saving_q"] == 850
    assert suggestion["late_code"] == "B"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_quoted_without_the_minimum_saving_is_not_a_suggestion(shop):
    shop.defaults = {"delivery": {"ride_suggestion": {"saving_min_q": 1000}}}
    shop.save()
    a, b = _at("CR-A", -23.310, -51.160), _at("CR-B", -23.305, -51.160)
    assert ride_plan.ride_plan([a, b])["suggestions"] == []


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_without_every_quote_the_suggestion_shows_unmarked(shop):
    a, b = _at("CR-A", -23.310, -51.160), _at("CR-B", -23.305, -51.160)
    with mock.patch.object(courier, "estimate_for_order", side_effect=[{"value_q": 1250, "km": 4.2}, None]):
        [suggestion] = ride_plan.ride_plan([a, b])["suggestions"]
    assert suggestion["quoted"] is False
    assert suggestion["suggested"] is False
    assert suggestion["together"] is None
    assert suggestion["saving_q"] is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_together_quote_shorter_than_one_alone_fails_the_sanity_check(shop):
    a, b = _at("CR-A", -23.310, -51.160), _at("CR-B", -23.305, -51.160)
    with mock.patch.object(courier, "estimate_for_order", return_value={"value_q": 2000, "km": 9.0}):
        assert ride_plan.ride_plan([a, b])["suggestions"] == []


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_an_order_still_in_preparation_never_enters(shop):
    a = _at("CR-A", -23.310, -51.160)
    b = _at("CR-B", -23.305, -51.160)
    Order.objects.filter(pk=b.pk).update(status=Order.Status.PREPARING)
    b.refresh_from_db()
    assert ride_plan.ride_plan([a, b])["suggestions"] == []


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_plan_is_cached_for_a_minute_by_orders_and_revisions(shop):
    a, b = _at("CR-A", -23.310, -51.160), _at("CR-B", -23.305, -51.160)
    first = ride_plan.ride_plan([a, b])
    with mock.patch.object(courier, "estimate_for_ride", side_effect=AssertionError("cotou de novo")):
        assert ride_plan.ride_plan([a, b]) == first


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_plan_carries_the_service_the_admin_marks_as_default(shop):
    DeliveryService.objects.update(is_default=False)
    DeliveryService.objects.update_or_create(
        ref="central-f5", defaults={"name": "Central", "kind": DeliveryService.KIND_MACHINE, "is_default": True})
    DeliveryService.objects.update_or_create(
        ref="casa-f5", defaults={"name": "Entregadores da casa", "kind": DeliveryService.KIND_OWN_FLEET})
    a, b = _at("CR-A", -23.310, -51.160), _at("CR-B", -23.305, -51.160)

    plan = ride_plan.ride_plan([a, b])

    assert plan["service"] == "central-f5"
    assert plan["service_reason"] == "default"
    assert {"central-f5", "casa-f5"} <= {option["ref"] for option in plan["service_options"]}


def test_without_a_courier_service_there_is_no_plan(shop):
    a, b = _at("CR-A", -23.310, -51.160), _at("CR-B", -23.305, -51.160)
    with override_settings(SHOPMAN_COURIER_ADAPTER=None):
        assert ride_plan.ride_plan([a, b])["suggestions"] == []


def test_admin_edits_the_four_params_and_saves_only_what_differs(shop):
    from shopman.shop.admin.shop import _ORDERING_FIELDSETS, ShopForm
    from shopman.shop.tests.test_admin import _shop_form_data

    names = ("defaults_delivery_ride_detour_km", "defaults_delivery_ride_saving_min_q",
             "defaults_delivery_ride_saving_min_percent", "defaults_delivery_ride_extra_wait_minutes")
    fields = [f for _, opts in _ORDERING_FIELDSETS for row in opts["fields"]
              for f in (row if isinstance(row, tuple) else (row,))]
    assert set(names) <= set(fields)

    data = _shop_form_data(shop)
    data.update({names[0]: "1.5", names[1]: "5.00", names[2]: "20", names[3]: "8"})
    form = ShopForm(data=data, instance=shop)
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.defaults["delivery"]["ride_suggestion"] == {
        "detour_km": 1.5, "saving_min_q": 500, "saving_min_percent": 20, "extra_wait_minutes": 8}
    assert ride_plan.params(saved) == {"detour_km": 1.5, "saving_min_q": 500, "saving_min_percent": 20,
                                       "extra_wait_minutes": 8}
    assert ShopForm(instance=saved).fields[names[1]].initial == 5

    data = _shop_form_data(saved)
    data.update(dict.fromkeys(names, ""))
    form = ShopForm(data=data, instance=saved)
    assert form.is_valid(), form.errors
    assert "ride_suggestion" not in (form.save().defaults.get("delivery") or {})


# ── o prazo combinado no plano (#2875) ────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_half_hour_that_closes_now_keeps_the_order_out_of_the_pair(shop):
    from datetime import timedelta

    from django.utils import timezone

    now = timezone.localtime()
    # A janela de B fecha um minuto e meio depois de ele chegar sozinho (a hora cheia
    # arredonda para baixo: entre meio e um minuto e meio de folga). Junto, a parada de
    # A custa dois minutos e passa do fim.
    alone = ride_plan.km_between(STORE, (-23.305, -51.160)) / ride_plan.SPEED_KMH * 60
    end = now + timedelta(minutes=alone + 1.5)
    start = end - timedelta(minutes=30)
    if start.date() != now.date() or end.date() != now.date():
        pytest.skip("a meia hora atravessa a meia-noite")
    slot = f"{start:%H:%M}-{end:%H:%M}"
    a = _at("CR-A", -23.310, -51.160)
    b = _at("CR-B", -23.305, -51.160, delivery_time_slot=slot, delivery_date=now.date().isoformat())
    assert ride_plan.ride_plan([a, b], quote=False)["suggestions"] == []


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_order_shift_has_no_end_and_does_not_limit(shop):
    from django.utils import timezone

    a = _at("CR-A", -23.310, -51.160)
    b = _at("CR-B", -23.305, -51.160, delivery_time_slot="slot-09",
            delivery_date=timezone.localdate().isoformat())
    [suggestion] = ride_plan.ride_plan([a, b], quote=False)["suggestions"]
    assert suggestion["refs"] == ["CR-A", "CR-B"]
