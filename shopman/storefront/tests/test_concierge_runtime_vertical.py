"""J01/J07/H06: executor→core sem rede; o pedido e a cobrança não se repetem."""

import pytest
from shopman.orderman.models import Directive, IdempotencyKey, Order, Session
from shopman.payman.models import PaymentIntent

from shopman.storefront.tests import test_concierge_engine as fixtures
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    SKU,
    _create_inbound,
    _reclaim,
)

surface = fixtures.surface
customer = fixtures.customer
conversation = fixtures.conversation

pytestmark = pytest.mark.django_db(transaction=True)


def test_j01_j07_real_core_keeps_one_order_when_the_confirmation_is_replayed(conversation, settings, django_capture_on_commit_callbacks):
    """O pedido pelo executor (``tools.execute``), como o pedido na conversa (WP-11 a WP-13) vai chamá-lo.

    A confirmação repetida (resposta perdida, o cliente manda "confirmo" de novo) não cria
    outro pedido nem outra cobrança: a chave de idempotência devolve o mesmo pedido.
    """
    from shopman.storefront.concierge import tools
    from shopman.storefront.concierge.tools import ToolContext

    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    ctx = ToolContext(conversation=conversation, channel_ref="whatsapp")
    _create_inbound(conversation, "quero dois pães, amanhã ao meio-dia, Pix", "vertical-1")
    _reclaim(ctx)
    review = fixtures._pickup_ready(ctx)
    assert review["ok"] and review["quote_token"], review
    fixtures._accept_review(ctx, review)
    session_key = ctx.conversation.session_key
    arguments = {"quote_token": review["quote_token"], "payment_method": "pix"}

    with django_capture_on_commit_callbacks(execute=True):
        first = tools.execute("place_order", arguments, ctx)
        replay = tools.execute("place_order", arguments, ctx)

    assert first["ok"] and replay["ok"], (first, replay)
    assert replay["order_ref"] == first["order_ref"]
    assert Order.objects.count() == 1
    order = Order.objects.get()
    assert order.total_q == 180 and order.session_key == session_key
    assert Session.objects.get(session_key=session_key).state == "committed"
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1
    assert PaymentIntent.objects.get(order_ref=order.ref).status == "pending"
    receipts = list(IdempotencyKey.objects.filter(scope__startswith="concierge").values("scope", "status", "response_body"))
    assert receipts and any(row["response_body"].get("order_ref") == order.ref for row in receipts)


def test_h09_status_reconciles_due_confirmation_with_worker_stopped(conversation, settings):
    from datetime import timedelta

    from django.utils import timezone

    from shopman.storefront.concierge import tools
    from shopman.storefront.concierge.tools import ToolContext
    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    order = Order.objects.create(ref="H09-ORDER", channel_ref="whatsapp", session_key="h09-session", data={"customer_ref": conversation.customer_ref, "fulfillment_type": "pickup"})
    deadline = timezone.now() - timedelta(minutes=1)
    directive = Directive.objects.create(topic="confirmation.timeout", payload={"order_ref": order.ref, "action": "cancel", "expires_at": deadline.isoformat()}, available_at=timezone.now()+timedelta(hours=1))
    Directive.objects.filter(pk=directive.pk).update(available_at=deadline)
    assert order.status == "new"
    context = ToolContext(conversation=conversation, channel_ref="whatsapp")
    _create_inbound(conversation, "acompanhar pedido", "h09-status")
    _reclaim(context)
    result = tools.order_status(context, order.ref)
    order.refresh_from_db()
    directive.refresh_from_db()
    assert order.status == "cancelled"
    assert directive.status == "done"
    assert result["ok"] and len(result["orders"]) == 1
    assert result["orders"][0]["order_ref"] == order.ref
    assert result["orders"][0]["status"] == "cancelled"


def test_d12_second_item_failure_preserves_source_fulfillment_and_all_holds(conversation, settings, monkeypatch):
    from decimal import Decimal

    from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product
    from shopman.stockman.models import Hold

    from shopman.shop.services import cart
    from shopman.storefront.concierge import tools
    from shopman.storefront.concierge.tools import ToolContext
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "transfer_enabled": True}
    context = ToolContext(conversation=conversation, channel_ref="whatsapp")
    _create_inbound(conversation, "finalizar no site", "d12-transfer")
    _reclaim(context)
    conversation = context.conversation
    fixtures._pickup_ready(context)
    second = Product.objects.create(sku="SYNTHETIC-SECOND", name="Segundo produto sintético", base_price_q=100, is_published=True, is_sellable=True)
    CollectionItem.objects.create(collection=Collection.objects.first(), product=second)
    for listing in Listing.objects.all():
        ListingItem.objects.create(listing=listing, product=second, price_q=100, is_published=True, is_sellable=True)
    fixtures._seed_stock(second.sku, Decimal("10"))
    assert tools.set_item(context, second.sku, 2)["ok"]
    source = Session.objects.get(session_key=conversation.session_key)
    before_items, before_data = source.items, source.data
    before_holds = list(Hold.objects.order_by("pk").values("pk", "sku", "quantity", "status", "quant_id"))
    attempted = []
    original = cart.add_item
    def add(**kwargs):
        attempted.append(kwargs["sku"])
        if kwargs["sku"] == second.sku:
            raise RuntimeError("synthetic second transfer item failure")
        return original(**kwargs)
    monkeypatch.setattr(cart, "add_item", add)
    result = tools.send_web_link(context, "checkout")
    source.refresh_from_db()
    conversation.refresh_from_db()
    assert attempted == [SKU, second.sku]
    assert result["error"] == "access_unavailable"
    assert source.state == "open" and conversation.session_key == source.session_key
    assert source.items == before_items and source.data == before_data
    assert source.data["delivery_time_slot"] == "slot-12"
    assert list(Hold.objects.order_by("pk").values("pk", "sku", "quantity", "status", "quant_id")) == before_holds
    assert not Session.objects.filter(channel_ref="web").exists()
    assert not IdempotencyKey.objects.filter(scope=f"concierge.transfer:{conversation.pk}").exists()
    assert not Order.objects.exists()


def test_wp13_the_conversation_closes_the_order_and_the_pix_goes_once(conversation, settings, monkeypatch):
    """WP-13 de ponta a ponta, com commit de verdade: o Pix nasce no commit e sai uma vez, à parte."""
    from shopman.storefront.tests import test_concierge_fechar_pedido as closing
    from shopman.storefront.tests.test_concierge_engine import _listed

    settings.SHOPMAN_CONCIERGE = CONCIERGE_SETTINGS
    monkeypatch.setattr("shopman.storefront.concierge.intents._model", lambda: "modelo-de-teste")
    monkeypatch.setattr(
        "shopman.storefront.concierge.transport.send_for",
        lambda binding, text: fixtures.SendOutcome("accepted", "accepted", f"test:{binding.subject}:{text[:8]}"),
    )
    _listed("CROISSANT", "Croissant", description="Folhado amanteigado", stock="50")
    summary = closing._pickup_until_summary(conversation)

    placed = closing._turn(conversation, f"confirmo {closing._code(summary)}")
    again = closing._turn(conversation, f"confirmo {closing._code(summary)}")

    order = Order.objects.get()
    pix = order.data["payment"]["copy_paste"]
    assert placed[0].startswith(f"Pedido {order.ref} registrado."), placed
    assert placed[1:] == [pix], "o código Pix numa mensagem só dele"
    assert pix not in again, "o Pix sai uma vez"
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1
