"""Negotiations stay visible after delivery; operator intents never send inline."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.backstage.projections.order_queue import build_two_zone_queue
from shopman.shop.models import Shop
from shopman.shop.services import ifood_handshake as hs
from shopman.shop.services import operator_orders

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def context(client, django_user_model):
    Shop.objects.create(name="Handshake API lab")
    user = django_user_model.objects.create_user(username="handshake-operator", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    order = Order.objects.create(ref="IFOOD-HANDSHAKE", external_ref="test-order", channel_ref="ifood", status="completed", data={"payment": {"method": "external"}})
    hs.persist_event(order, {"id": "hsd", "metadata": {
        "id": "dispute", "handshakeType": "AFTER_DELIVERY", "action": "CANCELLATION", "message": "Item incorreto",
        "expiresAt": (timezone.now() + timedelta(minutes=10)).isoformat(),
        "acceptCancellationReasons": ["CUSTOMER_SATISFACTION"], "timeoutAction": "ACCEPT_CANCELLATION",
    }}, settlement=False)
    return user, order


def test_completed_order_with_negotiation_remains_visible_and_actions_require_permission(context):
    user, order = context
    queue = build_two_zone_queue(user=user)
    assert not queue.intake and not queue.prep and not queue.expedition_pickup
    card = queue.ifood_negotiation_orders[0]
    assert card.ref == order.ref and card.status == "completed"
    negotiation = card.ifood_negotiations[0]
    assert negotiation.can_respond
    assert all(action.enabled and action.idempotency == "required" for action in negotiation.actions)
    denied = build_two_zone_queue(user=None).ifood_negotiation_orders[0].ifood_negotiations[0]
    assert not denied.can_respond and all(not action.enabled for action in denied.actions)
    hs.persist_event(order, {"id": "hss", "metadata": {"id": "settlement", "disputeId": "dispute", "status": "ACCEPTED"}}, settlement=True)
    assert not build_two_zone_queue(user=user).ifood_negotiation_orders


def test_response_replay_records_one_request_and_never_calls_provider_inline(client, context):
    user, order = context
    url = reverse("api-backstage-order-ifood-handshake", args=[order.ref])
    body = {"expected_actor_id": user.pk, "base_revision": operator_orders.operational_revision(order),
            "dispute_id": "dispute", "decision": "accept", "reason": "CUSTOMER_SATISFACTION", "detail_reason": "Conferido na loja"}
    key = str(uuid4())
    with patch.object(hs.requests, "post") as external:
        first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
        assert first.status_code == 200, first.content
        assert first.json()["response_queued"]
        second = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
        assert second.status_code == 200 and second.json()["replayed"]
        receipt = client.get(url, {"idempotency_key": key})
        assert receipt.json()["outcome"] == "applied"
        conflict = client.post(url, {**body, "decision": "reject"}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
        assert conflict.status_code == 409
        external.assert_not_called()
    assert Directive.objects.filter(topic="ifood.handshake_response").count() == 1
    order.refresh_from_db()
    assert order.status == "completed"


@pytest.mark.parametrize("mutation", ["actor", "revision", "reason", "missing_intention"])
def test_unreviewed_or_stale_decision_has_no_effect(client, context, mutation):
    user, order = context
    body = {"expected_actor_id": user.pk, "base_revision": operator_orders.operational_revision(order),
            "dispute_id": "dispute", "decision": "accept", "reason": "CUSTOMER_SATISFACTION"}
    if mutation == "actor":
        body["expected_actor_id"] = -1
    if mutation == "revision":
        body["base_revision"] = "stale"
    if mutation == "reason":
        body["reason"] = "invented"
    headers = {} if mutation == "missing_intention" else {"HTTP_IDEMPOTENCY_KEY": str(uuid4())}
    response = client.post(reverse("api-backstage-order-ifood-handshake", args=[order.ref]), body, content_type="application/json", **headers)
    assert response.status_code in {400, 409}, response.content
    assert not Directive.objects.filter(topic="ifood.handshake_response").exists()


def test_protected_evidence_uses_same_origin_endpoint_and_private_attachment(client, context):
    user, order = context
    order.data["ifood"]["handshakes"]["dispute"]["raw"]["evidences"] = [
        {"url": "javascript:invalid"},
        {"url": "https://merchant-api.ifood.com.br/order/v1.0/orders/test-order/cancellationEvidences/image-1"},
    ]
    order.save(update_fields=["data"])
    link = build_two_zone_queue(user=user).ifood_negotiation_orders[0].ifood_negotiations[0].evidence_urls[0]
    assert "index=1" in link and link.startswith("/api/v1/backstage/orders/")
    assert "merchant-api" not in link
    with patch("shopman.shop.services.ifood_evidence.fetch_evidence", return_value=(b"\x89PNG-test", "image/png")) as fetch:
        response = client.get(link)
        assert response.status_code == 200
        assert response.content == b"\x89PNG-test"
        assert response["Content-Type"] == "image/png"
        assert response["Content-Disposition"].startswith("attachment;")
        assert response["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in response["Cache-Control"]
        assert fetch.call_args.kwargs == {"dispute_id": "dispute", "index": 1}


def test_evidence_requires_order_management_permission(client, context, django_user_model):
    _user, order = context
    user = django_user_model.objects.create_user(username="no-order-right", is_staff=True)
    client.force_login(user)
    with patch("shopman.shop.services.ifood_evidence.fetch_evidence") as fetch:
        response = client.get(reverse("api-backstage-order-ifood-handshake-evidence", args=[order.ref]), {"dispute_id": "dispute", "index": "0"})
        assert response.status_code == 403
        fetch.assert_not_called()
