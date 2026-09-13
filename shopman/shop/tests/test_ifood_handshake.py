"""Hermetic dispute receipts and explicit decisions; never mutate order lifecycle."""
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
import requests
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import IFOOD_HANDSHAKE_RESPONSE
from shopman.shop.services import ifood_events
from shopman.shop.services import ifood_handshake as hs

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def config():
    with override_settings(SHOPMAN_IFOOD={"merchant_id": "test-store"}):
        yield


@pytest.fixture
def order():
    return Order.objects.create(ref="HS-ORDER", external_ref="external-order", channel_ref="ifood", status="completed")


def event(code="HSD", event_id="evt-dispute"):
    metadata = {
        "id": "dispute-1", "action": "CANCELLATION", "handshakeType": "AFTER_DELIVERY",
        "message": "Item incorreto", "expiresAt": (timezone.now() + timedelta(minutes=10)).isoformat(),
        "timeoutAction": "ACCEPT_CANCELLATION", "acceptCancellationReasons": ["CUSTOMER_SATISFACTION"],
    } if code == "HSD" else {"id": "settlement-1", "disputeId": "dispute-1", "status": "ACCEPTED"}
    return {"id": event_id, "code": code, "orderId": "external-order", "merchantId": "test-store", "metadata": metadata}


def ingest(evt):
    with patch.object(ifood_events, "acknowledge", return_value=True):
        return ifood_events.process_events([evt])


def queued(order):
    ingest(event())
    hs.enqueue_response(order, dispute_id="dispute-1", decision="accept", reason="CUSTOMER_SATISFACTION", actor="operator:1")
    return Directive.objects.get(topic=IFOOD_HANDSHAKE_RESPONSE).payload


def record(order):
    order.refresh_from_db()
    return order.data["ifood"]["handshakes"]["dispute-1"]


def test_event_before_order_retries_and_persists_before_ack():
    evt = event()
    with patch.object(ifood_events, "acknowledge", return_value=True) as ack:
        assert ifood_events.process_events([evt])["failed"] == 1
        ack.assert_not_called()
        order = Order.objects.create(ref="HS-ORDER", external_ref="external-order", channel_ref="ifood")
        assert ifood_events.process_events([evt])["ingested"] == 1
        assert record(order)["raw"]["id"] == "dispute-1"
        assert ifood_events.process_events([evt])["deduped"] == 1
    assert not Directive.objects.filter(topic=IFOOD_HANDSHAKE_RESPONSE).exists()


def test_settlement_before_dispute_never_reopens_or_cancels(order):
    assert ingest(event("HSS", "evt-settlement"))["ingested"] == 1
    assert ingest(event())["ingested"] == 1
    assert record(order)["state"] == "settled"
    assert order.status == "completed"
    assert order.data["ifood"]["handshake_pending"] is False
    assert hs.projection(order)[0]["can_respond"] is False


def test_enqueue_commits_only_operator_intention_and_blocks_second_decision(order):
    payload = queued(order)
    assert record(order)["state"] == "queued"
    assert payload["dispute_id"] == "dispute-1"
    with pytest.raises(hs.HandshakeValidationError):
        hs.enqueue_response(order, dispute_id="dispute-1", decision="reject", reason="WRONG_ORDER", actor="operator:2")
    assert Directive.objects.filter(topic=IFOOD_HANDSHAKE_RESPONSE).count() == 1
    assert order.status == "completed"


@pytest.mark.parametrize("decision,reason,detail", [("accept", "", ""), ("reject", "INVALID", ""),
    ("alternative", "", ""), ("accept", "CUSTOMER_SATISFACTION", "x" * 251)])
def test_invalid_decisions_never_enqueue(order, decision, reason, detail):
    ingest(event())
    with pytest.raises(hs.HandshakeValidationError):
        hs.enqueue_response(order, dispute_id="dispute-1", decision=decision, reason=reason, detail_reason=detail, actor="op")
    assert not Directive.objects.filter(topic=IFOOD_HANDSHAKE_RESPONSE).exists()


