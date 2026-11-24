"""A Nice traz a sacola do site enquanto a loja a edita, com trava de linha real (OC-18, §9.3).

A oferta inversa (``tools.bring_site_cart``) é oferta e aceite no mesmo turno, pelo
serviço de transferência. Duas conexões ao PostgreSQL disputam a sacola do site:

- a edição da loja trava primeiro: o aceite da Nice espera, lê a revisão nova e recusa
  com ``source_changed`` (X5); a sacola do site fica inteira e a conversa sem sacola;
- o aceite da Nice trava primeiro: a edição da loja espera e encontra a sacola já levada
  (``already_abandoned``).

Em nenhuma ordem sobram duas sacolas vivas ou reserva em dobro. O caminho de ida (a
conversa para o site) está em ``test_concierge_commercial_races.py`` e o serviço puro em
``shop/tests/test_session_transfer_postgres.py``.
"""
# ruff: noqa: F401, F811

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event

import pytest
from django.db import connection, transaction
from shopman.orderman.models import Session

from shopman.shop.services import cart, sessions
from shopman.storefront.concierge import tools
from shopman.storefront.tests.test_concierge_commercial_races import (
    Worker,
    assert_database_wait,
    isolated_callbacks,
    own_reserved,
    total_reserved,
)
from shopman.storefront.tests.test_concierge_engine import (
    CHANNEL,
    CONCIERGE_SETTINGS,
    SKU,
    conversation,
    ctx,
    customer,
    surface,
)

requires_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="Requires independent PostgreSQL connections"
)

pytestmark = [pytest.mark.django_db(transaction=True), requires_postgres]

WEB = "web"


def _site_cart(ctx, settings) -> Session:
    """A sacola de 2 pães da cliente no site, e a ponte ligada (override, nunca ambiente vivo)."""
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "transfer_enabled": True}
    _, key = cart.add_item(session_key=None, channel_ref=WEB, origin_channel=WEB, sku=SKU, qty=2, unit_price_q=90,
                           name="Pão Francês")
    sessions.modify_session(session_key=key, channel_ref=WEB, ops=[
        {"op": "set_data", "path": "customer", "value": {"ref": ctx.conversation.customer_ref, "name": "Ana"}},
    ])
    return Session.objects.get(session_key=key, channel_ref=WEB)


def test_x5_the_store_edit_that_holds_the_site_cart_first_makes_the_nice_offer_source_changed(ctx, settings):
    site = _site_cart(ctx, settings)
    editing, release = Event(), Event()

    def edit():
        with transaction.atomic():
            Session.objects.select_for_update().get(pk=site.pk)
            cart.add_item(session_key=site.session_key, channel_ref=WEB, origin_channel=WEB, sku=SKU, qty=1,
                          unit_price_q=90, name="Pão Francês")
            editing.set()
            assert release.wait(10)
        return "edited"

    editor = Worker(edit)
    bringer = Worker(lambda: tools.bring_site_cart(ctx))
    with ThreadPoolExecutor(max_workers=2) as pool:
        edited = pool.submit(editor)
        try:
            assert editing.wait(10)
            brought = pool.submit(bringer)
            assert_database_wait(bringer)
        finally:
            release.set()
        assert edited.result(20) == "edited"
        refusal = brought.result(20)

    assert refusal["ok"] is False and refusal["error"] == "source_changed", refusal
    site.refresh_from_db()
    assert site.state == "open" and Decimal(site.items[0]["qty"]) == Decimal(3)
    assert "transferred_to" not in site.data
    assert not Session.objects.filter(channel_ref=CHANNEL, state="open").exists()
    assert own_reserved(site.session_key) == total_reserved() == Decimal(3)


def test_the_nice_accept_that_holds_first_wins_and_the_late_store_edit_finds_it_gone(ctx, settings, monkeypatch):
    site = _site_cart(ctx, settings)
    boundary, release = Event(), Event()
    original_add = cart.add_item

    def paused_add(**kwargs):
        if kwargs.get("channel_ref") == CHANNEL and not boundary.is_set():
            boundary.set()  # sacola do site travada e abandonada, reservas devolvidas, ainda na transação
            assert release.wait(10)
        return original_add(**kwargs)

    monkeypatch.setattr(cart, "add_item", paused_add)
    bringer = Worker(lambda: tools.bring_site_cart(ctx))
    editor = Worker(lambda: original_add(session_key=site.session_key, channel_ref=WEB, origin_channel=WEB, sku=SKU,
                                         qty=1, unit_price_q=90, name="Pão Francês"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        brought = pool.submit(bringer)
        try:
            assert boundary.wait(10)
            edited = pool.submit(editor)
            assert_database_wait(editor)
        finally:
            release.set()
        result, refusal = brought.result(20), edited.result(20)

    assert result["ok"], result
    assert refusal["code"] == "already_abandoned", refusal
    site.refresh_from_db()
    ctx.conversation.refresh_from_db()
    here = Session.objects.get(session_key=ctx.conversation.session_key, channel_ref=CHANNEL)
    assert site.state == "abandoned" and here.state == "open"
    assert Decimal(here.items[0]["qty"]) == Decimal(2)
    assert own_reserved(site.session_key) == Decimal(0)
    assert own_reserved(here.session_key) == total_reserved() == Decimal(2)
