"""Cancelar a corrida na TaOn: o motivo certo por fase, a corrida inteira, e a recusa visível.

O mock (``courier_mock.cancel``) cancela como a central: antes do aceite só o
motivo 10, depois do aceite a lista de ``CANCEL_REASONS_AFTER_ACCEPT``, e o
erro 102 fora disso. Com o motivo fixo de antes (1), o cancelamento antes do
aceite falhava sempre e a falha era muda (issue #2463).
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.order_queue import (
    COURIER_CANCEL_REASONS,
    _courier_block,
    courier_cancel_confirmation,
)
from shopman.shop.adapters import courier_machine, courier_mock
from shopman.shop.adapters.courier_machine import CourierError, cancel_reason_for
from shopman.shop.directives import COURIER_CANCEL, COURIER_DISPATCH, COURIER_SYNC
from shopman.shop.handlers.courier_cancel import CourierCancelHandler
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.handlers.courier_sync import CourierSyncHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.tests.test_courier_service import _delivery_order, _dispatched_order

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


@pytest.fixture
def sse(monkeypatch):
    """Os avisos de tempo real que a corrida emitiu: ``[(ref, kind)]``."""
    seen: list[tuple[str, str]] = []
    original = courier._emit_sse

    def capture(order, payload):
        seen.append((order.ref, str(payload.get("kind") or "")))
        original(order, payload)

    monkeypatch.setattr(courier, "_emit_sse", capture)
    return seen


def _at(ref, lat, lng, **data):
    order = _delivery_order(ref=ref, payment=data.pop("payment", PAID), **data)
    address = dict(order.data["delivery_address_structured"], latitude=lat, longitude=lng)
    order.data = {**order.data, "delivery_address_structured": address}
    order.save(update_fields=["data"])
    return order


def _group(*orders):
    """Uma corrida aberta com vários pedidos; devolve o ``ride_ref``."""
    CourierDispatchHandler().handle(
        message=courier.request_group_dispatch(list(orders), actor="operator:ana"), ctx={})
    # O worker fecha a tarefa depois do handler; aqui o handler roda direto.
    Directive.objects.filter(topic=COURIER_DISPATCH).update(status=Directive.Status.DONE)
    for order in orders:
        order.refresh_from_db()
    return courier.get_block(orders[0])["ride_ref"]


def _cancel(task):
    CourierCancelHandler().handle(message=task, ctx={})


def _ride(order) -> str:
    return courier.get_block(order)["ride_ref"]


# ── a tabela ────────────────────────────────────────────────────────


@pytest.mark.parametrize("letter", ["D", "T", "P", "G"])
def test_before_accept_the_only_reason_the_central_takes_is_10(letter):
    assert cancel_reason_for(letter) == 10
    # Antes do aceite a escolha do operador não importa: a central só aceita o 10.
    assert cancel_reason_for(letter, 37) == 10
    assert cancel_reason_for(letter, courier_machine.CANCEL_INTENT_ORDER_CANCELLED) == 10


@pytest.mark.parametrize("letter", ["A", "S"])
def test_after_accept_the_reason_is_the_chosen_one(letter):
    assert cancel_reason_for(letter) == 12
    assert cancel_reason_for(letter, 37) == 37
    assert cancel_reason_for(letter, 40) == 40
    assert cancel_reason_for(letter, courier_machine.CANCEL_INTENT_ORDER_CANCELLED) == 33
    # Motivo fora da lista da central nunca é enviado: volta ao padrão.
    assert cancel_reason_for(letter, 10) == 12
    assert cancel_reason_for(letter, True) == 12


def test_the_reasons_the_screen_offers_are_the_ones_the_central_takes():
    offered = tuple(reason for reason, _ in COURIER_CANCEL_REASONS)
    assert offered == courier_machine.CANCEL_REASONS_OPERATOR
    assert set(offered) <= courier_machine.CANCEL_REASONS_AFTER_ACCEPT
    assert "T" in courier_machine.CANCELLABLE_STATUSES


# ── o motivo que vai à central ──────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancel_before_accept_sends_reason_10_and_cancels(shop):
    """O caso mais comum ("ninguém aceitou, cancela") cancela de verdade (#2463)."""
    order = _dispatched_order(shop)
    ride = _ride(order)
    _cancel(courier.cancel_ride(order, actor="operator:maria"))
    assert courier_mock.rides()[ride]["cancel_reasons"] == [10]
    assert courier_mock.rides()[ride]["status"] == "C"
    order.refresh_from_db()
    assert not courier.has_active_ride(order)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
@pytest.mark.parametrize(("chosen", "intent", "sent"), [
    (None, courier_machine.CANCEL_INTENT_OPERATOR, 12),
    (37, courier_machine.CANCEL_INTENT_OPERATOR, 37),
    (40, courier_machine.CANCEL_INTENT_OPERATOR, 40),
    (None, courier_machine.CANCEL_INTENT_ORDER_CANCELLED, 33),
])
def test_cancel_after_accept_sends_the_chosen_reason(shop, chosen, intent, sent):
    order = _dispatched_order(shop)
    ride = _ride(order)
    courier_mock.set_status(ride, "A")
    courier.apply_status(order, "A", source="poll")
    _cancel(courier.cancel_ride(order, actor="operator:maria", reason_id=chosen, intent=intent))
    assert courier_mock.rides()[ride]["cancel_reasons"] == [sent]
    assert courier_mock.rides()[ride]["status"] == "C"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_letter_is_read_again_before_the_post(shop):
    """O pedido ainda diz "procurando", a central já diz "aceita": vale a letra de agora."""
    order = _dispatched_order(shop)
    ride = _ride(order)
    courier_mock.set_status(ride, "A")  # o aceite ainda não chegou ao pedido
    assert courier.get_block(order)["status"] == "D"
    _cancel(courier.cancel_ride(order, actor="operator:maria"))
    assert courier_mock.rides()[ride]["cancel_reasons"] == [12]
    assert courier_mock.rides()[ride]["status"] == "C"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_error_102_reads_the_letter_and_resends_once(shop):
    """A leitura falha e a letra do pedido está velha: o 102 corrige o motivo, uma vez só."""
    order = _dispatched_order(shop)
    ride = _ride(order)
    courier_mock.set_status(ride, "A")
    courier_mock.fail_reads(ride)
    _cancel(courier.cancel_ride(order, actor="operator:maria"))
    assert courier_mock.rides()[ride]["cancel_reasons"] == [10, 12]
    assert courier_mock.rides()[ride]["status"] == "C"
    task = Directive.objects.get(topic=COURIER_CANCEL)
    assert task.payload["cancel_attempt"]["state"] == "accepted"
    assert task.payload["cancel_attempt"]["reasons"] == [10, 12]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ride_already_cancelled_at_the_central_is_adopted_without_a_post(shop):
    order = _dispatched_order(shop)
    ride = _ride(order)
    task = courier.cancel_ride(order, actor="operator:maria")
    courier_mock.set_status(ride, "C")
    _cancel(task)
    assert "cancel_reasons" not in courier_mock.rides()[ride]
    order.refresh_from_db()
    assert not courier.has_active_ride(order)
    assert courier.get_block(order)["attempts"][-1]["status"] == "C"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_unknown_reason_is_refused_before_anything_is_queued(shop):
    order = _dispatched_order(shop)
    with pytest.raises(ValueError, match="Motivo de cancelamento desconhecido"):
        courier.cancel_ride(order, actor="operator:maria", reason_id=10)
    assert not Directive.objects.filter(topic=COURIER_CANCEL).exists()


# ── a recusa nunca fica muda ────────────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_refusal_alerts_tells_the_screen_and_keeps_the_ride(shop, sse, monkeypatch):
    order = _dispatched_order(shop)
    ride = _ride(order)
    order.refresh_from_db()
    assert courier.ride_letter(courier.get_block(order)["ride_number"]) == "A"

    def refuse(courier_ref, *, reason_id):
        raise CourierError("Machine recusou (400): [67] O usuário informado não pode realizar essa operação.",
                           transient=False, codes=(67,))

    monkeypatch.setattr(courier_mock, "cancel", refuse)
    task = courier.cancel_ride(order, actor="operator:maria")
    with pytest.raises(DirectiveTerminalError, match="recusou"):
        _cancel(task)

    task.refresh_from_db()
    assert task.payload["cancel_attempt"]["state"] == "refused"
    order.refresh_from_db()
    assert _ride(order) == ride and courier.has_active_ride(order)
    message = "A TaOn não cancelou a corrida A. Cancele pela central da TaOn."
    alert = OperatorAlert.objects.get(order_ref=order.ref, type="integration_failed")
    assert (alert.severity, alert.message) == ("critical", message)
    assert (order.ref, "cancel_failed") in sse
    # A tela mostra a recusa e segue oferecendo o cancelar (a corrida está aberta).
    panel = _courier_block(order)
    assert panel["cancel_state"]["state"] == "failed"
    assert panel["cancel_state"]["message"] == message
    assert panel["can_cancel"] is True
    assert panel["error"] is None
    # Replay da tarefa recusada não chama a central de novo nem duplica o aviso.
    _cancel(task)
    assert OperatorAlert.objects.filter(order_ref=order.ref, type="integration_failed").count() == 1


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_pending_cancellation_hides_the_button_and_says_so(shop):
    order = _dispatched_order(shop)
    courier.cancel_ride(order, actor="operator:maria")
    panel = _courier_block(order)
    assert panel["cancel_state"]["state"] == "pending"
    assert panel["cancel_state"]["message"] == "Pedido de cancelamento enviado. Esperando a TaOn confirmar."
    assert panel["can_cancel"] is False


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ride_collected_at_the_central_is_never_cancelled(shop):
    """A central já diz "coletou" e o pedido ainda não soube: nada é enviado, a leitura vem já."""
    order = _dispatched_order(shop)
    ride = _ride(order)
    task = courier.cancel_ride(order, actor="operator:maria")
    courier_mock.set_status(ride, "E")
    _cancel(task)
    assert "cancel_reasons" not in courier_mock.rides()[ride]
    task.refresh_from_db()
    assert task.payload["cancel_attempt"]["state"] == "not_applied"
    assert Directive.objects.filter(topic=COURIER_SYNC, payload__order_ref=order.ref, status="queued").exists()


# ── a régua única do "dá para cancelar" ─────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_collected_ride_is_not_cancellable_at_any_door_even_with_a_late_letter(shop):
    """A sacola está na moto (``dispatched_at``): uma letra atrasada não devolve o cancelar."""
    from shopman.backstage.projections.deliveries import build_deliveries

    order = _dispatched_order(shop)
    block = dict(courier.get_block(order))
    block.update(status="A", dispatched_at="2026-11-16T14:00:00+00:00")  # "aceita" atrasada depois da coleta
    order.data = {**order.data, "courier": block}
    order.status = Order.Status.DISPATCHED
    order.save(update_fields=["data", "status"])

    assert courier.ride_cancellable(courier.get_block(order)) is False
    assert _courier_block(order)["can_cancel"] is False
    ride = next(r for r in build_deliveries().rides if r.lead_ref == order.ref)
    assert ride.cancel_action is None
    with pytest.raises(ValueError, match="em rota"):
        courier.cancel_ride(order, actor="operator:maria")
    assert courier.charge_outdated(order) is None or courier.charge_outdated(order)["collected"] is True


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_worker_does_not_cancel_a_ride_collected_after_the_request(shop):
    order = _dispatched_order(shop)
    ride = _ride(order)
    task = courier.cancel_ride(order, actor="operator:maria")
    block = dict(courier.get_block(order))
    block.update(status="A", dispatched_at="2026-11-16T14:00:00+00:00")
    order.data = {**order.data, "courier": block}
    order.save(update_fields=["data"])
    _cancel(task)
    assert "cancel_reasons" not in courier_mock.rides()[ride]
    task.refresh_from_db()
    assert task.payload["cancel_attempt"]["state"] == "not_applied"


# ── a corrida com vários pedidos se cancela inteira ─────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_cancelling_a_group_ride_frees_every_order_of_it(shop, sse):
    a, b, c = _at("CR-A", -23.30, -51.16), _at("CR-B", -23.335, -51.158), _at("CR-C", -23.25, -51.17)
    ride = _group(a, b, c)
    _cancel(courier.cancel_ride(a, actor="operator:maria"))
    assert courier_mock.rides()[ride]["cancel_reasons"] == [10]
    for order in (a, b, c):
        order.refresh_from_db()
        block = courier.get_block(order)
        assert not courier.has_active_ride(order), order.ref
        assert "ride_ref" not in block and block["attempts"][-1]["status"] == "C"
        assert not courier.ride_is_live(order)  # a letra e a cor voltam a ficar livres
        assert (order.ref, "cancel_queued") in sse
    # Quem cancelou foi o operador: nenhum aviso de "a TaOn cancelou".
    assert not OperatorAlert.objects.filter(type="courier_ride_cancelled").exists()


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_one_cancellation_per_ride_whichever_order_asks(shop):
    a, b = _at("CR-A", -23.30, -51.16), _at("CR-B", -23.335, -51.158)
    ride = _group(a, b)
    first = courier.cancel_ride(b, actor="operator:maria")
    again = courier.cancel_ride(a, actor="operator:maria")
    assert again.pk == first.pk
    assert Directive.objects.filter(topic=COURIER_CANCEL).count() == 1
    assert first.dedupe_key == f"courier.cancel:{ride}"
    # A tarefa aponta para o primeiro pedido da corrida e leva todos os dela.
    assert first.payload["order_ref"] == courier.ride_orders(a)[0]
    assert sorted(first.payload["order_refs"]) == ["CR-A", "CR-B"]
    # O pedido de cancelamento aparece em qualquer pedido da corrida.
    assert _courier_block(a)["cancel_state"]["state"] == "pending"
    assert _courier_block(b)["cancel_state"]["state"] == "pending"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_sync_releases_orders_stranded_in_a_ride_the_lead_already_ended(shop):
    """Só o primeiro pedido recebeu o C (falha no meio): a batida solta os outros."""
    a, b = _at("CR-A", -23.30, -51.16), _at("CR-B", -23.335, -51.158)
    ride = _group(a, b)
    lead_ref = courier.ride_orders(a)[0]
    lead, other = (a, b) if lead_ref == a.ref else (b, a)
    courier.apply_status(lead, "C", source="operator:maria")
    other.refresh_from_db()
    assert courier.get_block(other)["ride_ref"] == ride  # preso: "Procurando entregador" para sempre

    CourierSyncHandler().handle(message=Directive.objects.filter(topic=COURIER_SYNC).last(), ctx={})
    other.refresh_from_db()
    assert not courier.has_active_ride(other)
    assert courier.get_block(other)["attempts"][-1]["status"] == "C"
    assert not courier.ride_is_live(other)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_last_live_order_cancelled_takes_the_ride_with_it(shop):
    """Os dois pedidos da corrida foram cancelados: ninguém mais espera o entregador."""
    a, b = _at("CR-A", -23.30, -51.16), _at("CR-B", -23.335, -51.158)
    ride = _group(a, b)
    Order.objects.filter(pk=a.pk).update(status=Order.Status.CANCELLED)
    a.refresh_from_db()
    courier.on_order_cancelled(a)
    assert not Directive.objects.filter(topic=COURIER_CANCEL).exists()  # B ainda espera
    Order.objects.filter(pk=b.pk).update(status=Order.Status.CANCELLED)
    b.refresh_from_db()
    courier.on_order_cancelled(b)
    task = Directive.objects.get(topic=COURIER_CANCEL)
    assert task.payload["intent"] == courier_machine.CANCEL_INTENT_ORDER_CANCELLED
    _cancel(task)
    assert courier_mock.rides()[ride]["status"] == "C"
    for order in (a, b):
        order.refresh_from_db()
        assert not courier.has_active_ride(order)


# ── o aceite tardio de pedido cancelado ─────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_ride_opened_for_an_order_cancelled_meanwhile_is_cancelled_once(shop, monkeypatch):
    """O pedido foi cancelado enquanto a TaOn abria a corrida: ela não fica aberta e paga."""
    order = _delivery_order(ref="NB-261116-A47")
    task = courier.request_dispatch(order, actor="operator:ana")
    original = courier_mock.dispatch

    def cancel_meanwhile(payload):
        result = original(payload)
        Order.objects.filter(pk=order.pk).update(status=Order.Status.CANCELLED)
        return result

    monkeypatch.setattr(courier_mock, "dispatch", cancel_meanwhile)
    CourierDispatchHandler().handle(message=task, ctx={})
    order.refresh_from_db()
    ride = _ride(order)

    cancel = Directive.objects.get(topic=COURIER_CANCEL)
    assert cancel.payload["courier_ref"] == ride
    alert = OperatorAlert.objects.get(order_ref=order.ref, type="integration_failed")
    assert alert.message == ("O pedido A47 foi cancelado enquanto a TaOn abria a corrida. "
                             "Pedimos à TaOn o cancelamento da corrida.")
    # Nenhum aviso falso de "a corrida não abriu, chame de novo".
    assert not OperatorAlert.objects.filter(type="courier_dispatch_failed").exists()
    assert "error" not in courier.get_block(order)

    # Replay da tarefa de despacho (aceite já gravado): uma solicitação só, um aviso só.
    CourierDispatchHandler().handle(message=Directive.objects.get(topic=COURIER_DISPATCH), ctx={})
    assert Directive.objects.filter(topic=COURIER_CANCEL).count() == 1
    assert OperatorAlert.objects.filter(order_ref=order.ref, type="integration_failed").count() == 1

    _cancel(cancel)
    assert courier_mock.rides()[ride]["status"] == "C"
    assert courier_mock.rides()[ride]["cancel_reasons"] == [10]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_group_ride_opened_with_one_order_cancelled_keeps_the_ride_of_the_other(shop, monkeypatch):
    a, b = _at("NB-261116-A47", -23.30, -51.16), _at("NB-261116-C03", -23.335, -51.158)
    task = courier.request_group_dispatch([a, b], actor="operator:ana")
    original = courier_mock.dispatch

    def cancel_meanwhile(payload):
        result = original(payload)
        Order.objects.filter(pk=a.pk).update(status=Order.Status.CANCELLED)
        return result

    monkeypatch.setattr(courier_mock, "dispatch", cancel_meanwhile)
    CourierDispatchHandler().handle(message=task, ctx={})
    assert not Directive.objects.filter(topic=COURIER_CANCEL).exists()
    alert = OperatorAlert.objects.get(order_ref=a.ref)
    assert "tirar a parada" in alert.message
    assert not OperatorAlert.objects.filter(type="courier_dispatch_failed").exists()
    b.refresh_from_db()
    assert courier.has_active_ride(b)


# ── a confirmação que a tela mostra ─────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_confirmation_asks_only_to_confirm_before_accept_and_the_reason_after(shop):
    a, b = _at("NB-261116-A05", -23.335, -51.158), _at("NB-261116-C12", -23.30, -51.16)
    ride = _group(a, b)
    before = courier_cancel_confirmation(a)
    assert before == {
        "required": True,
        "description": "Cancelar a corrida A? A05 e C12 voltam para Aguardando.",
        "confirm_label": "Cancelar a corrida A",
    }

    courier_mock.set_status(ride, "A")
    for order in (a, b):
        courier.apply_status(order, "A", source="poll")
        order.refresh_from_db()
    after = courier_cancel_confirmation(b)
    assert after["description"] == "Cancelar a corrida A? A05 e C12 voltam para Aguardando."
    assert after["reason_question"] == "Por que cancelar a corrida A?"
    assert after["consequence"] == "A05 e C12 voltam para Aguardando."
    assert after["reasons"] == [
        {"id": 12, "label": "O entregador não está vindo"},
        {"id": 37, "label": "Está demorando demais"},
        {"id": 40, "label": "Não consegui falar com o entregador"},
    ]


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_confirmation_of_a_single_order_ride(shop):
    order = _dispatched_order(shop, ref="NB-261116-B07")
    assert courier.cancel_question(order) == "Cancelar a corrida A? B07 volta para Aguardando."