def test_delivery_uses_dispute_id_and_only_once_until_hss(order):
    payload = queued(order)
    with patch.object(hs.ifood_auth, "authorized_headers", return_value={"Authorization": "local-test"}), patch.object(
        hs.requests, "post", return_value=Mock(status_code=201, json=lambda: {"status": "ACCEPTED"}),
    ) as post:
        hs.deliver_response(payload)
        hs.deliver_response(payload)
    post.assert_called_once_with("https://merchant-api.ifood.com.br/order/v1.0/disputes/dispute-1/accept",
        headers={"Authorization": "local-test"}, json={"reason": "CUSTOMER_SATISFACTION"}, timeout=30)
    assert record(order)["state"] == "sent"
    ingest(event("HSS", "settlement-event"))
    assert record(order)["state"] == "settled"
    assert order.status == "completed"


def test_timeout_is_ambiguous_and_never_resends_financial_decision(order):
    payload = queued(order)
    with patch.object(hs.ifood_auth, "authorized_headers", return_value={"Authorization": "local-test"}), patch.object(
        hs.requests, "post", side_effect=requests.Timeout,
    ) as post:
        hs.deliver_response(payload)
        hs.deliver_response(payload)
    assert post.call_count == 1
    assert record(order)["state"] == "unknown"


def test_hss_during_send_is_not_overwritten(order):
    payload = queued(order)
    def reply(*args, **kwargs):
        ingest(event("HSS", "settlement-in-flight"))
        return Mock(status_code=201, json=lambda: {})
    with patch.object(hs.ifood_auth, "authorized_headers", return_value={"Authorization": "local-test"}), patch.object(hs.requests, "post", side_effect=reply):
        hs.deliver_response(payload)
    assert record(order)["state"] == "settled"


@pytest.mark.parametrize("expiry", ["2026-13-99T19:00:00Z", "", "2020-01-01T12:00:00Z"])
def test_invalid_or_expired_dispute_is_visible_but_cannot_be_answered(order, expiry):
    evt = event()
    evt["metadata"]["expiresAt"] = expiry
    ingest(evt)
    order.refresh_from_db()
    assert hs.projection(order)[0]["can_respond"] is False
    assert order.data["ifood"]["handshake_pending"] is True


def test_persistence_failure_never_acknowledges(order):
    with patch.object(hs, "_save", side_effect=RuntimeError("storage failed")), patch.object(ifood_events, "acknowledge") as ack:
        assert ifood_events.process_events([event()])["failed"] == 1
    ack.assert_not_called()
    order.refresh_from_db()
    assert not order.data.get("ifood", {}).get("handshakes")


def test_revision_and_unsupported_scenario_fail_closed(order):
    from shopman.shop.services.operator_orders import operational_revision
    stale = operational_revision(order)
    ingest(event())
    with pytest.raises(hs.HandshakeValidationError):
        hs.enqueue_response(order, dispute_id="dispute-1", decision="accept", reason="CUSTOMER_SATISFACTION", actor="op", expected_revision=stale)
    other = event(event_id="unsupported")
    other["metadata"].update(id="dispute-other", action="PROPOSED_AMOUNT_REFUND")
    ingest(other)
    with pytest.raises(hs.HandshakeValidationError):
        hs.enqueue_response(order, dispute_id="dispute-other", decision="accept", reason="CUSTOMER_SATISFACTION", actor="op")
    assert not Directive.objects.filter(topic=IFOOD_HANDSHAKE_RESPONSE).exists()


def test_worker_expiry_does_not_send_or_execute_timeout_action(order):
    payload = queued(order)
    future = timezone.now() + timedelta(hours=1)
    with patch.object(hs.timezone, "now", return_value=future), patch.object(hs.requests, "post") as post:
        hs.deliver_response(payload)
    post.assert_not_called()
    assert record(order)["state"] == "expired"
    assert order.status == "completed"


