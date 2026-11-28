# ruff: noqa: F401, F811
"""A sacola aberta em outro canal (OC-17, cenário C06 do Relatório II).

A cliente tem sacola aberta num canal (o site, o WhatsApp) e abre o outro. O outro
canal AVISA que ela existe, com a ação de trazer, e nunca sincroniza: a sacola de
origem fica intacta (itens, revisão, reservas). A outra sacola é achada pelo
``customer_ref`` que ela carrega, nunca pelo telefone (X7), e a leitura não grava.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from shopman.orderman.models import Session

from shopman.shop.projections.cart import items_phrase
from shopman.shop.services import cart as cart_service
from shopman.shop.services import sessions
from shopman.storefront.concierge import tools
from shopman.storefront.identity import IDENTITY_NUMBER, IDENTITY_SESSION_KEY
from shopman.storefront.tests.identity_fakes import make_identity_view
from shopman.storefront.tests.test_concierge_engine import (
    CHANNEL,
    SKU,
    conversation,
    ctx,
    customer,
    surface,
)

pytestmark = pytest.mark.django_db

WEB = "web"


def _web_cart(customer, qty: int = 2) -> Session:
    """A sacola do site da cliente, com o dono gravado como a loja grava."""
    _session, key = cart_service.add_item(
        session_key=None, channel_ref=WEB, origin_channel=WEB, sku=SKU, qty=qty, unit_price_q=90,
    )
    sessions.assign_customer(session_key=key, channel_ref=WEB, customer_uuid=customer.uuid)
    return Session.objects.get(session_key=key, channel_ref=WEB)


def _frozen(session: Session) -> tuple:
    """O que prova que a sacola não foi tocada: estado, revisão, linhas e reservas."""
    from shopman.stockman import Hold

    session = Session.objects.get(pk=session.pk)
    holds = sorted(
        Hold.objects.filter(metadata__reference=session.session_key).values_list("pk", "status", "quantity")
    )
    lines = [(item["sku"], str(item["qty"]), item.get("line_total_q")) for item in session.items]
    return session.state, session.rev, session.updated_at, lines, holds, dict(session.data or {})


def _other_customer():
    from shopman.guestman.models import Customer
    from shopman.guestman.services import customer as customer_service

    return customer_service.create(
        ref=Customer.generate_ref(), first_name="Bia", phone="+5543999990000", source_system="test"
    )


# ── A leitura ────────────────────────────────────────────────────────


def test_finds_the_open_cart_of_the_same_customer_in_another_channel(surface, customer):
    web = _web_cart(customer, qty=2)

    found = sessions.open_sessions_for_customer(customer.ref, exclude_channel=CHANNEL)

    assert [(e.channel_ref, e.channel_name, e.session_key) for e in found] == [(WEB, "Loja online", web.session_key)]
    assert found[0].items_count == 2
    assert found[0].lines_count == 1
    assert found[0].subtotal_q == 180
    assert found[0].revision == web.rev


def test_the_asking_channel_empty_and_closed_carts_never_appear(surface, customer):
    web = _web_cart(customer)
    assert sessions.open_sessions_for_customer(customer.ref, exclude_channel=WEB) == ()

    sessions.modify_session(
        session_key=web.session_key, channel_ref=WEB, ops=[{"op": "remove_line", "line_id": web.items[0]["line_id"]}],
    )
    assert sessions.open_sessions_for_customer(customer.ref, exclude_channel=CHANNEL) == ()

    again = _web_cart(customer)
    sessions.abandon_session(session_key=again.session_key, channel_ref=WEB)
    assert sessions.open_sessions_for_customer(customer.ref, exclude_channel=CHANNEL) == ()
    assert sessions.open_sessions_for_customer("", exclude_channel=CHANNEL) == ()


def test_another_customer_never_appears_not_even_by_the_same_phone(surface, customer):
    """X7: o dono é o ``customer_ref`` da sacola. Telefone igual não abre a sacola alheia."""
    other = _other_customer()
    _web_cart(other)
    _session, key = cart_service.add_item(
        session_key=None, channel_ref=WEB, origin_channel=WEB, sku=SKU, qty=1, unit_price_q=90,
    )
    Session.objects.filter(session_key=key).update(handle_type="phone", handle_ref=customer.phone)

    assert sessions.open_sessions_for_customer(customer.ref, exclude_channel=CHANNEL) == ()
    assert [e.channel_ref for e in sessions.open_sessions_for_customer(other.ref, exclude_channel=CHANNEL)] == [WEB]


def test_reading_never_writes(surface, customer):
    web = _web_cart(customer)
    before = _frozen(web)

    with CaptureQueriesContext(connection) as queries:
        sessions.open_sessions_for_customer(customer.ref, exclude_channel=CHANNEL)

    writes = [q["sql"] for q in queries if q["sql"].lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}]
    assert writes == []
    assert not any("FOR UPDATE" in q["sql"].upper() for q in queries)
    assert _frozen(web) == before


def test_items_phrase_counts_units_and_products_for_weight():
    assert items_phrase(SimpleNamespace(items_count=1, lines_count=1)) == "1 item"
    assert items_phrase(SimpleNamespace(items_count=3, lines_count=2)) == "3 itens"
    assert items_phrase(SimpleNamespace(items_count=Decimal("1.5"), lines_count=1)) == "1 produto"
    assert items_phrase(SimpleNamespace(items_count=Decimal("2.5"), lines_count=2)) == "2 produtos"


# ── A Nice avisa e não sincroniza ────────────────────────────────────

LINE = "No site, você tem outra sacola aberta, com 2 itens (R$ 1,80)."


def test_c06_nice_says_the_site_cart_exists_and_leaves_it_alone(ctx, customer):
    web = _web_cart(customer, qty=2)
    before = _frozen(web)

    cart = tools.view_cart(ctx)

    assert cart["ok"] and cart["lines"] == []
    assert cart["open_elsewhere"] == [
        {"channel": WEB, "where": "no site", "items": "2 itens", "subtotal": "R$ 1,80"}
    ]
    text = tools.render_result("view_cart", cart)
    assert text.splitlines()[-1] == LINE
    assert "—" not in text
    assert _frozen(web) == before
    ctx.conversation.refresh_from_db()
    assert ctx.conversation.session_key == ""


def test_c06_nice_review_keeps_the_quote_to_this_cart_and_never_merges(ctx, customer):
    web = _web_cart(customer, qty=2)
    tools.set_item(ctx, SKU, 3)
    before = _frozen(web)

    review = tools.review_order(ctx)

    assert review["ok"] and [line["qty"] for line in review["lines"]] == [3]
    assert review["open_elsewhere"][0]["where"] == "no site"
    assert LINE in tools.render_result("review_order", review).splitlines()
    ctx.conversation.refresh_from_db()
    own = Session.objects.get(session_key=ctx.conversation.session_key, channel_ref=CHANNEL)
    assert [(item["sku"], int(item["qty"])) for item in own.items] == [(SKU, 3)]
    assert _frozen(web) == before


def test_nice_with_an_empty_review_still_says_where_the_other_cart_is(ctx, customer):
    _web_cart(customer, qty=2)

    review = tools.review_order(ctx)

    assert review["missing"] == ["items"]
    assert tools.render_result("review_order", review).splitlines() == ["A sacola está vazia.", LINE]


def test_nice_without_other_cart_or_with_another_customers_cart_says_nothing(ctx, customer):
    _web_cart(_other_customer(), qty=2)

    cart = tools.view_cart(ctx)

    assert "open_elsewhere" not in cart
    assert "outra sacola" not in tools.render_result("view_cart", cart)


# ── A loja avisa e não sincroniza ────────────────────────────────────


def _store_request(customer=None, *, strength: str = ""):
    request = RequestFactory().get("/api/v1/storefront/cart/")
    request.session = SessionStore()
    if strength:
        request.session[IDENTITY_SESSION_KEY] = strength
    request.session.save()
    request.customer = (
        make_identity_view(subject_id=customer.uuid, name=customer.name, phone=customer.phone) if customer else None
    )
    return request


def test_c06_store_cart_shows_the_whatsapp_cart_with_the_bring_action_off(ctx, customer):
    from shopman.storefront.presentation.cart import build_cart

    tools.set_item(ctx, SKU, 3)
    ctx.conversation.refresh_from_db()
    whatsapp = Session.objects.get(session_key=ctx.conversation.session_key, channel_ref=CHANNEL)
    before = _frozen(whatsapp)

    cart = build_cart(request=_store_request(customer), channel_ref=WEB)

    assert len(cart.open_elsewhere) == 1
    entry = cart.open_elsewhere[0]
    assert (entry.channel, entry.channel_label, entry.items_count, entry.items_phrase) == (
        CHANNEL, "WhatsApp", 3, "3 itens",
    )
    assert (entry.subtotal_q, entry.subtotal_display) == (270, "R$ 2,70")
    # A ação de trazer existe e nasce desligada: quem liga é a passagem entre canais (X1).
    assert (entry.bring.ref, entry.bring.enabled) == ("bring_cart", False)
    assert whatsapp.session_key not in repr(cart)
    assert _frozen(whatsapp) == before


def test_store_says_nothing_to_a_visitor_or_a_forwarded_link(ctx, customer):
    from shopman.storefront.presentation.cart import build_cart

    tools.set_item(ctx, SKU, 3)

    assert build_cart(request=_store_request(), channel_ref=WEB).open_elsewhere == ()
    forwarded = _store_request(customer, strength=IDENTITY_NUMBER)
    assert build_cart(request=forwarded, channel_ref=WEB).open_elsewhere == ()


def test_store_never_shows_another_customers_cart(ctx, customer):
    from shopman.storefront.presentation.cart import build_cart

    tools.set_item(ctx, SKU, 3)  # a sacola do WhatsApp é da Ana

    assert build_cart(request=_store_request(_other_customer()), channel_ref=WEB).open_elsewhere == ()


def test_store_cart_payload_carries_the_field(ctx, customer):
    from shopman.storefront.api.projections import projection_data
    from shopman.storefront.presentation.cart import build_cart

    tools.set_item(ctx, SKU, 3)

    payload = projection_data(build_cart(request=_store_request(customer), channel_ref=WEB))

    assert payload["open_elsewhere"][0]["channel"] == CHANNEL
    assert set(payload["open_elsewhere"][0]) == {
        "channel", "channel_label", "items_count", "items_phrase", "subtotal_q", "subtotal_display", "bring",
    }
