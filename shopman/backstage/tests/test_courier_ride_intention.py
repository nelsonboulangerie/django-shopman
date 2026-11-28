"""Chamar UMA corrida para vários pedidos passa pelo protocolo de intenção.

O defeito (revisão das Entregas, 16/11/2026, P1-6): o ``courier-ride`` não
conferia quem chamava, o que a tela tinha lido nem a chave da intenção. A
corrida saía com endereço ou troco que o operador não viu, o retry depois de
rede caída virava "já pedida" e, com outra pessoa identificada, a corrida saía
no nome errado. Aqui cada uma dessas portas tem o seu teste.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import connection, connections
from django.test import override_settings
from django.urls import reverse
from shopman.orderman.models import Directive, Order

from shopman.backstage.projections.deliveries import build_deliveries
from shopman.shop.adapters import courier_mock
from shopman.shop.directives import COURIER_DISPATCH
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.models import Shop
from shopman.shop.services import courier
from shopman.shop.tests.test_courier_service import _delivery_order

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
PAID = {"method": "pix", "status": "captured"}
URL = "api-backstage-order-courier-ride"


@pytest.fixture(autouse=True)
def _mock_courier():
    courier_mock.reset()
    cache.clear()
    with override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER):
        yield
    courier_mock.reset()


@pytest.fixture
def shop():
    return Shop.objects.create(name="Loja", route="Rua da Loja", street_number="10", city="Londrina",
                               state_code="PR", latitude=-23.34, longitude=-51.15)


def _manager(username: str) -> User:
    user = User.objects.create_user(username, password="pw", is_staff=True)
    user.user_permissions.add(Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"), codename="manage_orders"))
    return user


@pytest.fixture
def operator(client, shop):
    user = _manager("marina")
    client.force_login(user)
    return user


def _pair():
    return _delivery_order(ref="RI-A", payment=PAID), _delivery_order(ref="RI-B", payment=PAID)


def _observed(operator) -> dict:
    """O que a tela das Entregas leu: a ação ``group_action`` da projeção."""
    action = build_deliveries(user=operator).group_action
    assert action is not None and action.enabled and action.ref == "courier-ride"
    return dict(action.payload_schema)


def _post(client, body, key):
    return client.post(reverse(URL), body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)


def _tasks():
    return Directive.objects.filter(topic=COURIER_DISPATCH)


# ── A projeção entrega a ação pronta ────────────────────────────────


def test_deliveries_projection_offers_the_group_action_with_each_revision(operator):
    a, b = _pair()
    # Já tem corrida aberta: não entra em outra, e fica fora da ação.
    busy = _delivery_order(ref="RI-C", payment=PAID)
    CourierDispatchHandler().handle(message=courier.request_dispatch(busy, actor="operator:ana"), ctx={})
    schema = _observed(operator)
    assert schema["expected_actor_id"] == operator.pk
    # Só quem pode entrar numa corrida com outros; cada um com o que a tela leu dele.
    assert schema["base_revisions"] == {a.ref: courier.dispatch_revision(a), b.ref: courier.dispatch_revision(b)}


def test_group_action_is_absent_with_fewer_than_two_orders(operator):
    _delivery_order(ref="RI-A", payment=PAID)
    assert build_deliveries(user=operator).group_action is None


def test_the_call_sheet_reads_the_ride_action_with_the_companions_from_deliveries(client, operator):
    # O sheet único (#2876) chama pela ação de grupo das Entregas; o detalhe do pedido
    # não monta mais a dele (#3003).
    from shopman.backstage.projections.deliveries import build_deliveries

    a, b = _pair()
    action = build_deliveries(user=operator).group_action
    assert action is not None and action.ref == "courier-ride"
    assert action.enabled and action.idempotency == "required"
    assert action.payload_schema["expected_actor_id"] == operator.pk
    assert action.payload_schema["base_revisions"] == {
        a.ref: courier.dispatch_revision(a), b.ref: courier.dispatch_revision(b),
    }
    detail = client.get(reverse("api-backstage-order-detail", args=[a.ref])).json()["order"]
    assert "courier-ride" not in [row["ref"] for row in detail["actions"]]


# ── As quatro portas ────────────────────────────────────────────────


def test_ride_without_the_observed_intention_is_refused(client, operator):
    _pair()
    schema = _observed(operator)

    no_key = client.post(reverse(URL), {**schema, "refs": ["RI-A", "RI-B"]}, content_type="application/json")
    assert (no_key.status_code, no_key.json()["code"]) == (400, "intention_required")

    # Faltou a revisão de um dos pedidos: a tela está velha.
    partial = {**schema, "refs": ["RI-A", "RI-B"], "base_revisions": {"RI-A": schema["base_revisions"]["RI-A"]}}
    missing = _post(client, partial, "ride-missing")
    assert (missing.status_code, missing.json()["code"]) == (400, "intention_required")

    assert not _tasks().exists()


def test_ride_called_under_another_identity_is_refused(client, operator):
    """A tela foi lida pela Marina; quem está identificado agora é o Pedro."""
    _pair()
    schema = _observed(operator)
    client.force_login(_manager("pedro"))

    response = _post(client, {**schema, "refs": ["RI-A", "RI-B"]}, "ride-actor")

    assert (response.status_code, response.json()["code"]) == (409, "actor_changed")
    assert not _tasks().exists()
    assert "called_by" not in courier.get_block(Order.objects.get(ref="RI-A"))


def test_ride_refuses_the_order_that_changed_and_names_it(client, operator):
    """O endereço de um pedido mudou por outra porta depois que a tela foi lida."""
    a, b = _pair()
    schema = _observed(operator)
    b.data = {**b.data, "delivery_address_structured": {**b.data["delivery_address_structured"], "route": "Outra rua"}}
    b.save(update_fields=["data"])

    response = _post(client, {**schema, "refs": [a.ref, b.ref]}, "ride-stale")

    body = response.json()
    assert response.status_code == 409, body
    assert body["code"] == body["error"]["code"] == "revision_changed"
    assert body["outcome"] == "not_applied"
    assert list(body["errors"]) == [b.ref]
    assert "mudou" in body["detail"]
    # Nada gravado: nem tarefa, nem número, nem "chamado por".
    assert not _tasks().exists()
    for ref in (a.ref, b.ref):
        assert "ride_number" not in courier.get_block(Order.objects.get(ref=ref))

    # Tela recarregada (revisões novas, chave nova): agora chama.
    fresh = _post(client, {**_observed(operator), "refs": [a.ref, b.ref]}, "ride-fresh")
    assert fresh.status_code == 200, fresh.content
    assert _tasks().count() == 1


def test_one_touch_one_ride_and_the_retry_replays_the_same_result(client, operator):
    """A resposta se perdeu na rede: a mesma chave devolve a mesma corrida."""
    _pair()
    body = {**_observed(operator), "refs": ["RI-A", "RI-B"]}

    first = _post(client, body, "ride-once")
    assert first.status_code == 200, first.content
    assert first.json()["outcome"] == "applied" and first.json()["replayed"] is False
    assert (first.json()["ride_number"], first.json()["ride_letter"]) == (1, "A")

    retry = _post(client, body, "ride-once")
    assert retry.status_code == 200
    assert retry.json()["replayed"] is True
    assert retry.json()["directive_id"] == first.json()["directive_id"]
    assert _tasks().count() == 1

    # O recibo responde sem executar nada.
    receipt = client.get(reverse(URL), {"idempotency_key": "ride-once"})
    assert (receipt.status_code, receipt.json()["outcome"]) == (200, "applied")
    unknown = client.get(reverse(URL), {"idempotency_key": "never-sent"})
    assert (unknown.status_code, unknown.json()["outcome"]) == (202, "unknown")
    assert _tasks().count() == 1


def test_the_same_key_never_carries_a_different_ride(client, operator):
    _pair()
    _delivery_order(ref="RI-D", payment=PAID)
    schema = _observed(operator)
    assert _post(client, {**schema, "refs": ["RI-A", "RI-B"]}, "ride-key").status_code == 200

    other = _post(client, {**schema, "refs": ["RI-A", "RI-D"]}, "ride-key")

    assert (other.status_code, other.json()["code"]) == (409, "intention_conflict")
    assert _tasks().count() == 1


def test_ride_already_open_with_the_same_orders_counts_as_done(client, operator):
    """Outro dispositivo já chamou e a TaOn já abriu: pedir de novo é feito, sem gravar nada."""
    a, b = _pair()
    schema = _observed(operator)
    assert _post(client, {**schema, "refs": [a.ref, b.ref]}, "ride-open").status_code == 200
    CourierDispatchHandler().handle(message=_tasks().get(), ctx={})
    assert courier.has_active_ride(Order.objects.get(ref=a.ref))

    # A tela velha (revisões de antes da chamada) pede a mesma corrida.
    again = _post(client, {**schema, "refs": [b.ref, a.ref]}, "ride-open-again")

    assert again.status_code == 200, again.content
    assert again.json()["already_called"] is True
    assert again.json()["outcome"] == "applied"
    assert again.json()["ride_letter"] == "A"
    assert "já tinha sido chamada" in again.json()["detail"]
    assert _tasks().count() == 1
    assert len(courier_mock.rides()) == 1


# ── O número (a letra) da corrida ───────────────────────────────────


def test_ride_keeps_the_number_the_screen_showed_when_it_is_still_free(client, operator):
    _pair()
    response = _post(client, {**_observed(operator), "refs": ["RI-A", "RI-B"], "ride_number": 3}, "ride-c")
    assert response.status_code == 200, response.content
    assert (response.json()["ride_number"], response.json()["ride_letter"]) == (3, "C")
    assert {courier.get_block(Order.objects.get(ref=ref))["ride_number"] for ref in ("RI-A", "RI-B")} == {3}


def test_ride_takes_the_next_free_number_when_the_shown_one_was_taken(client, operator):
    taken = _delivery_order(ref="RI-T", payment=PAID)
    courier.request_dispatch(taken, actor="operator:ana")
    assert courier.get_block(taken)["ride_number"] == 1
    _pair()

    response = _post(client, {**_observed(operator), "refs": ["RI-A", "RI-B"], "ride_number": 1}, "ride-next")

    assert response.status_code == 200, response.content
    assert (response.json()["ride_number"], response.json()["ride_letter"]) == (2, "B")


def test_ride_number_out_of_the_alphabet_is_a_field_error(client, operator):
    _pair()
    response = _post(client, {**_observed(operator), "refs": ["RI-A", "RI-B"], "ride_number": 27}, "ride-bad")
    assert response.status_code == 400
    assert response.json()["field"] == "ride_number"
    assert not _tasks().exists()


def test_single_dispatch_also_keeps_the_number_the_screen_showed(client, operator):
    order = _delivery_order(ref="RI-S", payment=PAID)
    stop = next(row for row in build_deliveries(user=operator).waiting if row.ref == order.ref)
    body = {**stop.dispatch_action.payload_schema, "ride_number": 4}

    response = client.post(reverse("api-backstage-order-courier-dispatch", args=[order.ref]), body,
                           content_type="application/json", HTTP_IDEMPOTENCY_KEY="single-d")

    assert response.status_code == 200, response.content
    assert (response.json()["ride_number"], response.json()["ride_letter"]) == (4, "D")


def test_seventh_live_ride_gets_its_own_letter_instead_of_repeating(shop):
    """Seis cores, 26 letras: a sétima corrida repete a cor, nunca a letra."""
    for index in range(7):
        order = _delivery_order(ref=f"RI-{index}", payment=PAID)
        courier.request_dispatch(order, actor="operator:ana")
    numbers = [courier.get_block(Order.objects.get(ref=f"RI-{index}"))["ride_number"] for index in range(7)]
    assert numbers == [1, 2, 3, 4, 5, 6, 7]
    assert courier.ride_letter(numbers[-1]) == "G"
    assert courier.free_ride_numbers()[0] == 8


def test_deliveries_projection_says_which_numbers_are_free(operator):
    busy = _delivery_order(ref="RI-T", payment=PAID)
    courier.request_dispatch(busy, actor="operator:ana")
    projection = build_deliveries(user=operator)
    assert projection.next_number == 2
    assert projection.free_numbers[:3] == (2, 3, 4)
    assert len(projection.free_numbers) == courier.RIDE_LETTERS - 1


# ── Duas chamadas ao mesmo tempo (Postgres de verdade) ──────────────


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(connection.vendor != "postgresql", reason="Requires independent PostgreSQL connections")
def test_two_calls_at_the_same_time_never_share_a_number(shop, monkeypatch):
    """Dois dispositivos chamam no mesmo instante: cada corrida sai com a sua letra.

    Sem a trava (``courier._lock_ride_numbers``) as duas liam o mesmo "menor
    livre" antes de qualquer uma gravar. A leitura fica lenta de propósito para
    a corrida entre as duas ser certa, e não sorte.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    orders = [_delivery_order(ref="RI-X", payment=PAID), _delivery_order(ref="RI-Y", payment=PAID)]
    read = courier._live_ride_numbers

    def slow_read(exclude_refs=()):
        live = read(exclude_refs)
        time.sleep(0.4)
        return live

    monkeypatch.setattr(courier, "_live_ride_numbers", slow_read)
    barrier = Barrier(2)

    def call(order):
        try:
            barrier.wait(timeout=10)
            courier.request_dispatch(order, actor="operator:ana")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        for job in [pool.submit(call, order) for order in orders]:
            job.result(timeout=30)

    numbers = sorted(courier.get_block(Order.objects.get(ref=order.ref))["ride_number"] for order in orders)
    assert numbers == [1, 2]
