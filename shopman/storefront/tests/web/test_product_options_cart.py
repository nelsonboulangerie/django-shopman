"""Escolhas no produto na sacola da loja (Fase 1, dono 02/10/2026).

O Croque com ovo e o Croque sem ovo são duas linhas; o Croque com ovo duas
vezes é uma linha de 2. O Frappé não entra sem sabor. O preço é o do produto
mais as opções, relidas do catálogo. A observação vai pela linha e não vaza
para a outra linha do mesmo SKU. A venda com opção não mexe no estoque do
insumo que a opção declara gastar.
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
from shopman.offerman.models import Product
from shopman.orderman.models import Session
from shopman.stockman import stock
from shopman.stockman.models import Move, Position, PositionKind

from shopman.storefront.tests.web.conftest import _ensure_listing_item

pytestmark = pytest.mark.django_db

CROQUE_GROUPS = [
    {
        "ref": "adicionais", "label": "Adicionais", "min": 0, "max": 2,
        "options": [
            {"ref": "ovo-frito", "label": "Ovo frito", "price_q": 400, "available": True,
             "consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}]},
            {"ref": "salada", "label": "Salada", "price_q": 300, "available": True, "consumes": []},
            {"ref": "bacon", "label": "Bacon", "price_q": 500, "available": False, "consumes": []},
        ],
    },
]
FRAPPE_GROUPS = [
    {
        "ref": "sabor", "label": "Sabor", "min": 1, "max": 1,
        "options": [
            {"ref": "cafe", "label": "Café", "price_q": 0, "available": True, "consumes": []},
            {"ref": "chocolate", "label": "Chocolate", "price_q": 0, "available": True, "consumes": []},
        ],
    },
]


def _stocked(channel, sku, name, price_q, groups):
    product = Product.objects.create(
        sku=sku, name=name, base_price_q=price_q, is_published=True, is_sellable=True,
        metadata={"option_groups": groups},
    )
    _ensure_listing_item(channel, product, price_q=price_q)
    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(quantity=Decimal("20"), sku=sku, position=position, target_date=None, reason="teste")
    return product


@pytest.fixture
def croque(channel):
    return _stocked(channel, "CQMO", "Croque Monsieur", 2400, CROQUE_GROUPS)


@pytest.fixture
def frappe(channel):
    return _stocked(channel, "FRAP", "Frappé", 1800, FRAPPE_GROUPS)


def _add(client, sku, options, qty=1):
    return client.post(
        "/api/v1/cart/lines/",
        data=json.dumps({"sku": sku, "qty": qty, "options": options}),
        content_type="application/json",
    )


def _lines(client) -> list[dict]:
    return Session.objects.get(session_key=client.session["cart_session_key"]).items


EGG = [{"group": "adicionais", "ref": "ovo-frito"}]


def test_with_and_without_egg_are_two_lines_and_egg_twice_is_one_line_of_two(client, croque):
    assert _add(client, "CQMO", EGG).status_code == 200
    assert _add(client, "CQMO", []).status_code == 200
    resp = _add(client, "CQMO", EGG)
    assert resp.status_code == 200, resp.content[:400]

    lines = sorted(_lines(client), key=lambda line: line["name"])
    assert [(line["name"], int(Decimal(str(line["qty"])))) for line in lines] == [
        ("Croque Monsieur", 1),
        ("Croque Monsieur (+ Ovo frito)", 2),
    ]
    with_egg = lines[1]
    # Preço = produto + opção, relido do catálogo; o cliente nunca mandou preço.
    assert with_egg["unit_price_q"] == 2800
    assert with_egg["line_total_q"] == 5600
    assert with_egg["meta"]["_list_q"] == 2800
    option = with_egg["meta"]["options"][0]
    assert option == {
        "group": "adicionais", "group_label": "Adicionais", "ref": "ovo-frito", "name": "Ovo frito",
        "qty": 1, "unit_price_q": 400, "consumes": [{"sku": "OVOS", "qty": "50", "unit": "g"}],
    }
    cart = resp.json()["cart"]
    projected = next(item for item in cart["items"] if item["line_id"] == with_egg["line_id"])
    assert projected["options_summary"] == "+ Ovo frito"
    assert projected["has_options"] is True


def test_frappe_without_flavor_is_refused_by_both_doors(client, frappe):
    resp = _add(client, "FRAP", [])
    assert resp.status_code == 400
    body = resp.json()
    assert body["error_code"] == "option_required"
    assert body["field"] == "options"
    assert "Sabor" in body["detail"]

    by_sku = client.put("/api/v1/cart/skus/FRAP/", data=json.dumps({"qty": 1}), content_type="application/json")
    assert by_sku.status_code == 400
    assert by_sku.json()["error_code"] == "option_required"

    ok = _add(client, "FRAP", [{"group": "sabor", "ref": "chocolate"}])
    assert ok.status_code == 200
    assert _lines(client)[0]["name"] == "Frappé (Chocolate)"
    assert _lines(client)[0]["unit_price_q"] == 1800


def test_unknown_unavailable_and_over_the_max_are_refused(client, croque):
    assert _add(client, "CQMO", [{"group": "adicionais", "ref": "trufa"}]).json()["error_code"] == "option_unknown"
    assert _add(client, "CQMO", [{"group": "adicionais", "ref": "bacon"}]).json()["error_code"] == "option_unavailable"
    twice = [{"group": "adicionais", "ref": "ovo-frito"}, {"group": "adicionais", "ref": "ovo-frito"}]
    assert _add(client, "CQMO", twice).json()["error_code"] == "option_unknown"
    assert "cart_session_key" not in client.session or not _lines(client)


def test_note_by_line_does_not_leak_to_the_other_line_of_the_same_sku(client, croque):
    _add(client, "CQMO", EGG)
    _add(client, "CQMO", [])
    with_egg = next(line for line in _lines(client) if line["meta"].get("options"))

    resp = client.put(
        f"/api/v1/cart/lines/{with_egg['line_id']}/notes/",
        data=json.dumps({"notes": "gema mole"}),
        content_type="application/json",
    )

    assert resp.status_code == 200
    notes = {line["line_id"]: line["meta"].get("notes") for line in _lines(client)}
    assert notes[with_egg["line_id"]] == "gema mole"
    assert [note for line_id, note in notes.items() if line_id != with_egg["line_id"]] == [None]


def test_line_qty_changes_one_line_and_keeps_the_other_lines_reservation(client, croque):
    from shopman.shop.services import availability

    _add(client, "CQMO", EGG)
    _add(client, "CQMO", [])
    key = client.session["cart_session_key"]
    with_egg = next(line for line in _lines(client) if line["meta"].get("options"))
    plain = next(line for line in _lines(client) if not line["meta"].get("options"))

    resp = client.put(
        f"/api/v1/cart/lines/{with_egg['line_id']}/", data=json.dumps({"qty": 3}), content_type="application/json",
    )
    assert resp.status_code == 200, resp.content[:400]
    assert resp.json()["line"]["line_id"] == with_egg["line_id"]
    assert availability.session_line_held_qty(key, "CQMO") == Decimal("4")

    resp = client.put(
        f"/api/v1/cart/lines/{with_egg['line_id']}/", data=json.dumps({"qty": 0}), content_type="application/json",
    )
    assert resp.status_code == 200
    assert [line["line_id"] for line in _lines(client)] == [plain["line_id"]]
    # A reserva da linha que ficou continua lá.
    assert availability.session_line_held_qty(key, "CQMO") == Decimal("1")


def test_option_price_is_reread_from_the_current_catalog(client, croque):
    _add(client, "CQMO", EGG)
    groups = json.loads(json.dumps(CROQUE_GROUPS))
    groups[0]["options"][0]["price_q"] = 500
    croque.metadata = {"option_groups": groups}
    croque.save(update_fields=["metadata"])

    _add(client, "CQMO", [])  # qualquer mutação reprecifica a sacola

    with_egg = next(line for line in _lines(client) if line["meta"].get("options"))
    assert with_egg["unit_price_q"] == 2900


def test_selling_with_an_option_does_not_move_the_ingredient_stock(client, croque):
    before = Move.objects.filter(quant__sku="OVOS").count()

    _add(client, "CQMO", EGG, qty=2)

    assert Move.objects.filter(quant__sku="OVOS").count() == before == 0


def test_reorder_revalidates_the_options_against_todays_catalog(client, croque, channel):
    from types import SimpleNamespace

    from shopman.orderman.models import Order, OrderItem

    from shopman.shop.services import customer_orders
    from shopman.storefront.cart import CartService

    order = Order.objects.create(ref="REP-1", channel_ref="web", status="completed", total_q=2800)
    OrderItem.objects.create(
        order=order, line_id="L-1", sku="CQMO", name="Croque Monsieur (+ Ovo frito)", qty=1,
        unit_price_q=2800, line_total_q=2800,
        meta={"options": [{"group": "adicionais", "ref": "ovo-frito", "name": "Ovo frito", "unit_price_q": 400}]},
    )
    request = SimpleNamespace(session=client.session, user=SimpleNamespace(is_authenticated=False))

    skipped = customer_orders.add_reorder_items(request, order, cart_service=CartService, channel_ref="web")
    assert skipped == []
    session = Session.objects.get(session_key=request.session["cart_session_key"])
    assert session.items[0]["name"] == "Croque Monsieur (+ Ovo frito)"
    assert session.items[0]["meta"]["options"][0]["ref"] == "ovo-frito"

    # A opção saiu do cardápio: a recompra não inventa, devolve como "não deu".
    groups = json.loads(json.dumps(CROQUE_GROUPS))
    groups[0]["options"][0]["available"] = False
    croque.metadata = {"option_groups": groups}
    croque.save(update_fields=["metadata"])
    assert customer_orders.add_reorder_items(request, order, cart_service=CartService, channel_ref="web") == [
        "Croque Monsieur"
    ]