def test_accept_without_reason_options_sends_empty_body_and_reject_requires_enum(order):
    evt = event()
    evt["metadata"].pop("acceptCancellationReasons")
    ingest(evt)
    hs.enqueue_response(order, dispute_id="dispute-1", decision="accept", actor="op")
    assert record(order)["response"]["body"] == {}


def test_projection_filters_unsafe_evidence_links(order):
    evt = event()
    evt["metadata"]["evidences"] = [{"url": value} for value in ["javascript:alert(1)", "https://user:password@example.com", "https://[", "https://example.com/evidence"]]
    evt["metadata"]["item"] = {"id": "food-1", "quantity": 2}
    evt["metadata"]["alternatives"] = [{"type": "REFUND"}]
    ingest(evt)
    order.refresh_from_db()
    projected = hs.projection(order)[0]
    assert projected["evidence_urls"] == ["https://example.com/evidence"]
    assert projected["items"] == ["2 × food-1"]
    assert projected["alternatives_available"] is True


@pytest.mark.parametrize("metadata", [
    {"id": "settlement-1", "disputeId": "dispute-1", "status": "INVALID"},
    {"id": "settlement-1", "status": "ACCEPTED"},
])
def test_malformed_settlement_cannot_hide_pending_dispute(order, metadata):
    ingest(event())
    evt = event("HSS", "bad-settlement")
    evt["metadata"] = metadata
    with patch.object(ifood_events, "acknowledge") as ack:
        assert ifood_events.process_events([evt])["failed"] == 1
    ack.assert_not_called()
    assert record(order)["state"] == "open"
    assert order.data["ifood"]["handshake_pending"] is True


def test_delivery_explicit_rejection_uses_official_body(order):
    ingest(event())
    hs.enqueue_response(order, dispute_id="dispute-1", decision="reject", reason="WRONG_ORDER", actor="op")
    payload = Directive.objects.get(topic=IFOOD_HANDSHAKE_RESPONSE).payload
    with patch.object(hs.ifood_auth, "authorized_headers", return_value={"Authorization": "local-test"}), patch.object(hs.requests, "post", return_value=Mock(status_code=201, json=lambda: {})) as post:
        hs.deliver_response(payload)
    assert post.call_args.args[0].endswith("/disputes/dispute-1/reject")
    assert post.call_args.kwargs["json"] == {"reason": "WRONG_ORDER"}


def test_enqueue_rolls_back_state_if_durable_queue_fails(order):
    ingest(event())
    with patch.object(hs, "create_deduped", side_effect=RuntimeError("queue unavailable")), pytest.raises(RuntimeError):
        hs.enqueue_response(order, dispute_id="dispute-1", decision="reject", reason="WRONG_ORDER", actor="op")
    assert record(order)["state"] == "open"


def test_official_hss_example_without_metadata_id_is_durable(order):
    ingest(event())
    evt = event("HSS", "official-settlement-event")
    evt["metadata"].pop("id")
    assert ingest(evt)["ingested"] == 1
    assert "official-settlement-event" in record(order)["settlements"]
    assert ingest(evt)["deduped"] == 1
    assert record(order)["state"] == "settled"


def test_intermediate_alternative_stays_visible_and_late_replay_never_reopens_final(order):
    ingest(event())
    alternative = event("HSS", "alternative-event")
    alternative["metadata"].update(id="alternative-1", status="ALTERNATIVE_REPLIED")
    ingest(alternative)
    assert record(order)["state"] == "awaiting_customer"
    assert order.data["ifood"]["handshake_pending"] is True
    assert not hs.projection(order)[0]["can_respond"]
    ingest(event("HSS", "final-event"))
    assert record(order)["state"] == "settled"
    alternative["id"] = "late-alternative-event"
    alternative["metadata"]["id"] = "alternative-late"
    ingest(alternative)
    assert record(order)["state"] == "settled"
    assert order.data["ifood"]["handshake_pending"] is False
