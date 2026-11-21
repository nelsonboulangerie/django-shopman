"""O selo de Entregas no menu e a nota fiscal na página Entregas (F10 da revisão
das Entregas/TaOn, ENT-PERF-14, J12 e ENT-19).

- O selo conta o que aguarda entregador com a MESMA régua da lista Aguardando,
  numa consulta de pedidos (e uma das tarefas de despacho, só quando há corrida
  chamada à espera da central), qualquer que seja o número de pedidos.
- Se a contagem falhar, o selo recebe ``null`` e a tela mostra "?": zero diria
  "nada aguardando", e isso seria mentira.
- A página Entregas diz quando um pedido está com a NFC-e não autorizada ou com
  a DANFE por imprimir, com os MESMOS campos do cartão do Gestor. Só avisa: a
  chamada e a saída seguem (dono, 17/09/2026).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from shopman.orderman.models import Directive, Order

from shopman.backstage.projections import deliveries as deliveries_projection
from shopman.backstage.projections.deliveries import build_deliveries, deliveries_waiting_count
from shopman.backstage.tests.test_deliveries_projection import MOCK_ADAPTER, _at, _call
from shopman.shop.adapters import courier_mock
from shopman.shop.directives import FISCAL_EMIT_NFCE
from shopman.shop.models import Shop
from shopman.shop.services import courier

pytestmark = [pytest.mark.django_db, pytest.mark.channels("web", "pdv")]

#: O teto do selo: os pedidos numa consulta e as tarefas de despacho em outra.
COUNT_QUERY_CEILING = 2


@pytest.fixture(autouse=True)
def _clean_mock():
    courier_mock.reset()
    yield
    courier_mock.reset()


@pytest.fixture
def shop():
    return Shop.objects.create(
        name="Nelson Boulangerie", route="Av. Madre Leônia Milito", street_number="446",
        neighborhood="Bela Suíça", city="Londrina", state_code="PR",
        latitude=-23.3405, longitude=-51.1580,
    )


def _board(waiting: int) -> None:
    """``waiting`` entregas aguardando, uma corrida na rua e uma chamada sem resposta ainda."""
    for index in range(waiting):
        _at(f"EN-{index}", -23.30, -51.16)
    _call(_at("EN-RUA", -23.31, -51.16))
    # Chamada que a central ainda não respondeu: a tarefa está na fila, a corrida
    # já tem número (ocupa uma letra) e não tem ``ride_ref``.
    courier.request_dispatch(_at("EN-FILA", -23.32, -51.16), actor="operator:ana")


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
@pytest.mark.parametrize("waiting", [1, 8])
def test_the_badge_counts_under_a_fixed_ceiling_of_queries(shop, waiting, django_assert_max_num_queries):
    _board(waiting)
    pending = Order.objects.get(ref="EN-FILA")
    assert courier.get_block(pending).get("ride_number") and not courier.get_block(pending).get("ride_ref")

    with django_assert_max_num_queries(COUNT_QUERY_CEILING):
        count = deliveries_waiting_count()

    # A mesma régua da lista: a corrida na rua e a chamada na fila não aguardam.
    assert count == waiting == len(build_deliveries().waiting)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_badge_reads_orders_in_one_query_when_no_call_waits_for_the_provider(shop, django_assert_num_queries):
    for index in range(5):
        _at(f"EN-{index}", -23.30, -51.16)
    _call(_at("EN-RUA", -23.31, -51.16))

    with django_assert_num_queries(1):
        assert deliveries_waiting_count() == 5


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_the_page_does_not_grow_one_query_per_order(shop):
    """As tarefas de despacho, a NFC-e e a DANFE vêm em lote: a página com oito
    pedidos lê o banco tantas vezes quanto a de um."""

    def queries() -> int:
        with CaptureQueriesContext(connection) as captured:
            build_deliveries()
        return len(captured)

    _board(1)
    few = queries()
    for index in range(1, 8):
        _at(f"EN-{index}", -23.30, -51.16)
    assert queries() == few


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_failed_count_is_unknown_never_zero(shop, monkeypatch):
    _at("EN-A", -23.30, -51.16)

    def broken():
        raise RuntimeError("banco fora")

    monkeypatch.setattr(deliveries_projection, "_delivery_orders", broken)
    assert deliveries_waiting_count() is None

    user = get_user_model().objects.create_user("gestor", password="x", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders"))
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/v1/backstage/deliveries/count/").json() == {"waiting": None, "call_refs": []}


def _fiscal_failed(order: Order) -> None:
    Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref})


def _authorized_nfce(order: Order) -> None:
    order.data = {**order.data, "nfce_access_key": "4" * 44}
    order.save(update_fields=["data"])


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_stop_says_when_the_nfce_failed_and_the_call_still_goes(shop):
    order = _at("EN-A", -23.30, -51.16)
    _fiscal_failed(order)

    (stop,) = build_deliveries().waiting
    assert stop.fiscal_status == "failed"
    # Só avisa: o "Chamar sozinho" continua lá, e o pedido entra em corrida.
    assert stop.dispatch_action is not None
    assert stop.group_refusal == ""


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_ride_stop_carries_the_danfe_still_to_print(shop):
    order = _at("EN-A", -23.30, -51.16)
    _call(order)
    for status in ("A", "E"):
        courier.apply_status(order, status, source="test")
        order.refresh_from_db()
    assert order.status == Order.Status.DISPATCHED
    _authorized_nfce(order)
    Order.objects.filter(pk=order.pk).update(dispatched_at=None)

    (ride,) = build_deliveries().rides
    (stop,) = ride.stops
    assert stop.fiscal_status == "authorized"
    # A MESMA leitura do cartão do Gestor: saiu do despacho sem a DANFE impressa.
    assert stop.danfe_state == "not_printed"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_stop_with_nothing_fiscal_to_do_says_nothing(shop):
    _at("EN-A", -23.30, -51.16)

    (stop,) = build_deliveries().waiting
    assert stop.fiscal_status != "failed"
    assert stop.danfe_state in ("", "on_dispatch")
