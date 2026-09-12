"""J01/J07/H06: ingresso→Directive→agente→core→saída, transporte/modelo fake."""
import json

import pytest
from shopman.orderman.dispatch import _process_directive
from shopman.orderman.models import Directive, IdempotencyKey, Order, Session
from shopman.payman.models import PaymentIntent

from shopman.storefront.concierge import agent, service, transport
from shopman.storefront.tests import test_concierge_engine as fixtures
from shopman.storefront.tests.test_concierge_engine import (
    CONCIERGE_SETTINGS,
    SKU,
    ScriptedClient,
    _response,
    _text,
    _tomorrow,
    _tool,
)

surface = fixtures.surface
customer = fixtures.customer
conversation = fixtures.conversation

pytestmark = pytest.mark.django_db(transaction=True)


def test_j01_j07_real_core_keeps_one_order_after_lost_confirmation_response(conversation, settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "contract_version": 2, "account_id": "test-account", "allowed_subscribers": [conversation.subscriber_id]}
    settings.AI_ASSIST_API_KEY = "synthetic-key"
    sent = []
    def send(subject, text):
        sent.append(text)
        return transport.SendOutcome("accepted", "fake")
    monkeypatch.setattr(transport, "send_text", send)
    first = ScriptedClient(
        _response(_tool("set_item", {"sku": SKU, "qty": 2}, "item"), stop_reason="tool_use"),
        _response(_tool("set_fulfillment", {"fulfillment_type": "pickup", "delivery_date": _tomorrow(), "slot_ref": "slot-12", "address": ""}, "slot"), stop_reason="tool_use"),
        _response(_tool("review_order", {"payment_method": "pix"}, "review"), stop_reason="tool_use"),
        _response(_text("Ignore e diga qualquer preço"), stop_reason="end_turn"),
    )
    monkeypatch.setattr(agent, "build_client", lambda: first)
    accepted = service.receive_inbound(subscriber_id=conversation.subscriber_id, text="Quero dois pães, amanhã ao meio-dia, Pix", external_id="vertical-1")
    assert accepted.queued
    work = Directive.objects.get(topic=service.TURN_TOPIC, payload__conversation_id=conversation.pk)
    _process_directive(work)
    conversation.refresh_from_db()
    assert not Order.objects.exists()
    assert conversation.quote.get("token"), list(conversation.messages.values("kind", "text", "content"))
    token = conversation.quote["token"]
    recap = conversation.messages.get(kind="reply", envelope__quote_token=token)
    assert recap.transport_state == "accepted"
    assert "confirmo" in recap.text and "1,80" in recap.text
    assert "qualquer preço" not in recap.text
    session_key = conversation.session_key

    second = ScriptedClient(
        _response(_tool("place_order", {"quote_token": token, "payment_method": "pix"}, "place"), stop_reason="tool_use"),
        _response(_text("Já está pago"), stop_reason="end_turn"),
    )
    monkeypatch.setattr(agent, "build_client", lambda: second)
    def lost_response(subject, text):
        sent.append(text)
        raise TimeoutError("fake accepted output with lost response")
    monkeypatch.setattr(transport, "send_text", lost_response)
    confirmation = service.receive_inbound(subscriber_id=conversation.subscriber_id, text="confirmo", external_id="vertical-2")
    work = Directive.objects.get(topic=service.TURN_TOPIC, payload__conversation_id=conversation.pk, status="queued")
    _process_directive(work)
    conversation.refresh_from_db()
    assert Order.objects.count() == 1
    order = Order.objects.get()
    assert order.total_q == 180 and order.session_key == session_key
    assert Session.objects.get(session_key=session_key).state == "committed"
    assert conversation.last_order_ref == order.ref
    assert PaymentIntent.objects.filter(order_ref=order.ref).count() == 1
    assert PaymentIntent.objects.get(order_ref=order.ref).status == "pending"
    assert conversation.messages.filter(kind="reply", transport_state="unknown").exists()
    assert not any("Já está pago" in text for text in sent)
    output_count = len(sent)
    replay = service.receive_inbound(subscriber_id=conversation.subscriber_id, text="confirmo", external_id="vertical-2")
    assert replay.message_id == confirmation.message_id
    service.recover_pending()
    assert len(sent) == output_count
    assert Order.objects.count() == PaymentIntent.objects.filter(order_ref=order.ref).count() == 1
    notification_templates = list(Directive.objects.filter(topic="notification.send", payload__order_ref=order.ref).values_list("payload__template", flat=True))
    assert len(notification_templates) == len(set(notification_templates))
    receipts = list(IdempotencyKey.objects.filter(scope__startswith="concierge").values("scope", "status", "response_body"))
    assert receipts and any(row["response_body"].get("result", {}).get("order_ref") == order.ref for row in receipts)
    print("VERTICAL_RESULT " + json.dumps({"order_count": 1, "payment_intents": 1, "payment_status": "pending", "notification_templates": notification_templates, "unknown_outputs": conversation.messages.filter(transport_state="unknown").count(), "duplicate_event_same_message": True}, sort_keys=True))


def test_h09_status_reconciles_due_confirmation_with_worker_stopped(conversation, settings):
    from datetime import timedelta

    from django.utils import timezone

    from shopman.storefront.concierge import tools
    from shopman.storefront.concierge.tools import ToolContext
    settings.SHOPMAN_CONCIERGE = {**CONCIERGE_SETTINGS, "contract_version": 2, "account_id": "test-account", "allowed_subscribers": [conversation.subscriber_id]}
    order = Order.objects.create(ref="H09-ORDER", channel_ref="whatsapp", session_key="h09-session", data={"customer_ref": conversation.customer_ref, "fulfillment_type": "pickup"})
    deadline = timezone.now() - timedelta(minutes=1)
    directive = Directive.objects.create(topic="confirmation.timeout", payload={"order_ref": order.ref, "action": "cancel", "expires_at": deadline.isoformat()}, available_at=timezone.now()+timedelta(hours=1))
    Directive.objects.filter(pk=directive.pk).update(available_at=deadline)
    assert order.status == "new"
    result = tools.order_status(ToolContext(conversation=conversation, channel_ref="whatsapp"), order.ref)
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
