"""Observação por item da loja chega ao ticket da cozinha.

O PDV já mandava observação por linha (``meta["notes"]``) ao KDS; a loja só
aceitava a observação do pedido inteiro (``order_notes``). O caminho até o KDS
existia (``kds._order_to_lines`` lê ``meta["notes"]``); faltava o primeiro elo:
a sacola da loja gravar a nota na linha.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from shopman.orderman.models import Order, Session

from shopman.backstage.models import KDSInstance, KDSTicket
from shopman.shop.services import kds
from shopman.storefront.tests._checkout_auth import authenticate_checkout
from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

SKU = "PAO-FRANCES"


@pytest.fixture(autouse=True)
def _clear_rate_limit_cache():
    # O checkout conta tentativas no cache compartilhado; sem limpar, o próximo
    # teste do mesmo worker herda o contador e recebe 429.
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def _add(client) -> dict:
    resp = client.put(f"/api/v1/cart/skus/{SKU}/", data={"qty": 2}, content_type="application/json")
    assert resp.status_code == 200, resp.content
    return resp.json()["cart"]["items"][0]


def _set_notes(client, line_id: str, notes: str):
    return client.put(
        f"/api/v1/cart/lines/{line_id}/notes/",
        data={"notes": notes},
        content_type="application/json",
    )


def test_line_note_is_saved_in_meta_notes_and_shown_in_cart(client):
    _seed_surface()
    line = _add(client)
    assert line["notes"] == ""

    resp = _set_notes(client, line["line_id"], "  sem   cebola  ")

    assert resp.status_code == 200, resp.content
    cart_line = resp.json()["cart"]["items"][0]
    assert cart_line["line_id"] == line["line_id"]
    assert cart_line["notes"] == "sem cebola"
    session = Session.objects.get(session_key=client.session["cart_session_key"])
    assert session.items[0]["meta"]["notes"] == "sem cebola"
    assert "notes" not in session.items[0]


def test_empty_note_clears_it(client):
    _seed_surface()
    line = _add(client)
    _set_notes(client, line["line_id"], "sem cebola")

    resp = _set_notes(client, line["line_id"], "")

    assert resp.status_code == 200, resp.content
    assert resp.json()["cart"]["items"][0]["notes"] == ""
    session = Session.objects.get(session_key=client.session["cart_session_key"])
    assert "notes" not in session.items[0]["meta"]


def test_qty_change_keeps_the_note(client):
    _seed_surface()
    line = _add(client)
    _set_notes(client, line["line_id"], "bem passado")

    resp = client.put(f"/api/v1/cart/skus/{SKU}/", data={"qty": 3}, content_type="application/json")

    assert resp.status_code == 200, resp.content
    assert resp.json()["cart"]["items"][0]["notes"] == "bem passado"


def test_note_over_the_limit_is_refused(client):
    _seed_surface()
    line = _add(client)

    resp = _set_notes(client, line["line_id"], "x" * 281)

    assert resp.status_code == 400, resp.content


def test_unknown_line_is_404(client):
    _seed_surface()
    _add(client)

    resp = _set_notes(client, "L-nao-existe", "sem cebola")

    assert resp.status_code == 404, resp.content


def test_without_cart_is_404(client):
    _seed_surface()

    resp = _set_notes(client, "L-1", "sem cebola")

    assert resp.status_code == 404, resp.content


def test_storefront_line_note_reaches_the_kds_ticket(client, django_capture_on_commit_callbacks):
    from shopman.storefront.services.pickup_slots import get_slots

    _seed_surface()
    KDSInstance.objects.create(ref="notes-encomendas", name="Encomendas", type="picking")
    authenticate_checkout(client)
    line = _add(client)
    assert _set_notes(client, line["line_id"], "sem cebola").status_code == 200

    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post(
            "/api/v1/checkout/",
            data=with_baseline(client, {
                "name": "Ana",
                "phone": "+5543999990001",
                "fulfillment_type": "pickup",
                "delivery_date": timezone.localdate().isoformat(),
                "delivery_time_slot": get_slots()[-1]["ref"],
                "payment_method": "cash",
            }),
            content_type="application/json",
        )
    assert resp.status_code == 201, resp.content
    order = Order.objects.get(ref=resp.json()["order_ref"])
    assert order.items.get(sku=SKU).meta["notes"] == "sem cebola"

    # O lifecycle pode já ter disparado; dispatch é idempotente por line_id.
    kds.dispatch(order)

    ticket = KDSTicket.objects.get(session_key=order.session_key)
    assert [(item["sku"], item["notes"]) for item in ticket.items] == [(SKU, "sem cebola")]
