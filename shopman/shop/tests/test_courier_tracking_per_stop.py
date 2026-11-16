"""O link de rastreio é o da parada DESTE pedido, ou não existe.

Corrida com várias paradas tem um link por parada, e cada link mostra a entrega
de um cliente. Até 16/11/2026 todo pedido da corrida gravava ``links[0]``: o
cliente B recebia, no aviso de saída e no botão "Acompanhar o entregador" da
página dele, a entrega do cliente A. Aqui o casamento é provado ou o link some.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings
from shopman.orderman.models import Directive

from shopman.shop.adapters import courier_machine, courier_mock
from shopman.shop.directives import COURIER_SYNC
from shopman.shop.handlers.courier_dispatch import CourierDispatchHandler
from shopman.shop.handlers.courier_sync import CourierSyncHandler
from shopman.shop.models import Shop
from shopman.shop.projections.order_tracking import _courier_tracking_url
from shopman.shop.services import courier
from shopman.shop.services.notification import _build_context
from shopman.shop.tests.test_courier_service import _delivery_order

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
PAID = {"method": "pix", "status": "captured"}
REFS = ["TRK-B", "TRK-A", "TRK-C"]  # a ordem das paradas que vai à TaOn


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


def _at(ref, lat, lng):
    order = _delivery_order(ref=ref, payment=PAID)
    address = dict(order.data["delivery_address_structured"], latitude=lat, longitude=lng)
    order.data = {**order.data, "delivery_address_structured": address}
    order.save(update_fields=["data"])
    return order


def _three_stop_ride():
    """A loja fica em (-23.3405, -51.1580): B é a mais perto, depois A, depois C."""
    orders = {
        "TRK-A": _at("TRK-A", -23.30, -51.16),
        "TRK-B": _at("TRK-B", -23.335, -51.158),
        "TRK-C": _at("TRK-C", -23.25, -51.17),
    }
    directive = courier.request_group_dispatch(list(orders.values()), actor="operator:ana")
    CourierDispatchHandler().handle(message=directive, ctx={})
    for order in orders.values():
        order.refresh_from_db()
    ride_id = courier.get_block(orders["TRK-B"])["id_mch"]
    assert courier.get_block(orders["TRK-A"])["ride_orders"] == REFS
    return orders, ride_id


def _read(ride_id, status):
    courier_mock.set_status(ride_id, status)
    CourierSyncHandler().handle(message=Directive.objects.filter(topic=COURIER_SYNC).last(), ctx={})


def _link(ref):
    return f"https://rastreio.mock/parada-de/{ref}"


def _entry(ref, *, stop, key="id_externo", code=None):
    entry = {"parada_id": str(stop), "link_rastreio": _link(ref), "codigo_confirmacao": code}
    if key:
        entry[key] = ref
    return entry


def _suffix(order):
    return _build_context(order, {"order_ref": order.ref}, "order_dispatched")["courier_tracking_suffix"]


# ── O casamento, puro ───────────────────────────────────────────────


@pytest.mark.parametrize("key", ["id_externo", "numero_pedido"])
def test_the_entry_that_names_the_order_wins_whatever_the_list_order(key):
    shuffled = [_entry("TRK-C", stop=3, key=key, code=3003), _entry("TRK-A", stop=2, key=key, code=2002),
                _entry("TRK-B", stop=1, key=key, code=1001)]
    for ref, code in (("TRK-A", "2002"), ("TRK-B", "1001"), ("TRK-C", "3003")):
        assert courier.link_for_order(ref, REFS, shuffled) == {
            "tracking_url": _link(ref), "confirmation_code": code, "tracking_match": "id",
        }


def test_a_list_that_names_the_others_and_not_this_order_gives_nothing():
    """A lista fala em pedidos: a posição não vale para quem ela não nomeou."""
    links = [_entry("TRK-B", stop=1), _entry("TRK-A", stop=2), {"parada_id": "3", "link_rastreio": _link("?")}]
    assert courier.link_for_order("TRK-C", REFS, links) == {}
    # Nomeado duas vezes também não é prova.
    twice = [_entry("TRK-B", stop=1), _entry("TRK-B", stop=2), _entry("TRK-C", stop=3)]
    assert courier.link_for_order("TRK-B", REFS, twice) == {}


def test_one_entry_per_stop_in_the_sent_order_matches_by_position():
    links = [_entry(ref, stop=index, key=None) for index, ref in enumerate(REFS, start=1)]
    for ref in REFS:
        found = courier.link_for_order(ref, REFS, links)
        assert (found["tracking_url"], found["tracking_match"]) == (_link(ref), "position")


@pytest.mark.parametrize(
    "links",
    [
        # O formato único do OpenAPI v1 (``{"link"}``), como o adapter o entrega.
        [{"parada_id": "", "link_rastreio": "https://rastreio.mock/unico", "codigo_confirmacao": None}],
        # Uma parada a menos e uma a mais do que a corrida tem.
        [_entry("x", stop=1, key=None), _entry("y", stop=2, key=None)],
        [_entry(str(n), stop=n, key=None) for n in range(1, 5)],
        # Três entradas que não são uma por parada: parada ou link repetido.
        [_entry("x", stop=1, key=None), _entry("y", stop=1, key=None), _entry("z", stop=3, key=None)],
        [_entry("x", stop=1, key=None), _entry("x", stop=2, key=None), _entry("z", stop=3, key=None)],
        [],
    ],
    ids=["formato-unico", "faltou-parada", "sobrou-parada", "parada-repetida", "link-repetido", "vazio"],
)
def test_no_proof_no_link_in_a_ride_with_several_stops(links):
    for ref in REFS:
        assert courier.link_for_order(ref, REFS, links) == {}


def test_the_stop_already_recorded_on_the_order_picks_its_entry():
    """Lista de outro tamanho, mas o pedido já sabe qual é a sua parada (``courier.stop_id``)."""
    links = [_entry("x", stop=71, key=None), _entry("y", stop=72, key=None), _entry("z", stop=73, key=None),
             _entry("volta", stop=74, key=None)]
    found = courier.link_for_order("TRK-A", REFS, links, stop_id="72")
    assert (found["tracking_url"], found["tracking_match"]) == (_link("y"), "stop")
    assert courier.link_for_order("TRK-A", REFS, links, stop_id="99") == {}


def test_a_ride_of_one_order_keeps_its_link_in_both_formats():
    """Sem outro cliente na rota, não há link alheio para vazar."""
    single = [{"parada_id": "", "link_rastreio": "https://rastreio.mock/unico", "codigo_confirmacao": None}]
    assert courier.link_for_order("TRK-A", None, single) == {
        "tracking_url": "https://rastreio.mock/unico", "confirmation_code": "", "tracking_match": "single",
    }
    with_return = [_entry("ida", stop=1, key=None, code=4321), _entry("volta", stop=2, key=None)]
    assert courier.link_for_order("TRK-A", ["TRK-A"], with_return)["tracking_url"] == _link("ida")


def test_the_machine_adapter_turns_the_single_format_into_one_entry(monkeypatch):
    """O ``{"link"}`` único chega ao casamento como UMA entrada: numa corrida de 3, não casa."""
    monkeypatch.setattr(courier_machine, "_inert", lambda: False)
    monkeypatch.setattr(courier_machine, "_request", lambda *a, **k: {"link": "https://taon.example/r/unico"})
    links = courier_machine.tracking_links("184532")
    assert len(links) == 1
    assert all(courier.link_for_order(ref, REFS, links) == {} for ref in REFS)


# ── Só o que foi provado se lê ──────────────────────────────────────


def test_a_link_recorded_without_proof_is_no_link():
    """O dado gravado quando todo pedido recebia a primeira parada não vale mais."""
    old = {"id_mch": "1", "status": "E", "ride_orders": REFS,
           "tracking_url": "https://rastreio.mock/de-outro-cliente", "confirmation_code": "1234"}
    assert courier.proven_tracking(old) == {"url": "", "code": ""}
    assert courier.proven_tracking({**old, "tracking_match": "single"}) == {"url": "", "code": ""}
    assert courier.proven_tracking({**old, "tracking_match": "qualquer"}) == {"url": "", "code": ""}
    assert courier.proven_tracking({**old, "tracking_match": "id"}) == {
        "url": "https://rastreio.mock/de-outro-cliente", "code": "1234",
    }
    assert courier.proven_tracking(None) == {"url": "", "code": ""}


def test_the_link_and_the_code_are_read_through_one_door_only():
    """Quem lê ``tracking_url`` direto do bloco pula a prova: só ``courier.proven_tracking`` lê."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    # ``context.get("tracking_url")`` é o link da página do pedido no aviso, outra coisa.
    raw_read = re.compile(r"""(?<!context)\.get\(\s*["'](?:tracking_url|confirmation_code)["']""")
    offenders = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if "tests" not in path.parts and "migrations" not in path.parts
        and path.relative_to(root).as_posix() != "shop/services/courier.py"
        and raw_read.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == []


# ── Da leitura da TaOn ao cliente ───────────────────────────────────


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_three_shuffled_stops_each_customer_follows_their_own_delivery(shop, monkeypatch):
    orders, ride_id = _three_stop_ride()
    courier_mock.set_tracking_links(ride_id, [
        _entry("TRK-C", stop=3, code=3003), _entry("TRK-B", stop=1, code=1001), _entry("TRK-A", stop=2, code=2002),
    ])
    calls: list[str] = []
    real = courier_mock.tracking_links
    monkeypatch.setattr(courier_mock, "tracking_links", lambda ref: calls.append(ref) or real(ref))

    _read(ride_id, "A")
    _read(ride_id, "E")

    # Uma leitura dos links para a corrida inteira, não uma por pedido.
    assert calls == [ride_id]
    for ref, code in (("TRK-A", "2002"), ("TRK-B", "1001"), ("TRK-C", "3003")):
        order = orders[ref]
        order.refresh_from_db()
        block = courier.get_block(order)
        assert (block["tracking_url"], block["confirmation_code"], block["tracking_match"]) == (_link(ref), code, "id")
        # Página do pedido (botão "Acompanhar o entregador") e aviso de saída.
        assert _courier_tracking_url(order) == _link(ref)
        assert _suffix(order) == f"\nAcompanhe o entregador: {_link(ref)}"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_one_link_per_stop_in_the_sent_order_reaches_each_customer(shop):
    orders, ride_id = _three_stop_ride()

    _read(ride_id, "A")
    _read(ride_id, "E")

    seen = set()
    for index, ref in enumerate(REFS, start=1):
        order = orders[ref]
        order.refresh_from_db()
        assert courier.get_block(order)["tracking_match"] == "position"
        assert _courier_tracking_url(order) == f"https://rastreio.mock/pedido/{ride_id}/parada/{index}"
        seen.add(_courier_tracking_url(order))
    assert len(seen) == 3


