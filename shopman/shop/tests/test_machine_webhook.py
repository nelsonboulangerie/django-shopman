"""Webhook Machine: auth fail-closed (token + Signature-V2), idempotência e transições via funil."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient
from shopman.orderman.models import Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import courier_mock
from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.webhooks.machine import signature_for

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
API_KEY = "chave-da-api-machine"
MACHINE = {"webhook_token": "tok-machine-1", "api_key": API_KEY}


class SignedClient(APIClient):
    """Cliente que assina como a Machine: ``Signature-V2`` = HMAC-SHA-512 do corpo."""

    def post(self, path, data=None, format=None, content_type=None, **extra):
        body = json.dumps(data if data is not None else {}).encode("utf-8")
        extra.setdefault("HTTP_SIGNATURE_V2", signature_for(body, API_KEY))
        return super().post(path, body, content_type="application/json", **extra)


def _client() -> APIClient:
    return SignedClient()


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Nelson",
        city="Londrina",
        state_code="PR",
        latitude=-23.34,
        longitude=-51.15,
    )


def _order_with_ride(ref="WH-1") -> Order:
    order = Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"S-{ref}",
        status=Order.Status.READY,
        snapshot={"items": []},
        data={
            "fulfillment_type": "delivery",
            "customer": {"name": "Ana", "phone": "5543999990000"},
            "delivery_address_structured": {"latitude": -23.31, "longitude": -51.16},
            "courier": {
                "provider": "machine",
                "id_mch": "184532",
                "status": "D",
                "requested_at": "2026-07-07T10:00:00-03:00",
            },
        },
        total_q=5000,
    )
    courier_mock.dispatch({"paradas": [{"id_externo": ref}]})  # popula o mock p/ get_details
    courier_mock.rides()["184532"] = courier_mock.rides().pop(f"MOCK-{ref}")
    return order


def _url(token="tok-machine-1"):
    url = reverse("webhooks:machine-webhook")
    return f"{url}?token={token}" if token else url


# ── autenticação ────────────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_rejects_without_token():
    resp = _client().post(_url(token=""), {"id_mch": "1", "status": "E"}, format="json")
    assert resp.status_code == 401


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_rejects_wrong_token():
    resp = _client().post(_url(token="errado"), {"id_mch": "1", "status": "E"}, format="json")
    assert resp.status_code == 401


@override_settings(SHOPMAN_MACHINE={"webhook_token": ""})
def test_rejects_everything_when_token_unconfigured():
    # Fail-closed: sem token configurado o endpoint rejeita até o token "vazio".
    resp = _client().post(_url(token=""), {}, format="json")
    assert resp.status_code == 401


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_accepts_token_via_header():
    client = _client()
    resp = client.post(
        reverse("webhooks:machine-webhook"),
        {"foo": "bar"},
        format="json",
        HTTP_X_MACHINE_WEBHOOK_TOKEN="tok-machine-1",
    )
    assert resp.status_code == 202  # autenticado; payload não reconhecido


# ── Signature-V2 (HMAC-SHA-512 do corpo com a chave da API) ─────────


def _raw_post(body: bytes, **headers):
    return APIClient().post(_url(), body, content_type="application/json", **headers)


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_valid_signature_over_the_raw_body_is_accepted():
    # Bytes exatos, com espaços que um re-serializador mudaria: a conta é sobre o corpo cru.
    body = b'{"algo":  "desconhecido" }'
    resp = _raw_post(body, HTTP_SIGNATURE_V2=signature_for(body, API_KEY))
    assert resp.status_code == 202


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_uppercase_hex_signature_is_accepted():
    body = b'{"algo": "desconhecido"}'
    resp = _raw_post(body, HTTP_SIGNATURE_V2=signature_for(body, API_KEY).upper())
    assert resp.status_code == 202


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_invalid_signature_is_rejected_and_touches_nothing(shop):
    order = _order_with_ride()
    body = json.dumps({"id_mch": "184532", "status": "E"}).encode()
    forged = signature_for(body, "outra-chave")
    resp = _raw_post(body, HTTP_SIGNATURE_V2=forged)
    assert resp.status_code == 401
    order.refresh_from_db()
    assert order.status == Order.Status.READY
    assert OperatorAlert.objects.filter(type="webhook_failed").exists()


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_signature_of_another_body_is_rejected():
    signed = b'{"id_mch": "184532", "status": "E"}'
    sent = b'{"id_mch": "184532", "status": "F"}'
    resp = _raw_post(sent, HTTP_SIGNATURE_V2=signature_for(signed, API_KEY))
    assert resp.status_code == 401


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_missing_signature_is_rejected_even_with_the_right_token():
    resp = _raw_post(b'{"algo": "desconhecido"}')
    assert resp.status_code == 401


@override_settings(SHOPMAN_MACHINE={"webhook_token": "tok-machine-1", "api_key": ""})
def test_without_api_key_every_post_is_rejected_loudly():
    # Falha fechada e gritando: sem a chave não há o que conferir, e ninguém é aceito calado.
    from shopman.shop.webhooks import machine

    body = b'{"algo": "desconhecido"}'
    with patch.object(machine.logger, "error") as error:
        resp = _raw_post(body, HTTP_SIGNATURE_V2=signature_for(body, ""))
    assert resp.status_code == 401
    assert "MACHINE_API_KEY" in error.call_args.args[0]
    assert OperatorAlert.objects.filter(type="webhook_failed").exists()


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_registration_probe_get_needs_only_the_token():
    assert APIClient().get(_url()).status_code == 200
    assert APIClient().get(_url(token="errado")).status_code == 401


# ── payload defensivo ───────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_unrecognized_payload_is_accepted_not_rejected():
    resp = _client().post(_url(), {"algo": "desconhecido"}, format="json")
    assert resp.status_code == 202
    assert resp.data["status"] == "unrecognized"


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_unknown_ride_returns_ok(shop):
    resp = _client().post(_url(), {"id_mch": "999999", "status": "E"}, format="json")
    assert resp.status_code == 200
    assert resp.data["kind"] == "unknown_ride"


# ── eventos de status ───────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_status_e_advances_order_to_dispatched(shop):
    order = _order_with_ride()
    resp = _client().post(_url(), {"id_mch": "184532", "status": "E"}, format="json")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    assert courier.get_block(order)["status"] == "E"
    assert courier.get_block(order)["last_source"] == "webhook"


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_status_f_marks_delivered(shop):
    order = _order_with_ride()
    client = _client()
    client.post(_url(), {"id_mch": "184532", "status": "E"}, format="json")
    resp = client.post(_url(), {"id_mch": "184532", "status": "F"}, format="json")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED)


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_status_n_alerts_operator(shop):
    order = _order_with_ride()
    resp = _client().post(_url(), {"id_mch": "184532", "status": "N"}, format="json")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert not courier.has_active_ride(order)
    assert OperatorAlert.objects.filter(type="courier_not_attended", order_ref=order.ref).exists()


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_replay_same_status_is_noop(shop):
    order = _order_with_ride()
    client = _client()
    first = client.post(_url(), {"id_mch": "184532", "status": "E"}, format="json")
    assert first.data["kind"] == "status"
    replay = client.post(_url(), {"id_mch": "184532", "status": "E"}, format="json")
    assert replay.status_code == 200
    assert replay.data["kind"] == "replay"
    order.refresh_from_db()
    assert order.events.filter(type="courier_status").count() == 1


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_alternate_id_and_status_keys_are_understood(shop):
    order = _order_with_ride()
    resp = _client().post(
        _url(), {"solicitacao_id": 184532, "situacao": "e"}, format="json"
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED


# ── eventos de posição ──────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_position_event_goes_to_cache_not_order(shop):
    order = _order_with_ride()
    before = order.updated_at
    resp = _client().post(
        _url(), {"id_mch": "184532", "lat": "-23.305", "lng": "-51.162"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["kind"] == "position"
    assert cache.get("courier:pos:184532") == {"lat": "-23.305", "lng": "-51.162"}
    order.refresh_from_db()
    assert order.updated_at == before  # posição nunca escreve no Order


# ── formato documentado (docs.machine.global, v1 entregas, "Webhooks > Sobre") ──


def _documented_status(code, label):
    return {
        "datetime": "2026-10-01T13:20:05Z",
        "event_id": "550e8400-e29b-41d4-a716-446655440000",
        "company_id": 8,
        "request_id": 184532,
        "status_code": code,
        "status_label": label,
        "links": {"request": "https://api.taximachine.com.br/api/v1/request/184532"},
    }


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_documented_status_payload_advances_the_order(shop):
    order = _order_with_ride()
    resp = _client().post(_url(), _documented_status("E", "IN_PROGRESS"), format="json")
    assert resp.status_code == 200
    assert resp.data["kind"] == "status"
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    assert courier.get_block(order)["status"] == "E"


@pytest.mark.parametrize(("code", "label"), [("AP", "ARRIVED_AT_LOCATION"), ("ER", "STOP_FINISHED")])
@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_documented_event_that_is_not_a_state_keeps_the_ride_letter(shop, code, label):
    order = _order_with_ride()
    resp = _client().post(_url(), _documented_status(code, label), format="json")
    assert resp.status_code == 200
    assert resp.data["kind"] == "event"
    order.refresh_from_db()
    assert courier.get_block(order)["status"] == "D"


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_status_push_asks_for_a_full_reading_now(shop):
    """O aviso traz só a letra: o entregador e a previsão vêm da batida, já."""
    from django.utils import timezone
    from shopman.orderman.models import Directive

    from shopman.shop.directives import COURIER_SYNC

    order = _order_with_ride()
    _client().post(_url(), _documented_status("A", "ACCEPTED"), format="json")
    sync = Directive.objects.get(topic=COURIER_SYNC, payload__order_ref=order.ref, status=Directive.Status.QUEUED)
    assert sync.available_at <= timezone.now()
    order.refresh_from_db()
    assert courier.get_block(order)["driver"]["name"] == "Entregador Mock"  # detalhes buscados, não o corpo do aviso


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_arrival_event_marks_the_driver_at_the_shop(shop):
    order = _order_with_ride()
    courier.apply_status(order, "A", source="poll")
    resp = _client().post(_url(), _documented_status("AP", "ARRIVED_AT_LOCATION"), format="json")
    assert resp.data["kind"] == "event"
    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["status"] == "A"
    assert block["progress"]["arrived_pickup_at"] == "2026-10-01T13:20:05Z"

    courier.apply_status(order, "E", source="poll")
    order.refresh_from_db()
    _client().post(_url(), _documented_status("AP", "ARRIVED_AT_LOCATION"), format="json")
    order.refresh_from_db()
    assert courier.get_block(order)["progress"]["arrived_dropoff_at"] == "2026-10-01T13:20:05Z"


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_documented_position_batch_goes_to_cache(shop):
    batch = {
        "event_id": "01a01e79-080c-7d22-bdf6-432b1ba40c44",
        "datetime": "2026-10-01T17:00:00Z",
        "data": [
            {"timestamp": 1786381200000, "company_id": 8, "request_id": 184532, "driver_id": 8101,
             "coordinates": {"latitude": -23.305, "longitude": -51.162}},
            {"timestamp": 1786381200000, "company_id": 8, "request_id": 184533, "driver_id": 8102},
        ],
    }
    resp = _client().post(_url(), batch, format="json")
    assert resp.status_code == 200
    assert resp.data == {"status": "ok", "kind": "position_batch", "positions": 1}
    assert cache.get("courier:pos:184532") == {"lat": "-23.305", "lng": "-51.162"}
    assert cache.get("courier:pos:184533") is None


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_deprecated_position_payload_goes_to_cache(shop):
    resp = _client().post(
        _url(), {"id_mch": "184532", "condutor_id": "9", "lat_cond": "-23.3", "lng_cond": "-51.1"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["kind"] == "position"
    assert cache.get("courier:pos:184532") == {"lat": "-23.3", "lng": "-51.1"}


# ── desistência do entregador: a TaOn reabre a MESMA corrida ─────────


def _event(code, *, event_id, at, **extra):
    """Um aviso de status no formato documentado: um ``event_id`` por fato."""
    return {"datetime": at, "event_id": event_id, "company_id": 8, "request_id": 184532,
            "status_code": code, "status_label": code, **extra}


def _accepted_order(ref="WH-1") -> Order:
    order = _order_with_ride(ref)
    _client().post(_url(), _event("A", event_id="evt-aceite-1", at="2026-10-01T14:14:00Z"), format="json")
    order.refresh_from_db()
    assert courier.get_block(order)["driver"]["name"] == "Entregador Mock"
    return order


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_driver_withdrawal_with_will_reopen_keeps_the_same_ride(shop):
    """``C`` com ``will_reopen``: a TaOn redistribui sozinha. "Não abra outra solicitação."

    Antes o ``C`` arquivava a corrida, tirava o ``id_mch``, avisava "chame o
    entregador de novo" e devolvia a custódia: dois entregadores, duas corridas pagas.
    """
    order = _accepted_order()
    with patch("shopman.shop.services.courier._return_custody") as returned:
        resp = _client().post(
            _url(), _event("C", event_id="evt-desistiu-1", at="2026-10-01T14:32:00Z", will_reopen=True), format="json",
        )
    assert resp.status_code == 200
    assert resp.data["kind"] == "reopened"

    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["id_mch"] == "184532"  # a MESMA corrida, ainda chamada
    assert block["status"] == "D"
    assert "driver" not in block
    assert "attempts" not in block  # nada foi arquivado
    assert block["reopens"] == [{"at": "2026-10-01T14:32:00Z", "driver": "Entregador Mock", "source": "webhook",
                                 "accepted_at": "2026-10-01T14:14:00Z"}]
    assert "A" not in block["status_at"]  # o próximo aceite registra a própria hora
    assert courier.has_active_ride(order)
    returned.assert_not_called()  # o troco e a maquininha seguem separados
    assert not OperatorAlert.objects.filter(order_ref=order.ref, type__in=("courier_ride_cancelled", "courier_not_attended")).exists()
    assert order.events.filter(type="courier_ride_reopened").count() == 1
    assert courier.reopen_view(block) == {"at": "2026-10-01T14:32:00Z", "driver": "Entregador Mock"}


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_second_driver_acceptance_is_a_new_fact_not_a_replay(shop):
    """A chave antiga (corrida + letra) descartava o ``A`` do novo entregador como repetição."""
    order = _accepted_order()
    client = _client()
    client.post(_url(), _event("C", event_id="evt-desistiu-1", at="2026-10-01T14:32:00Z", will_reopen=True), format="json")
    courier_mock.set_driver("184532", {"name": "Léo", "phone": "(43) 99124-5580",
                                        "vehicle_plate": "BRA2E19", "vehicle_model": "Moto preta"})
    resp = client.post(_url(), _event("A", event_id="evt-aceite-2", at="2026-10-01T14:36:00Z"), format="json")
    assert resp.data["kind"] == "status"

    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["status"] == "A"
    assert block["driver"]["name"] == "Léo"
    assert block["status_at"]["A"] == "2026-10-01T14:36:00Z"
    assert courier.reopen_view(block) == {"at": "", "driver": ""}  # a corrida voltou a ter dono


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_plain_cancellation_without_will_reopen_still_ends_the_ride(shop):
    order = _accepted_order()
    resp = _client().post(_url(), _event("C", event_id="evt-cancelou", at="2026-10-01T14:32:00Z", will_reopen=False), format="json")
    assert resp.data["kind"] == "status"
    order.refresh_from_db()
    assert not courier.has_active_ride(order)
    assert OperatorAlert.objects.filter(type="courier_ride_cancelled", order_ref=order.ref).exists()


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_redelivered_event_is_a_replay_and_asks_for_a_reading(shop):
    from django.utils import timezone
    from shopman.orderman.models import Directive

    from shopman.shop.directives import COURIER_SYNC

    order = _order_with_ride()
    client = _client()
    body = _event("E", event_id="evt-coleta-1", at="2026-10-01T14:40:00Z")
    assert client.post(_url(), body, format="json").data["kind"] == "status"
    Directive.objects.filter(topic=COURIER_SYNC).delete()

    replay = client.post(_url(), body, format="json")
    assert replay.data["kind"] == "replay"
    order.refresh_from_db()
    assert order.events.filter(type="courier_status").count() == 1
    sync = Directive.objects.get(topic=COURIER_SYNC, payload__order_ref=order.ref, status=Directive.Status.QUEUED)
    assert sync.available_at <= timezone.now()


# ── letras fora de ordem ────────────────────────────────────────────


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_late_acceptance_after_pickup_is_refused(shop):
    """Sonda da revisão: "after late A … A dispatched". A sacola na moto não volta a "aceita"."""
    order = _order_with_ride()
    client = _client()
    client.post(_url(), _event("E", event_id="evt-coleta-1", at="2026-10-01T14:40:00Z"), format="json")
    resp = client.post(_url(), _event("A", event_id="evt-aceite-atrasado", at="2026-10-01T14:14:00Z"), format="json")
    assert resp.status_code == 200
    assert resp.data["kind"] == "stale"

    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["status"] == "E"
    assert order.status == Order.Status.DISPATCHED
    assert "reopens" not in block


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_older_event_never_overrides_a_newer_one(shop):
    """Um ``D`` de antes do aceite, entregue depois, não vira "o entregador desistiu"."""
    order = _accepted_order()
    resp = _client().post(_url(), _event("D", event_id="evt-procura-velha", at="2026-10-01T14:10:00Z"), format="json")
    assert resp.data["kind"] == "stale"
    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["status"] == "A"
    assert block["driver"]["name"] == "Entregador Mock"
    assert "reopens" not in block


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_accepted_ride_that_goes_back_to_searching_loses_the_driver(shop):
    """A única volta legítima: aceita que volta a procurar antes da coleta."""
    order = _accepted_order()
    resp = _client().post(_url(), _event("D", event_id="evt-voltou-a-procurar", at="2026-10-01T14:32:00Z"), format="json")
    assert resp.data["kind"] == "status"
    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["status"] == "D"
    assert "driver" not in block
    assert block["reopens"][-1]["driver"] == "Entregador Mock"
    assert block["last_provider_at"] == "2026-10-01T14:32:00Z"


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_stale_acceptance_after_the_withdrawal_does_not_bring_the_driver_back(shop):
    order = _accepted_order()
    client = _client()
    client.post(_url(), _event("C", event_id="evt-desistiu-1", at="2026-10-01T14:32:00Z", will_reopen=True), format="json")
    resp = client.post(_url(), _event("A", event_id="evt-aceite-reenviado", at="2026-10-01T14:14:30Z"), format="json")
    assert resp.data["kind"] == "stale"
    order.refresh_from_db()
    assert courier.get_block(order)["status"] == "D"
    assert "driver" not in courier.get_block(order)


# ── corrida que constava como encerrada dá sinal de vida ────────────


def _order_with_archived_ride(ref="WH-ARQ", **courier_block) -> Order:
    return Order.objects.create(
        ref=ref, channel_ref="web", session_key=f"S-{ref}", status=Order.Status.READY, snapshot={"items": []},
        data={
            "fulfillment_type": "delivery",
            "customer": {"name": "Ana", "phone": "5543999990000"},
            "delivery_address_structured": {"latitude": -23.31, "longitude": -51.16},
            "courier": {
                "provider": "machine", "ride_number": 2, "called_at": "2026-10-01T14:10:00Z",
                "attempts": [{"id_mch": "184532", "status": "C", "requested_at": "2026-10-01T14:10:00Z",
                              "status_at": {"D": "2026-10-01T14:10:00Z", "C": "2026-10-01T14:32:00Z"},
                              "ended_at": "2026-10-01T14:32:05Z"}],
                **courier_block,
            },
        },
        total_q=5000,
    )


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_live_event_for_an_archived_ride_restores_it_and_alerts(shop):
    order = _order_with_archived_ride()
    courier_mock.rides()["184532"] = {"status": "A", "driver": None}
    resp = _client().post(_url(), _event("A", event_id="evt-aceite-2", at="2026-10-01T14:36:00Z"), format="json")
    assert resp.status_code == 200
    assert resp.data["kind"] == "restored"

    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["id_mch"] == "184532"
    assert block["status"] == "A"
    assert "attempts" not in block
    assert block["ride_number"] == 2
    assert order.events.filter(type="courier_ride_restored").count() == 1
    alert = OperatorAlert.objects.get(type="integration_failed", order_ref=order.ref)
    assert "A TaOn retomou a corrida B do pedido" in alert.message
    assert "Não chame outro entregador" in alert.message


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_late_event_for_an_archived_ride_changes_nothing(shop):
    """O aceite de ANTES do cancelamento, entregue depois: sem prova, não retoma."""
    order = _order_with_archived_ride()
    courier_mock.rides()["184532"] = {"status": "C", "driver": None}
    resp = _client().post(_url(), _event("A", event_id="evt-aceite-velho", at="2026-10-01T14:14:00Z"), format="json")
    assert resp.data["kind"] == "stale"
    order.refresh_from_db()
    assert "id_mch" not in courier.get_block(order)
    assert not OperatorAlert.objects.filter(order_ref=order.ref).exists()


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_archived_ride_alive_while_another_ride_runs_is_a_critical_alert(shop):
    order = _order_with_archived_ride(id_mch="999001", status="D", requested_at="2026-10-01T14:33:00Z")
    courier_mock.rides()["184532"] = {"status": "A", "driver": None}
    resp = _client().post(_url(), _event("A", event_id="evt-aceite-2", at="2026-10-01T14:36:00Z"), format="json")
    assert resp.data["kind"] == "conflict"
    order.refresh_from_db()
    assert courier.get_block(order)["id_mch"] == "999001"  # a corrida de agora não é trocada
    alert = OperatorAlert.objects.get(type="integration_failed", order_ref=order.ref)
    assert alert.severity == "critical"
    assert "não pagar duas corridas" in alert.message


# ── o corpo cru não vai para o log ──────────────────────────────────


@pytest.fixture
def webhook_log():
    """As linhas do webhook como saem, já pelo formatter de privacidade."""
    import io
    import logging

    from shopman.shop.logging import PrivacySafeFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(PrivacySafeFormatter("{levelname} {message}", style="{"))
    target = logging.getLogger("shopman.shop.webhooks.machine")
    level = target.level
    target.addHandler(handler)
    target.setLevel(logging.INFO)
    yield stream
    target.removeHandler(handler)
    target.setLevel(level)


@override_settings(SHOPMAN_MACHINE=MACHINE, SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_log_is_a_closed_list_never_the_raw_body(shop, webhook_log):
    _order_with_ride()
    body = _event(
        "A", event_id="evt-aceite-1", at="2026-10-01T14:14:00Z", stop_id=77,
        driver={"name": "Diego Ferreira", "phone": "43998761203", "cpf": "12345678910",
                "pix_key": "diego.ferreira@pix.example", "photo_url": "https://cdn.taon.example/drivers/8101.jpg"},
    )
    assert _client().post(_url(), body, format="json").status_code == 200
    logged = webhook_log.getvalue()

    for personal in ("Diego Ferreira", "43998761203", "12345678910", "diego.ferreira", "8101.jpg", "raw="):
        assert personal not in logged
    assert "kind=status request=184532 code=A event=evt-aceite-1 stop=77 will_reopen=no" in logged
    assert "sha256=" in logged and "size=" in logged


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_position_batch_and_unknown_payload_log_no_values(webhook_log):
    batch = {"event_id": "evt-pos", "datetime": "2026-10-01T17:00:00Z",
             "data": [{"request_id": 184532, "driver_id": 8101, "coordinates": {"latitude": -23.305, "longitude": -51.162}}]}
    _client().post(_url(), batch, format="json")
    _client().post(_url(), {"nome_condutor": "Diego Ferreira", "telefone": "43998761203"}, format="json")
    logged = webhook_log.getvalue()

    assert "kind=position_batch items=1 stored=1" in logged
    assert "kind=unrecognized keys=nome_condutor,telefone" in logged
    for personal in ("-23.305", "-51.162", "Diego Ferreira", "43998761203"):
        assert personal not in logged


@override_settings(SHOPMAN_MACHINE=MACHINE)
def test_signature_mismatch_logs_a_digest_not_the_body(webhook_log):
    body = json.dumps({"request_id": 184532, "status_code": "A", "driver": {"name": "Diego Ferreira"}}).encode("utf-8")
    resp = _raw_post(body, HTTP_SIGNATURE_V2="ABCDEF0123456789" + "0" * 112)
    assert resp.status_code == 401
    logged = webhook_log.getvalue()
    assert "Diego Ferreira" not in logged
    assert "signature=abcdef01..." in logged
    assert f"size={len(body)} sha256=" in logged
