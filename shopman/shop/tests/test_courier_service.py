"""Courier (Machine): despacho async, funil de status e transições derivadas.

Usa o adapter mock (``courier_mock``) — sem rede. O funil ``apply_status`` é o
mesmo para webhook e polling, então estes testes cobrem as duas vias.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.shop.adapters import courier_mock
from shopman.shop.directives import COURIER_DISPATCH, COURIER_SYNC, DELIVERY_AUTO_COMPLETE
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.handlers.courier_sync import CourierSyncHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    cache.clear()
    yield
    courier_mock.reset()


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Nelson Boulangerie",
        route="Av. Madre Leônia Milito",
        street_number="446",
        neighborhood="Bela Suíça",
        city="Londrina",
        state_code="PR",
        formatted_address="Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR",
        latitude=-23.3405,
        longitude=-51.1580,
    )


def _delivery_order(ref="CR-1", status=Order.Status.READY, channel_ref="web", **data_overrides) -> Order:
    data = {
        "fulfillment_type": "delivery",
        "customer": {"name": "Ana Lima", "phone": "5543999990000"},
        "delivery_address_structured": {
            "route": "Rua das Flores",
            "street_number": "123",
            "neighborhood": "Centro",
            "city": "Londrina",
            "state_code": "PR",
            "formatted_address": "Rua das Flores 123 - Centro - Londrina",
            "delivery_instructions": "Portão azul",
            "latitude": -23.31,
            "longitude": -51.16,
        },
        "delivery_fee_q": 800,
    }
    data.update(data_overrides)
    return Order.objects.create(
        ref=ref,
        channel_ref=channel_ref,
        session_key=f"S-{ref}",
        status=status,
        snapshot={"items": []},
        data=data,
        total_q=5000,
    )


def _run_dispatch(order) -> None:
    directive = Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=order.ref).first()
    assert directive is not None, "despacho não foi enfileirado"
    CourierDispatchHandler().handle(message=directive, ctx={})
    order.refresh_from_db()


# ── request_dispatch ────────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_request_dispatch_queues_directive_once(shop):
    order = _delivery_order()
    d1 = courier.request_dispatch(order, actor="test")
    d2 = courier.request_dispatch(order, actor="test")
    assert d1 is not None
    assert d2 is not None and d2.pk == d1.pk  # idempotente: reusa o enfileirado
    assert d1.dedupe_key == f"courier.dispatch:{order.ref}:1"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_request_dispatch_noop_for_pickup_and_wrong_status(shop):
    pickup = _delivery_order(ref="CR-P", fulfillment_type="pickup")
    assert courier.request_dispatch(pickup, actor="test") is None

    new = _delivery_order(ref="CR-W", status=Order.Status.NEW)
    assert courier.request_dispatch(new, actor="test") is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
@pytest.mark.parametrize("status", [Order.Status.ACCEPTED, Order.Status.PREPARING])
def test_house_delivery_calls_courier_from_acceptance_on_pdv_channel(shop, status):
    """O operador chama na hora, desde o aceite (decisão do dono, 13/10/2026).

    Caso do alpha: encomenda do PDV, entrega, em preparo (o KDS mandou) e o
    Gestor só oferecia "Cotar entrega".
    """
    order = _delivery_order(ref=f"PDV-{status}", status=status, channel_ref="pdv")
    assert courier.request_dispatch(order, actor="test") is not None
    _run_dispatch(order)
    assert courier.get_block(order)["id_mch"] == f"MOCK-{order.ref}"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
@pytest.mark.parametrize("status", [Order.Status.ACCEPTED, Order.Status.PREPARING])
def test_collection_before_ready_takes_the_order_out(shop, status):
    """Chamou antes do pronto e o entregador coletou: o pedido sai, não fica no preparo."""
    order = _delivery_order(ref=f"CR-EARLY-{status}", status=status)
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    courier.apply_status(order, "F", source="webhook")
    order.refresh_from_db()
    assert order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED)


def test_request_dispatch_noop_without_adapter(shop):
    order = _delivery_order()
    assert courier.request_dispatch(order, actor="test") is None
    assert not Directive.objects.filter(topic=COURIER_DISPATCH).exists()


# ── handler de despacho ─────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_opens_ride_and_schedules_sync(shop):
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)

    block = courier.get_block(order)
    assert block["id_mch"] == f"MOCK-{order.ref}"
    assert block["provider"] == "machine"
    assert block["status"] == "D"
    assert block["estimate"] == {"value_q": 1250, "minutes": 18.0, "km": 4.2}
    assert Directive.objects.filter(topic=COURIER_SYNC, payload__order_ref=order.ref).exists()

    # payload enviado à Machine: partida = loja, parada = cliente
    ride = courier_mock.rides()[block["id_mch"]]
    payload = ride["payload"]
    assert payload["partida"]["endereco"] == "Av. Madre Leônia Milito 446"
    assert payload["paradas"][0]["id_externo"] == order.ref
    assert payload["paradas"][0]["nome_cliente_parada"] == "Ana Lima"
    assert payload["paradas"][0]["telefone_cliente_parada"] == "5543999990000"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_replay_is_noop(shop):
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)
    first_id = courier.get_block(order)["id_mch"]

    directive = Directive.objects.filter(topic=COURIER_DISPATCH).first()
    CourierDispatchHandler().handle(message=directive, ctx={})  # replay at-least-once
    order.refresh_from_db()
    assert courier.get_block(order)["id_mch"] == first_id
    assert len(courier_mock.rides()) == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_skips_cancelled_order(shop):
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    order.refresh_from_db()
    directive = Directive.objects.filter(topic=COURIER_DISPATCH).first()
    CourierDispatchHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    assert "id_mch" not in courier.get_block(order)
    assert not courier_mock.rides()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_terminal_failure_records_error_and_alerts(shop, monkeypatch):
    from shopman.orderman.exceptions import DirectiveTerminalError

    from shopman.shop.adapters.courier_machine import CourierError

    def _refuse(payload):
        raise CourierError("Machine recusou (400): [2] Atributo obrigatório.", transient=False)

    monkeypatch.setattr(courier_mock, "dispatch", _refuse)
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    directive = Directive.objects.filter(topic=COURIER_DISPATCH).first()
    with pytest.raises(DirectiveTerminalError):
        CourierDispatchHandler().handle(message=directive, ctx={})

    order.refresh_from_db()
    assert "recusou" in courier.get_block(order)["error"]["message"]
    alert = OperatorAlert.objects.get(type="courier_dispatch_failed")
    assert alert.order_ref == order.ref
    assert alert.severity == "critical"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_dispatch_handler_unknown_failure_requires_verification(shop, monkeypatch):
    from shopman.orderman.exceptions import DirectiveTerminalError

    from shopman.shop.adapters.courier_machine import CourierError

    def _timeout(payload):
        raise CourierError("Machine indisponível: timeout", transient=True)

    monkeypatch.setattr(courier_mock, "dispatch", _timeout)
    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    directive = Directive.objects.filter(topic=COURIER_DISPATCH).first()
    with pytest.raises(DirectiveTerminalError):
        CourierDispatchHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    assert "sem resultado confirmado" in courier.get_block(order)["error"]["message"]
    assert OperatorAlert.objects.filter(type="courier_dispatch_failed").exists()
    directive.refresh_from_db()
    assert directive.payload["dispatch_attempt"]["state"] == "unknown"


# ── apply_status: transições derivadas ──────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def _dispatched_order(shop, ref="CR-1") -> Order:
    order = _delivery_order(ref=ref)
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)
    return order


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_accepted_ride_enriches_driver_and_tracking(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "A", source="poll")
    block = courier.get_block(order)
    assert block["status"] == "A"
    assert block["driver"]["name"] == "Entregador Mock"
    assert block["tracking_url"].startswith("https://rastreio.mock/")
    assert order.status == Order.Status.READY  # aceite ainda não é coleta


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_pickup_by_courier_advances_order_to_dispatched(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    block = courier.get_block(order)
    assert block["status"] == "E"
    assert block["dispatched_at"]
    # rede de segurança por ETA agendada como sempre
    assert Directive.objects.filter(topic=DELIVERY_AUTO_COMPLETE, payload__order_ref=order.ref).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_finished_ride_marks_delivered(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    courier.apply_status(order, "F", source="webhook")
    order.refresh_from_db()
    assert order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED)
    assert courier.get_block(order)["finished_at"]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_finished_without_observed_pickup_still_delivers(shop):
    # Webhook perdido/polling largo: F chega com o pedido ainda READY.
    order = _dispatched_order(shop)
    courier.apply_status(order, "F", source="poll")
    order.refresh_from_db()
    assert order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_not_attended_archives_ride_and_alerts(shop):
    order = _dispatched_order(shop)
    ride_id = courier.get_block(order)["id_mch"]
    courier.apply_status(order, "N", source="poll")
    order.refresh_from_db()

    block = courier.get_block(order)
    assert not courier.has_active_ride(order)
    assert block["attempts"][0]["id_mch"] == ride_id
    assert block["attempts"][0]["status"] == "N"
    assert OperatorAlert.objects.filter(type="courier_not_attended", order_ref=order.ref).exists()
    assert order.status == Order.Status.READY  # pedido não trava por causa da corrida


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_apply_status_is_idempotent_and_ignores_late_events(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    courier.apply_status(order, "E", source="poll")  # replay: no-op
    courier.apply_status(order, "F", source="webhook")
    order.refresh_from_db()
    events_before = order.events.filter(type="courier_status").count()
    courier.apply_status(order, "E", source="poll")  # atrasado pós-terminal: no-op
    assert order.events.filter(type="courier_status").count() == events_before


# ── redispatch / cancel_ride ────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_redispatch_after_not_attended_queues_new_attempt(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "N", source="poll")
    order.refresh_from_db()
    Directive.objects.filter(topic=COURIER_DISPATCH).delete()

    courier.redispatch(order, actor="operator:maria")
    directive = Directive.objects.get(topic=COURIER_DISPATCH, payload__order_ref=order.ref)
    assert directive.dedupe_key == f"courier.dispatch:{order.ref}:2"

    CourierDispatchHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    assert courier.has_active_ride(order)
    assert len(courier.get_block(order)["attempts"]) == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_redispatch_blocked_with_active_ride(shop):
    order = _dispatched_order(shop)
    with pytest.raises(ValueError, match="corrida ativa"):
        courier.redispatch(order, actor="operator:maria")


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancel_ride_before_pickup(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "A", source="poll")
    task = courier.cancel_ride(order, actor="maria")
    from shopman.shop.handlers.courier_cancel import CourierCancelHandler

    CourierCancelHandler().handle(message=task, ctx={})
    order.refresh_from_db()
    assert not courier.has_active_ride(order)
    # cancelamento pelo operador não gera alerta (ele mesmo agiu)
    assert not OperatorAlert.objects.filter(type="courier_ride_cancelled").exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancel_ride_blocked_after_pickup(shop):
    order = _dispatched_order(shop)
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    with pytest.raises(ValueError, match="em rota"):
        courier.cancel_ride(order, actor="maria")


# ── pedido cancelado: a corrida não segue aberta ────────────────────


def _cancel_order(order) -> None:
    """O pedido vira cancelado e a fase on_cancelled do lifecycle roda."""
    from shopman.shop.lifecycle import dispatch

    Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
    order.refresh_from_db()
    dispatch(order, "on_cancelled")


def _cancelled_order_alerts(order):
    return OperatorAlert.objects.filter(order_ref=order.ref, type="integration_failed", severity="critical")


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
@pytest.mark.parametrize("ride_status", ["D", "A"])
def test_cancelling_order_before_pickup_cancels_the_ride_once(shop, ride_status):
    from shopman.shop.directives import COURIER_CANCEL
    from shopman.shop.handlers.courier_cancel import CourierCancelHandler

    order = _dispatched_order(shop)
    ride = courier.get_block(order)["id_mch"]
    if ride_status != "D":
        courier.apply_status(order, ride_status, source="poll")
    _cancel_order(order)
    tasks = Directive.objects.filter(topic=COURIER_CANCEL, payload__order_ref=order.ref)
    assert tasks.count() == 1  # enfileirado pela fase on_cancelled do lifecycle
    courier.on_order_cancelled(order)  # replay da fase: idempotente
    assert tasks.count() == 1
    assert tasks.get().payload["courier_ref"] == ride
    CourierCancelHandler().handle(message=tasks.get(), ctx={})
    order.refresh_from_db()
    assert courier_mock.rides()[ride]["status"] == "C"
    assert not courier.has_active_ride(order)
    courier.on_order_cancelled(order)  # corrida já cancelada: nada a fazer
    assert tasks.count() == 1
    assert not _cancelled_order_alerts(order).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancelling_order_after_pickup_warns_operator_once(shop):
    from shopman.shop.directives import COURIER_CANCEL

    order = _dispatched_order(shop, ref="NB-261013-A47")
    block = {**courier.get_block(order), "status": "E"}
    Order.objects.filter(pk=order.pk).update(data={**order.data, "courier": block})
    order.refresh_from_db()
    _cancel_order(order)
    assert _cancelled_order_alerts(order).count() == 1  # aviso da fase on_cancelled
    courier.on_order_cancelled(order)
    courier.apply_status(order, "E", source="webhook")  # replay do fato

    alert = _cancelled_order_alerts(order).get()
    assert alert.message == "O entregador já coletou o pedido A47, que foi cancelado: fale com a central."
    assert not Directive.objects.filter(topic=COURIER_CANCEL).exists()
    assert courier_mock.rides()[block["id_mch"]]["status"] != "C"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_pickup_arriving_after_cancellation_warns_operator(shop):
    """A coleta chega antes de o worker cancelar a corrida: o aviso sai do fato."""
    from shopman.shop.directives import COURIER_CANCEL
    from shopman.shop.handlers.courier_cancel import CourierCancelHandler

    order = _dispatched_order(shop)
    courier.apply_status(order, "A", source="poll")
    _cancel_order(order)
    courier.apply_status(order, "E", source="webhook")
    CourierCancelHandler().handle(message=Directive.objects.get(topic=COURIER_CANCEL), ctx={})
    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert _cancelled_order_alerts(order).count() == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancelling_order_without_ride_is_silent(shop):
    order = _delivery_order(ref="CR-SEM")
    _cancel_order(order)
    assert not _cancelled_order_alerts(order).exists()


# ── polling (courier.sync) ──────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_handler_applies_status_and_reschedules(shop):
    order = _dispatched_order(shop)
    courier_mock.set_status(courier.get_block(order)["id_mch"], "A")
    directive = Directive.objects.get(topic=COURIER_SYNC, payload__order_ref=order.ref)
    Directive.objects.filter(pk=directive.pk).update(status=Directive.Status.DONE)

    CourierSyncHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    assert courier.get_block(order)["status"] == "A"
    assert Directive.objects.filter(
        topic=COURIER_SYNC, payload__order_ref=order.ref, status=Directive.Status.QUEUED
    ).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_handler_stops_on_terminal_status(shop):
    order = _dispatched_order(shop)
    ride_id = courier.get_block(order)["id_mch"]
    courier_mock.set_status(ride_id, "E")
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    courier_mock.set_status(ride_id, "F")

    directive = Directive.objects.get(topic=COURIER_SYNC, payload__order_ref=order.ref)
    Directive.objects.filter(pk=directive.pk).update(status=Directive.Status.DONE)
    CourierSyncHandler().handle(message=directive, ctx={})
    order.refresh_from_db()

    assert order.status in (Order.Status.DELIVERED, Order.Status.COMPLETED)
    assert not Directive.objects.filter(
        topic=COURIER_SYNC, payload__order_ref=order.ref, status=Directive.Status.QUEUED
    ).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_handler_respects_poll_disabled(shop):
    shop.defaults = {"delivery": {"courier_poll_seconds": 0}}
    shop.save()
    from shopman.shop.models.shop import SHOP_CACHE_KEY

    cache.delete(SHOP_CACHE_KEY)

    order = _delivery_order()
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)
    # com polling desligado o despacho não agenda heartbeat
    assert not Directive.objects.filter(topic=COURIER_SYNC, payload__order_ref=order.ref).exists()


def _beat(order):
    """Uma batida do polling, do jeito que o worker roda."""
    directive = Directive.objects.filter(
        topic=COURIER_SYNC, payload__order_ref=order.ref, status=Directive.Status.QUEUED
    ).first()
    Directive.objects.filter(pk=directive.pk).update(status=Directive.Status.DONE)
    CourierSyncHandler().handle(message=directive, ctx={})
    order.refresh_from_db()


def _sync_alerts(order):
    return OperatorAlert.objects.filter(type="integration_failed", order_ref=order.ref,
                                        message__contains=f"corrida {courier.get_block(order).get('id_mch')}")


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_failure_is_not_silent(shop, django_capture_on_commit_callbacks):
    """13/10/2026: a leitura recusou a cada minuto e nem o pedido nem o operador souberam."""
    order = _dispatched_order(shop)
    ride = courier.get_block(order)["id_mch"]
    courier_mock.fail_reads(ride)

    _beat(order)
    block = courier.get_block(order)
    assert block["status"] == "D"
    assert block["sync"]["failing_since"]
    assert "[67]" in block["sync"]["last_error"]
    assert not _sync_alerts(order).exists()

    revision = courier.dispatch_revision(order)
    _beat(order)
    assert courier.dispatch_revision(order) == revision  # a batida que falha de novo não gira a revisão
    _beat(order)
    assert _sync_alerts(order).filter(resolved_at__isnull=True).count() == 1
    assert courier.progress_view(courier.get_block(order))["sync_since"]

    _beat(order)
    assert _sync_alerts(order).count() == 1  # um aviso por corrida

    # A central voltou a responder: a tela se corrige e o aviso sai sozinho.
    courier_mock.rides()[ride].pop("read_error")
    courier_mock.set_status(ride, "A")
    with django_capture_on_commit_callbacks(execute=True):
        _beat(order)
    block = courier.get_block(order)
    assert block["status"] == "A"
    assert "sync" not in block
    assert not _sync_alerts(order).filter(resolved_at__isnull=True).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_stores_the_ride_progress_and_the_screen_view(shop):
    order = _dispatched_order(shop)
    ride = courier.get_block(order)["id_mch"]
    courier_mock.set_status(ride, "A")
    courier_mock.set_progress(ride, {
        "accepted_at": "2026-10-13T18:42:00+00:00",
        "pickup_eta_at": "2026-10-13T18:49:00+00:00",
        "pickup_eta_minutes": 7,
        "trip_minutes": 9,
    })
    _beat(order)
    block = courier.get_block(order)
    assert block["progress"]["pickup_eta_at"] == "2026-10-13T18:49:00+00:00"
    view = courier.progress_view(block)
    assert view["pickup_eta_at"] == "2026-10-13T18:49:00+00:00"
    assert view["delivery_eta_at"].startswith("2026-10-13T18:58:00")  # chegada à loja + viagem

    courier_mock.set_progress(ride, {"arrived_pickup_at": "2026-10-13T18:50:00+00:00"})
    _beat(order)
    assert courier.progress_view(courier.get_block(order))["arrived_pickup_at"] == "2026-10-13T18:50:00+00:00"

    courier_mock.set_status(ride, "E")
    courier_mock.set_progress(ride, {"picked_up_at": "2026-10-13T18:52:00+00:00"})
    _beat(order)
    view = courier.progress_view(courier.get_block(order))
    assert view["pickup_eta_at"] == ""  # já coletou: a chegada à loja sai da tela
    assert view["delivery_eta_at"].startswith("2026-10-13T19:01:00")  # coleta + viagem


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_unchanged_reading_does_not_rewrite_the_order(shop):
    order = _dispatched_order(shop)
    ride = courier.get_block(order)["id_mch"]
    courier_mock.set_status(ride, "A")
    _beat(order)
    revision = courier.dispatch_revision(order)
    _beat(order)
    assert courier.dispatch_revision(order) == revision


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_gives_up_on_a_ride_older_than_the_cap(shop):
    from datetime import timedelta

    from django.utils import timezone

    order = _dispatched_order(shop)
    block = dict(courier.get_block(order))
    block["requested_at"] = (timezone.now() - timedelta(hours=courier.MAX_POLL_HOURS + 1)).isoformat()
    courier._save_block(order, block)
    _beat(order)
    assert not Directive.objects.filter(
        topic=COURIER_SYNC, payload__order_ref=order.ref, status=Directive.Status.QUEUED
    ).exists()


# ── cotação ─────────────────────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_estimate_for_order_caches_and_stores(shop):
    order = _delivery_order()
    est = courier.estimate_for_order(order, store=True)
    assert est == {"value_q": 1250, "minutes": 18.0, "km": 4.2}
    order.refresh_from_db()
    assert courier.get_block(order)["estimate"] == est
    # segunda chamada vem do cache (adapter não é consultado)
    import unittest.mock as mock

    with mock.patch.object(courier_mock, "estimate", side_effect=AssertionError("cache miss")):
        assert courier.estimate_for_order(order) == est


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_estimate_for_order_sends_both_addresses(shop):
    """A cotação leva o endereço da loja e o do cliente (obrigatórios na API de entregas)."""
    import unittest.mock as mock

    order = _delivery_order()
    with mock.patch.object(courier_mock, "estimate", wraps=courier_mock.estimate) as spy:
        courier.estimate_for_order(order)
    kwargs = spy.call_args.kwargs
    assert kwargs["pickup"] == {
        "lat": "-23.3405000", "lng": "-51.1580000", "street": "Av. Madre Leônia Milito 446",
        "neighborhood": "Bela Suíça", "city": "Londrina", "state": "PR",
    }
    assert kwargs["dropoff"] == {
        "lat": "-23.31", "lng": "-51.16", "street": "Rua das Flores 123",
        "neighborhood": "Centro", "city": "Londrina", "state": "PR",
    }


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_estimate_for_order_none_without_coordinates(shop):
    order = _delivery_order(delivery_address_structured={"city": "Londrina"})
    assert courier.estimate_for_order(order) is None


# ── gancho do lifecycle (_on_ready) ─────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_on_ready_with_courier_auto_queues_dispatch(shop):
    from shopman.shop.config import ChannelConfig
    from shopman.shop.lifecycle import _on_ready

    config = ChannelConfig.from_dict(
        {"fulfillment": {"timing": "external", "courier": "auto"}}
    )
    order = _delivery_order()
    _on_ready(order, config)
    assert Directive.objects.filter(topic=COURIER_DISPATCH, payload__order_ref=order.ref).exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_on_ready_with_courier_none_does_not_dispatch(shop):
    from shopman.shop.config import ChannelConfig
    from shopman.shop.lifecycle import _on_ready

    config = ChannelConfig.from_dict({"fulfillment": {"timing": "external"}})
    order = _delivery_order()
    _on_ready(order, config)
    assert not Directive.objects.filter(topic=COURIER_DISPATCH).exists()


# ── notificação: link de rastreio do entregador ─────────────────────


def test_notification_context_includes_courier_tracking(shop):
    from shopman.shop.services.notification import _build_context

    order = _delivery_order(
        courier={
            "provider": "machine",
            "id_mch": "1",
            "status": "E",
            "tracking_url": "https://rastreio.mock/pedido/x",
        }
    )
    ctx = _build_context(order, {"order_ref": order.ref}, "order_dispatched")
    assert ctx["courier_tracking_url"] == "https://rastreio.mock/pedido/x"
    assert ctx["courier_tracking_suffix"] == "\nAcompanhe o entregador: https://rastreio.mock/pedido/x"


def test_notification_context_suppresses_suffix_without_ride(shop):
    from shopman.shop.services.notification import _build_context

    order = _delivery_order(ref="CR-NO-RIDE")
    ctx = _build_context(order, {"order_ref": order.ref}, "order_dispatched")
    assert ctx["courier_tracking_url"] == ""
    assert ctx["courier_tracking_suffix"] == ""


def test_channel_config_validates_courier_values():
    from shopman.shop.config import ChannelConfig

    config = ChannelConfig.from_dict({"fulfillment": {"courier": "sempre"}})
    with pytest.raises(ValueError, match="fulfillment.courier"):
        config.validate()


@pytest.mark.parametrize("status", ["E", "F"])
def test_collection_dispatches_with_cash_at_the_door_without_inventing_custody(status):
    """Decisão do dono (13/10/2026): a coleta da TaOn despacha também com cobrança na porta."""
    from shopman.cashman.models import Entry

    order = _delivery_order(payment={"method": "cash", "collection": "on_delivery", "change_for_q": 10000},
                            courier={"id_mch": "LAB-RIDE", "status": "A"})
    courier.apply_status(order, status, source="poll")
    courier.apply_status(order, status, source="poll")  # replay: no-op
    order.refresh_from_db()
    assert order.status in ({"dispatched"} if status == "E" else {"delivered", "completed"})
    assert order.data["dispatch"]["collector"] == "courier_partner"
    # Fato externo não lança troco da gaveta.
    assert not Entry.objects.filter(kind=Entry.Kind.COURIER_OUT, order_ref=order.ref).exists()
    assert order.events.filter(type="courier_status").count() == 1
    if status == "E":
        assert courier.get_block(order)["door_charge"] == {"cash_q": 5000, "change_for_q": 10000, "card_q": 0}


def test_collection_dispatches_card_at_the_door_without_reserving_a_house_machine():
    order = _delivery_order(payment={"method": "credit", "collection": "on_delivery"},
                            courier={"id_mch": "LAB-CARD", "status": "A"})
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    assert order.status == "dispatched"
    assert "device_ref" not in order.data["dispatch"]
    assert courier.get_block(order)["door_charge"] == {"cash_q": 0, "change_for_q": 0, "card_q": 5000}


def test_operator_dispatch_before_collection_keeps_drawer_change(django_user_model):
    """Troco da gaveta que vai com o entregador da TaOn: despacha no Gestor antes da coleta."""
    from shopman.cashman import services as cash

    from shopman.shop.services import operator_orders

    order = _delivery_order(payment={"method": "cash", "collection": "on_delivery", "change_for_q": 5500},
                            courier={"id_mch": "LAB-RIDE", "status": "A"})
    user = django_user_model.objects.create_user(username="custodian")
    shift = cash.open_shift(operator=user, float_q=1000)
    operator_orders.advance_order(order, actor=user.username, change_out_q=500, cash_shift=shift)
    courier.apply_status(order, "E", source="poll")
    order.refresh_from_db()
    assert order.status == "dispatched"
    assert "collector" not in order.data.get("dispatch", {})
    assert operator_orders.courier_change(order).out_q == 500


@pytest.mark.parametrize(("payment", "expected"), [
    ({"method": "cash", "collection": "on_delivery", "change_for_q": 10000},
     "Pedido 1 · Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00"),
    ({"method": "cash", "collection": "on_delivery"},
     "Pedido 1 · Cobrar R$ 50,00 em dinheiro · sem troco"),
    ({"method": "debit", "collection": "on_delivery"},
     "Pedido 1 · Cobrar R$ 50,00 no cartão (maquininha)"),
    ({"method": "mixed", "collection": "on_delivery", "change_for_q": 5000, "tenders": [
        {"method": "cash", "amount_q": 3000, "collection": "on_delivery", "status": "pending"},
        {"method": "credit", "amount_q": 2000, "collection": "on_delivery", "status": "pending"}]},
     "Pedido 1 · Cobrar R$ 30,00 em dinheiro · troco para R$ 50,00 · Cobrar R$ 20,00 no cartão (maquininha)"),
    ({"method": "pix", "status": "captured"}, "Pedido 1 · Pago, não cobrar"),
    ({"method": "cash", "collection": "on_delivery", "cod_settled_at": "2026-10-13T12:00:00+00:00"},
     "Pedido 1 · Pago, não cobrar"),
])
def test_ride_observation_says_what_to_charge_at_the_door(shop, payment, expected):
    order = _delivery_order(ref="CR-1", payment=payment)
    body = courier.build_machine_payload(order)
    assert body["paradas"][0]["observacao_parada"] == expected
    assert body["paradas"][0]["id_externo"] == "CR-1"


def test_terminal_fact_recovers_local_failure_without_polling_provider(monkeypatch):
    from shopman.shop.services import operator_orders

    order = _delivery_order(status="dispatched", courier={"id_mch": "LAB-F", "status": "E"})
    real = operator_orders.confirm_received
    monkeypatch.setattr(operator_orders, "confirm_received", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("local failure")))
    with pytest.raises(RuntimeError, match="local failure"):
        courier.apply_status(order, "F", source="poll")
    order.refresh_from_db()
    assert courier.get_block(order)["status"] == "F"
    monkeypatch.setattr(operator_orders, "confirm_received", real)
    directive = Directive.objects.create(topic=COURIER_SYNC, payload={"order_ref": order.ref})
    CourierSyncHandler().handle(message=directive, ctx={})
    order.refresh_from_db()
    assert order.status in {"delivered", "completed"}
    assert order.events.filter(type="courier_status").count() == 1


def test_old_ride_response_does_not_modify_replacement():
    order = _delivery_order(courier={"id_mch": "OLD", "status": "A"})
    stale = Order.objects.get(pk=order.pk)
    courier._save_block(order, {"id_mch": "NEW", "status": "A"})
    courier.apply_status(stale, "F", source="webhook")
    order.refresh_from_db()
    assert courier.get_block(order) == {"id_mch": "NEW", "status": "A"}
    assert order.status == "ready"
    assert not order.events.filter(type="courier_status").exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_remote_accept_with_lost_response_never_repeats_dispatch_blindly(shop, monkeypatch):
    from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError

    from shopman.shop.adapters.courier_machine import CourierDispatchResult, CourierError

    accepted = []

    def accepted_but_response_lost(payload):
        accepted.append(payload)
        if len(accepted) == 1:
            raise CourierError("Resposta perdida após aceite remoto sintético", transient=True)
        return CourierDispatchResult(courier_ref="SECOND-REMOTE-RIDE")

    monkeypatch.setattr(courier_mock, "dispatch", accepted_but_response_lost)
    order = _delivery_order(ref="LOST-REMOTE-RESPONSE")
    task = courier.request_dispatch(order, actor="lab")
    for _ in range(2):
        try:
            CourierDispatchHandler().handle(message=task, ctx={})
        except (DirectiveTransientError, DirectiveTerminalError):
            pass
    assert len(accepted) == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_known_acceptance_recovers_local_failure_without_remote_retry(shop, monkeypatch):
    order = _delivery_order(ref="KNOWN-ACCEPTANCE")
    task = courier.request_dispatch(order, actor="lab")
    original = courier._save_block

    def fail_adoption(order, block, **kwargs):
        if block.get("id_mch"):
            raise RuntimeError("local adoption failed")
        return original(order, block, **kwargs)

    monkeypatch.setattr(courier, "_save_block", fail_adoption)
    with pytest.raises(RuntimeError, match="local adoption failed"):
        CourierDispatchHandler().handle(message=task, ctx={})
    task.refresh_from_db()
    assert task.payload["dispatch_attempt"]["state"] == "accepted"
    assert len(courier_mock.rides()) == 1
    monkeypatch.setattr(courier, "_save_block", original)
    CourierDispatchHandler().handle(message=task, ctx={})
    order.refresh_from_db()
    assert courier.has_active_ride(order)
    assert len(courier_mock.rides()) == 1
    assert order.events.filter(type="courier_ride_opened").count() == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_lost_acceptance_receipt_blocks_new_remote_attempt(shop, monkeypatch):
    from shopman.orderman.exceptions import DirectiveTerminalError

    order = _delivery_order(ref="LOST-ACCEPTANCE-RECEIPT")
    task = courier.request_dispatch(order, actor="lab")
    handler = CourierDispatchHandler()
    original = handler._set_attempt

    def fail_receipt(message, state, **values):
        if state == "accepted":
            raise RuntimeError("receipt storage failed")
        return original(message, state, **values)

    monkeypatch.setattr(handler, "_set_attempt", fail_receipt)
    with pytest.raises(RuntimeError, match="receipt storage failed"):
        handler.handle(message=task, ctx={})
    task.refresh_from_db()
    assert task.payload["dispatch_attempt"]["state"] == "started"
    with pytest.raises(DirectiveTerminalError, match="sem resultado confirmado"):
        handler.handle(message=task, ctx={})
    with pytest.raises(ValueError, match="resultado"):
        courier.redispatch(order, actor="lab")
    assert len(courier_mock.rides()) == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_legacy_retried_attempt_without_receipt_requires_verification(shop):
    from shopman.orderman.exceptions import DirectiveTerminalError

    order = _delivery_order(ref="LEGACY-UNCONFIRMED")
    task = Directive.objects.create(topic=COURIER_DISPATCH, attempts=2, payload={"order_ref": order.ref})
    with pytest.raises(DirectiveTerminalError, match="sem resultado confirmado"):
        CourierDispatchHandler().handle(message=task, ctx={})
    assert not courier_mock.rides()


@pytest.mark.django_db(transaction=True)
@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_two_dispatch_workers_do_not_open_two_remote_rides(shop, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connection, connections
    from shopman.orderman.exceptions import DirectiveTerminalError

    if connection.vendor != "postgresql":
        pytest.skip("Independent row locks require PostgreSQL")
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *a: None)
    order = _delivery_order(ref="TWO-DISPATCH-WORKERS")
    tasks = [Directive.objects.create(topic=COURIER_DISPATCH, payload={"order_ref": order.ref}) for _ in range(2)]
    entered, release = Event(), Event()
    original = courier_mock.dispatch
    calls = []

    def delayed_remote(body):
        calls.append(body)
        entered.set()
        assert release.wait(10)
        return original(body)

    monkeypatch.setattr(courier_mock, "dispatch", delayed_remote)

    def worker(task):
        try:
            CourierDispatchHandler().handle(message=task, ctx={})
            return "accepted"
        except DirectiveTerminalError:
            return "verification"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker, tasks[0])
        try:
            assert entered.wait(10)
            second = pool.submit(worker, tasks[1])
            assert second.result(timeout=10) == "verification"
        finally:
            release.set()
        assert first.result(timeout=10) == "accepted"
    assert len(calls) == 1
    order.refresh_from_db()
    assert courier.has_active_ride(order)


# ── ensaio a seco: o caminho inteiro do lifecycle, com o adapter mock ─────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ensaio_a_seco_despacho_status_e_cancelamento(shop):
    """Pedido pronto → despacho → aceite por polling → cancelamento, pelo caminho real.

    Mesmas peças que o worker usa em produção: ``lifecycle._on_ready`` enfileira,
    os handlers de Directive executam, e o adapter é o mock no lugar da Machine.
    """
    from shopman.shop.config import ChannelConfig
    from shopman.shop.handlers.courier_cancel import CourierCancelHandler
    from shopman.shop.lifecycle import _on_ready

    order = _delivery_order(ref="ENSAIO-1")
    _on_ready(order, ChannelConfig.from_dict({"fulfillment": {"timing": "external", "courier": "auto"}}))

    _run_dispatch(order)  # despacho: POST /abrirSolicitacao
    ride = courier.get_block(order)["id_mch"]
    assert ride == "MOCK-ENSAIO-1"
    assert courier.get_block(order)["status"] == "D"

    courier_mock.set_status(ride, "A")  # a central aceitou
    sync = Directive.objects.get(topic=COURIER_SYNC, payload__order_ref=order.ref)
    Directive.objects.filter(pk=sync.pk).update(status=Directive.Status.DONE)
    CourierSyncHandler().handle(message=sync, ctx={})  # status: GET /solicitacaoStatus
    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["status"] == "A"
    assert block["driver"]["name"] == "Entregador Mock"  # detalhes: GET /v1/request/{id}
    assert block["tracking_url"] == f"https://rastreio.mock/pedido/{ride}"  # GET /obterLinkRastreio/{id}

    task = courier.cancel_ride(order, actor="ensaio")
    CourierCancelHandler().handle(message=task, ctx={})  # cancelamento: POST /cancelar
    order.refresh_from_db()
    assert courier_mock.rides()[ride]["status"] == "C"
    assert not courier.has_active_ride(order)


# ── Edição depois da chamada (P2-28) ────────────────────────────────


def _cod_order(ref="CR-EDIT") -> Order:
    order = _delivery_order(ref=ref, status=Order.Status.PREPARING, payment={
        "method": "cash", "collection": "on_delivery", "change_for_q": 10000})
    courier.request_dispatch(order, actor="test")
    _run_dispatch(order)
    return order


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ride_keeps_the_observation_it_carried(shop):
    """A corrida guarda a observação que foi à TaOn: é com ela que o entregador cobra."""
    order = _cod_order()
    block = courier.get_block(order)
    sent = courier_mock.rides()[block["id_mch"]]["payload"]["paradas"][0]["observacao_parada"]
    assert block["door_charge_note"] == sent
    assert "troco para R$ 100,00" in sent
    assert courier.charge_outdated(order) is None


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_editing_the_charge_after_the_call_flags_the_ride(shop):
    """Troco ou forma de pagar mudou com a corrida aberta: a TaOn não altera a
    observação, e a tela precisa dizer que o entregador vai cobrar o antigo."""
    from shopman.shop.services.order_helpers import merge_order_data

    order = _cod_order()
    merge_order_data(order, {"payment": {"method": "cash", "collection": "on_delivery", "change_for_q": 5000}})
    order.refresh_from_db()
    assert courier.charge_outdated(order) == {
        "sent": "Cobrar R$ 50,00 em dinheiro · troco para R$ 100,00",
        "current": "Cobrar R$ 50,00 em dinheiro · sem troco",
        "collected": False,
    }

    merge_order_data(order, {"payment": {"method": "debit", "collection": "on_delivery"}})
    order.refresh_from_db()
    assert courier.charge_outdated(order)["current"] == "Cobrar R$ 50,00 no cartão (maquininha)"

    # Coletou: cancelar já não serve, a tela pede o telefone.
    courier.apply_status(order, "E", source="webhook")
    order.refresh_from_db()
    assert courier.charge_outdated(order)["collected"] is True


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_new_call_after_cancel_carries_the_new_charge(shop):
    """Cancelar e chamar de novo: a corrida nova leva a cobrança de agora."""
    from shopman.shop.handlers.courier_cancel import CourierCancelHandler
    from shopman.shop.services.order_helpers import merge_order_data

    order = _cod_order()
    merge_order_data(order, {"payment": {"method": "cash", "collection": "on_delivery", "change_for_q": 5000}})
    order.refresh_from_db()
    CourierCancelHandler().handle(message=courier.cancel_ride(order, actor="maria"), ctx={})
    order.refresh_from_db()
    assert courier.charge_outdated(order) is None
    assert "door_charge_note" not in courier.get_block(order)

    Directive.objects.filter(topic=COURIER_DISPATCH).update(status=Directive.Status.DONE)
    CourierDispatchHandler().handle(message=courier.redispatch(order, actor="operator:maria"), ctx={})
    order.refresh_from_db()
    block = courier.get_block(order)
    assert block["door_charge_note"].endswith("Cobrar R$ 50,00 em dinheiro · sem troco")
    assert courier.charge_outdated(order) is None