@pytest.mark.parametrize(
    "links",
    [
        [{"parada_id": "", "link_rastreio": "https://rastreio.mock/unico", "codigo_confirmacao": 1234}],
        [_entry("TRK-B", stop=1), {"parada_id": "2", "link_rastreio": _link("x")},
         {"parada_id": "3", "link_rastreio": _link("y")}],
    ],
    ids=["formato-unico", "so-uma-parada-nomeada"],
)
@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_unproven_link_is_never_recorded_and_the_customer_sees_no_button(shop, links):
    orders, ride_id = _three_stop_ride()
    courier_mock.set_tracking_links(ride_id, links)

    _read(ride_id, "A")
    _read(ride_id, "E")

    named = {entry.get("id_externo") for entry in links}
    for ref, order in orders.items():
        order.refresh_from_db()
        block = courier.get_block(order)
        assert block["status"] == "E"
        if ref in named:
            assert _courier_tracking_url(order) == _link(ref)
            continue
        assert "tracking_url" not in block and "confirmation_code" not in block and "tracking_match" not in block
        assert _courier_tracking_url(order) == ""
        assert _suffix(order) == ""


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_link_that_arrives_late_is_matched_on_a_later_reading(shop, monkeypatch):
    """Faltou no aceite: a batida seguinte busca de novo, uma vez por corrida, e casa cada parada."""
    orders, ride_id = _three_stop_ride()
    courier_mock.set_tracking_links(ride_id, [])
    calls: list[str] = []
    real = courier_mock.tracking_links
    monkeypatch.setattr(courier_mock, "tracking_links", lambda ref: calls.append(ref) or real(ref))
    _read(ride_id, "A")
    assert all("tracking_url" not in courier.get_block(order) for order in orders.values())
    # A lista vazia também é uma leitura só: os três pedidos não batem na TaOn um a um.
    assert calls == [ride_id]

    courier_mock.set_tracking_links(ride_id, [_entry(ref, stop=index) for index, ref in enumerate(REFS, start=1)])
    # Passou a espera entre uma tentativa e outra (5 min por corrida).
    cache.delete_many([f"courier:tracking_retry:{ride_id}", f"courier:tracking_links:{ride_id}"])
    _read(ride_id, "A")

    for ref, order in orders.items():
        order.refresh_from_db()
        assert courier.proven_tracking(courier.get_block(order))["url"] == _link(ref)


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_ride_of_one_order_still_gets_its_link_and_code(shop):
    order = _at("TRK-SOLO", -23.30, -51.16)
    CourierDispatchHandler().handle(message=courier.request_dispatch(order, actor="operator:ana"), ctx={})
    order.refresh_from_db()
    ride_id = courier.get_block(order)["id_mch"]

    _read(ride_id, "A")
    _read(ride_id, "E")

    order.refresh_from_db()
    block = courier.get_block(order)
    assert (block["tracking_url"], block["confirmation_code"], block["tracking_match"]) == (
        f"https://rastreio.mock/pedido/{ride_id}", "1234", "single",
    )
    assert _courier_tracking_url(order) == f"https://rastreio.mock/pedido/{ride_id}"
    assert _suffix(order) == f"\nAcompanhe o entregador: https://rastreio.mock/pedido/{ride_id}"
