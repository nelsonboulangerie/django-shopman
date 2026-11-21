"""A seção Entregas do Gestor: o que aguarda entregador e as corridas vivas.

Usa o adapter mock da TaOn (sem rede). O número da corrida dá a cor e a LETRA dela
na tela (corrida se nomeia por letra): nasce na chamada, não muda enquanto a corrida
vive e volta a ficar livre depois.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient
from shopman.orderman.models import Order

from shopman.backstage.projections.deliveries import (
    build_deliveries,
    deliveries_waiting_count,
    deliveries_waiting_summary,
)
from shopman.shop.adapters import courier_mock
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.tests.test_courier_service import _delivery_order

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
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
        name="Nelson Boulangerie", route="Av. Madre Leônia Milito", street_number="446",
        neighborhood="Bela Suíça", city="Londrina", state_code="PR",
        formatted_address="Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR",
        latitude=-23.3405, longitude=-51.1580,
    )


def _at(ref, lat, lng, **data):
    order = _delivery_order(ref=ref, payment=data.pop("payment", PAID), **data)
    address = dict(order.data["delivery_address_structured"], latitude=lat, longitude=lng, neighborhood="Centro")
    order.data = {**order.data, "delivery_address_structured": address}
    order.save(update_fields=["data"])
    return order


def _call(*orders):
    directive = courier.request_group_dispatch(list(orders), actor="operator:ana") if len(orders) > 1 \
        else courier.request_dispatch(orders[0], actor="operator:ana")
    CourierDispatchHandler().handle(message=directive, ctx={})
    for order in orders:
        order.refresh_from_db()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_waiting_lists_deliveries_without_a_ride_with_coordinates(shop):
    _at("EN-A", -23.30, -51.16)
    _at("EN-B", -23.31, -51.17)

    deliveries = build_deliveries()

    assert deliveries.origin is not None and deliveries.origin.latitude == pytest.approx(-23.3405)
    assert [stop.ref for stop in deliveries.waiting] == ["EN-A", "EN-B"]
    first = deliveries.waiting[0]
    assert (first.latitude, first.longitude, first.place) == (-23.30, -51.16, "Centro")
    assert deliveries.rides == ()
    assert deliveries_waiting_count() == 2


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_called_ride_leaves_waiting_and_shows_as_one_ride_with_its_number(shop):
    a, b = _at("EN-A", -23.30, -51.16), _at("EN-B", -23.335, -51.158)
    alone = _at("EN-C", -23.32, -51.15)

    _call(a, b)

    deliveries = build_deliveries()
    assert [stop.ref for stop in deliveries.waiting] == ["EN-C"]
    (ride,) = deliveries.rides
    assert ride.number == 1
    assert ride.letter == "A"
    assert ride.state == "searching"
    # As paradas na ordem do percurso (a mais perto da loja primeiro).
    assert [stop.ref for stop in ride.stops] == ["EN-B", "EN-A"]
    assert courier.get_block(a)["ride_number"] == courier.get_block(b)["ride_number"] == 1

    _call(alone)
    rides = build_deliveries().rides
    assert [ride.number for ride in rides] == [1, 2]
    assert [ride.letter for ride in rides] == ["A", "B"]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_number_is_freed_when_the_ride_ends(shop):
    a = _at("EN-A", -23.30, -51.16)
    b = _at("EN-B", -23.31, -51.16)
    _call(a)
    _call(b)
    assert courier.get_block(b)["ride_number"] == 2

    # Entregue e pago antes (nada volta com o entregador): a corrida acabou.
    for status in ("A", "E", "F"):
        courier.apply_status(a, status, source="test")
        a.refresh_from_db()

    assert courier.next_ride_number() == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_ride_link_is_offered_only_when_the_ride_has_one_stop(shop):
    """O link é de UMA parada: com várias, "o link da corrida" seria o de um cliente só."""
    a, b = _at("EN-A", -23.30, -51.16), _at("EN-B", -23.335, -51.158)
    alone = _at("EN-C", -23.32, -51.15)
    _call(a, b)
    _call(alone)
    for order in (a, b, alone):
        courier.apply_status(order, "A", source="test")
        order.refresh_from_db()

    shared, single = build_deliveries().rides
    assert [stop.ref for stop in shared.stops] == ["EN-B", "EN-A"]
    # Cada pedido tem o link da própria parada gravado, e mesmo assim a corrida não oferece um.
    assert courier.proven_tracking(courier.get_block(a))["url"] != courier.proven_tracking(courier.get_block(b))["url"]
    assert shared.tracking_url == ""
    assert single.tracking_url == f"https://rastreio.mock/pedido/{courier.get_block(alone)['ride_ref']}"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_bags_sum_the_declared_volumes_and_name_who_is_missing(shop):
    a, b = _at("EN-A", -23.30, -51.16), _at("EN-B", -23.335, -51.158)
    a.data = {**a.data, "volumes": 2}
    a.save(update_fields=["data"])

    _call(a, b)

    (ride,) = build_deliveries().rides
    assert ride.bags == 2
    assert ride.undeclared == ("B",)  # o código curto do pedido, como o balcão fala


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_endpoint_answers_for_who_runs_the_board(shop):
    _at("EN-A", -23.30, -51.16)
    user = get_user_model().objects.create_user("gestor", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders"))
    client = APIClient()
    client.force_authenticate(user)

    body = client.get("/api/v1/backstage/deliveries/").json()
    count = client.get("/api/v1/backstage/deliveries/count/").json()

    assert [stop["ref"] for stop in body["waiting"]] == ["EN-A"]
    assert body["waiting"][0]["dispatch_action"]["payload_schema"]["expected_actor_id"] == user.pk
    assert count == {"waiting": 1, "call_refs": ["EN-A"]}


def test_anonymous_is_refused():
    assert APIClient().get("/api/v1/backstage/deliveries/").status_code in (401, 403)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_pickup_orders_never_show(shop):
    order = _at("EN-A", -23.30, -51.16)
    order.data = {**order.data, "fulfillment_type": "pickup"}
    order.save(update_fields=["data"])
    assert Order.objects.count() == 1
    assert build_deliveries().waiting == ()


# ── a corrida segue chamada: desistência e agrupada pela TaOn ───────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_withdrawal_shows_as_the_same_ride_looking_for_another_driver(shop):
    """O entregador desistiu: a corrida não volta para Aguardando nem pede outra chamada."""
    from shopman.backstage.projections.order_queue import _card_courier_label, _courier_block

    order = _at("EN-A", -23.30, -51.16)
    _call(order)
    courier.apply_status(order, "A", source="poll")
    order.refresh_from_db()
    assert courier.record_reopen(order, at="2026-11-16T17:32:00+00:00") == "applied"

    deliveries = build_deliveries()
    assert deliveries.waiting == ()  # segue sendo uma corrida, não um pedido a chamar
    (ride,) = deliveries.rides
    assert (ride.state, ride.status_label) == ("reopened", "Procurando outro entregador")
    assert (ride.reopened_at, ride.reopened_driver) == ("2026-11-16T17:32:00+00:00", "Entregador Mock")
    assert ride.driver is None and ride.number == 1

    order.refresh_from_db()
    block = _courier_block(order)
    assert block["status_label"] == "Procurando outro entregador"
    assert (block["reopened_at"], block["reopened_driver"]) == ("2026-11-16T17:32:00+00:00", "Entregador Mock")
    # A corrida está viva: nem "Chamar entregador", nem "Chamar de novo".
    assert block["can_dispatch"] is False and block["can_dispatch_again"] is False
    assert _card_courier_label(order) == "Procurando outro entregador"

    # Outro entregador aceitou: a corrida volta a ter dono e a frase some.
    courier.apply_status(order, "A", source="poll")
    (ride,) = build_deliveries().rides
    assert ride.state == "coming" and ride.reopened_at == ""


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_withdrawal_never_turns_into_nobody_accepted(shop):
    """A espera recomeça na desistência: não é a chamada antiga que "ninguém aceitou"."""
    from datetime import timedelta

    from django.utils import timezone

    order = _at("EN-A", -23.30, -51.16)
    _call(order)
    courier.apply_status(order, "A", source="poll")
    order.refresh_from_db()
    long_ago = (timezone.now() - timedelta(minutes=40)).isoformat()
    order.data = {**order.data, "courier": {**order.data["courier"], "called_at": long_ago, "requested_at": long_ago}}
    order.save(update_fields=["data"])
    courier.record_reopen(order)

    assert build_deliveries().rides[0].state == "reopened"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ride_grouped_by_the_provider_is_never_nobody_accepted(shop):
    """Letra U: a TaOn juntou a outra corrida, que já tem entregador. Antes virava "Ninguém aceitou ainda"."""
    from datetime import timedelta

    from django.utils import timezone

    order = _at("EN-A", -23.30, -51.16)
    _call(order)
    courier.apply_status(order, "U", source="poll")
    order.refresh_from_db()
    long_ago = (timezone.now() - timedelta(minutes=40)).isoformat()
    order.data = {**order.data, "courier": {**order.data["courier"], "called_at": long_ago, "requested_at": long_ago}}
    order.save(update_fields=["data"])

    deliveries = build_deliveries()
    assert deliveries.waiting == ()
    (ride,) = deliveries.rides
    assert (ride.state, ride.status_label) == ("grouped", "Junto com outra corrida")
    assert ride.cancel_action is None


# ── cancelar a corrida: a mesma régua e o mesmo estado do Painel do pedido ──


def _gestor():
    user = get_user_model().objects.create_user("gestor-cancel", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders"))
    return user


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancel_action_carries_the_question_and_the_reasons_only_after_accept(shop):
    a, b = _at("NB-261116-A05", -23.335, -51.158), _at("NB-261116-C12", -23.30, -51.16)
    _call(a, b)
    user = _gestor()

    ride = build_deliveries(user=user).rides[0]
    assert ride.cancel_state == ""
    assert ride.cancel_action.label == "Cancelar corrida"
    assert ride.cancel_action.confirmation == {
        "required": True,
        "description": "Cancelar a corrida A? A05 e C12 voltam para Aguardando.",
        "confirm_label": "Cancelar a corrida A",
    }

    for order in (a, b):
        courier.apply_status(order, "A", source="poll")
    ride = build_deliveries(user=user).rides[0]
    assert [reason["id"] for reason in ride.cancel_action.confirmation["reasons"]] == [12, 37, 40]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_requested_cancellation_shows_as_pending_and_takes_the_button_away(shop):
    a, b = _at("EN-A", -23.30, -51.16), _at("EN-B", -23.335, -51.158)
    _call(a, b)
    courier.cancel_ride(b, actor="operator:ana")  # pedido por qualquer pedido da corrida

    ride = build_deliveries(user=_gestor()).rides[0]
    assert ride.cancel_state == "pending"
    assert ride.cancel_message == "Pedido de cancelamento enviado. Esperando a TaOn confirmar."
    assert ride.cancel_action is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_refused_cancellation_says_so_and_matches_the_order_panel(shop, monkeypatch):
    from shopman.orderman.exceptions import DirectiveTerminalError

    from shopman.backstage.projections.order_queue import _courier_block
    from shopman.shop.adapters.courier_machine import CourierError
    from shopman.shop.handlers.courier_cancel import CourierCancelHandler

    order = _at("EN-A", -23.30, -51.16)
    _call(order)

    def refuse(courier_ref, *, reason_id):
        raise CourierError("Machine recusou (400): [67] não pode", transient=False, codes=(67,))

    monkeypatch.setattr(courier_mock, "cancel", refuse)
    task = courier.cancel_ride(order, actor="operator:ana")
    with pytest.raises(DirectiveTerminalError):
        CourierCancelHandler().handle(message=task, ctx={})

    ride = build_deliveries(user=_gestor()).rides[0]
    assert ride.cancel_state == "failed"
    assert ride.cancel_message == "A TaOn não cancelou a corrida A. Cancele pela central da TaOn."
    assert ride.cancel_action is not None  # a corrida segue aberta: dá para tentar de novo
    # Paridade: a seção Entregas e o Painel do pedido leem a mesma fonte.
    order.refresh_from_db()
    panel = _courier_block(order)["cancel_state"]
    assert (panel["state"], panel["message"]) == (ride.cancel_state, ride.cancel_message)



# ── F4a: a página Entregas sabe o mesmo que o Painel do pedido ───────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_call_without_answer_offers_call_again_never_call_alone(shop):
    """ENT-SEC-06: com a chamada sem resposta, o "Chamar sozinho" que o servidor
    recusaria some; no lugar, o "Chamar de novo" do Painel, com a mesma frase."""
    from shopman.orderman.models import Directive

    from shopman.backstage.projections.order_queue import (
        _courier_block,
        courier_dispatch_again_confirmation,
        courier_no_answer_message,
    )
    from shopman.shop.directives import COURIER_DISPATCH

    order = _at("EN-A", -23.30, -51.16)
    Directive.objects.create(topic=COURIER_DISPATCH, status="failed",
        payload={"order_ref": order.ref, "actor": "lab", "dispatch_attempt": {"state": "unknown"}})

    (stop,) = build_deliveries().waiting

    assert stop.dispatch_action is None
    assert stop.dispatch_again_action is not None
    assert stop.dispatch_again_action.ref == "courier-dispatch-again"
    assert stop.dispatch_again_action.confirmation == {
        "required": True, "description": courier_dispatch_again_confirmation("TaOn")}
    # O nome é o do serviço cadastrado (a TaOn, padrão da migração), não texto fixo (#3139).
    assert stop.error == courier_no_answer_message("TaOn")
    assert stop.error.startswith("A TaOn não respondeu")
    # Não entra em corrida com outros, e diz por quê.
    assert stop.group_refusal
    # Paridade com o Painel: a mesma condição decide os dois gestos.
    block = _courier_block(order)
    assert block["can_dispatch"] is False and block["can_dispatch_again"] is True
    assert block["error"]["message"] == stop.error


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_normal_waiting_order_offers_call_alone_and_matches_the_panel(shop):
    from shopman.backstage.projections.order_queue import _courier_block

    order = _at("EN-A", -23.30, -51.16)

    (stop,) = build_deliveries().waiting

    assert stop.dispatch_action is not None and stop.dispatch_again_action is None
    assert stop.error == "" and stop.group_refusal == ""
    block = _courier_block(order)
    assert block["can_dispatch"] is True and block["can_dispatch_again"] is False


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_ride_says_when_the_provider_stopped_answering(shop):
    """O dado parado: a mesma fonte do Painel (``courier.progress_view``)."""
    order = _at("EN-A", -23.30, -51.16)
    _call(order)
    block = courier.get_block(order)
    block["sync"] = {"failing_since": "2026-11-18T14:05:00-03:00"}
    order.data = {**order.data, "courier": block}
    order.save(update_fields=["data"])

    (ride,) = build_deliveries().rides

    assert ride.sync_since == "2026-11-18T14:05:00-03:00"
    assert courier.progress_view(courier.get_block(order))["sync_since"] == ride.sync_since


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_stop_whose_charge_changed_after_the_call_says_so(shop):
    from shopman.shop.services.order_helpers import merge_order_data

    order = _at("EN-A", -23.30, -51.16,
                payment={"method": "cash", "collection": "on_delivery", "change_for_q": 10000})
    _call(order)
    (ride,) = build_deliveries().rides
    assert ride.stops[0].charge_outdated is None

    merge_order_data(order, {"payment": {"method": "cash", "collection": "on_delivery", "change_for_q": 5000}})
    order.refresh_from_db()

    (ride,) = build_deliveries().rides
    assert ride.stops[0].charge_outdated == courier.charge_outdated(order)
    assert ride.stops[0].charge_outdated["collected"] is False


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_waiting_brings_the_house_suggestion_and_the_badge_never_asks_the_central(shop):
    _at("EN-A", -23.310, -51.160)
    _at("EN-B", -23.305, -51.160)

    plan = build_deliveries().ride_plan

    [suggestion] = plan.suggestions
    assert suggestion.refs == ("EN-A", "EN-B")
    assert suggestion.places == "Centro"
    assert (suggestion.quoted, suggestion.suggested) == (True, True)
    assert (suggestion.together_q, suggestion.separate_q, suggestion.saving_q) == (1650, 2500, 850)
    assert suggestion.late_code == "B" and suggestion.late_minutes >= 1
    # O selo do menu nunca monta o plano (nem pergunta à central).
    from unittest import mock

    from shopman.shop.services import ride_plan
    with mock.patch.object(ride_plan, "ride_plan", side_effect=AssertionError("o selo montou o plano")):
        assert deliveries_waiting_count() == 2


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_card_call_refs_are_the_ready_ones_that_can_be_called_now(shop):
    """O "Chamar entregador" do cartão Pronto (#2876): só o pronto que aguarda e dá
    para chamar agora; o em preparo conta no selo, a corrida na rua não aparece."""
    _at("EN-PRONTO", -23.30, -51.16)
    _at("EN-PREPARO", -23.30, -51.17, status=Order.Status.PREPARING)
    _call(_at("EN-RUA", -23.31, -51.16))

    summary = deliveries_waiting_summary()

    assert summary == {"waiting": 2, "call_refs": ["EN-PRONTO"]}


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_card_call_refs_skip_a_call_without_answer(shop):
    """Chamada sem resposta da central trava outra: o cartão não oferece chamar."""
    from shopman.orderman.models import Directive

    from shopman.shop.directives import COURIER_DISPATCH

    order = _at("EN-A", -23.30, -51.16)
    _at("EN-B", -23.30, -51.17)
    Directive.objects.create(topic=COURIER_DISPATCH, status="failed",
        payload={"order_ref": order.ref, "actor": "lab", "dispatch_attempt": {"state": "unknown"}})

    assert deliveries_waiting_summary() == {"waiting": 2, "call_refs": ["EN-B"]}
