"""Electronic cancellation request: protocol, routing and access fences."""

from __future__ import annotations

import json

import pytest
from shopman.orderman.models import OrderEvent

from shopman.backstage.models import OperatorAlert
from shopman.storefront.services.cancellation_requests import EVENT_TYPE

pytestmark = pytest.mark.django_db


def _request(client, ref: str, *, key: str = "cancel-request-1", reason: str = ""):
    return client.post(
        f"/api/v1/orders/{ref}/cancellation-request/",
        data=json.dumps({"reason": reason}),
        content_type="application/json",
        HTTP_X_IDEMPOTENCY_KEY=key,
    )


def test_paid_order_offers_human_cancellation_request(order_paid):
    from shopman.storefront.presentation.order_tracking import build_order_tracking

    projection = build_order_tracking(order_paid)

    assert not any(action.ref == "cancel_order" for action in projection.actions)
    action = next(action for action in projection.actions if action.ref == "request_cancellation")
    assert action.label == "Solicitar cancelamento"
    assert action.href.endswith("/cancellation-request/")


def test_request_returns_protocol_without_changing_order_and_routes_to_orders(client, order_paid):
    response = _request(
        client,
        order_paid.ref,
        reason="Não vou conseguir receber no horário.",
    )

    assert response.status_code == 200
    payload = response.json()
    request = payload["cancellation_request"]
    assert request["protocol"].startswith("SC-")
    assert request["title"] == "Solicitação recebida"
    order_paid.refresh_from_db()
    assert order_paid.status == "accepted"

    event = OrderEvent.objects.get(order=order_paid, type=EVENT_TYPE)
    assert event.payload == {
        "protocol": request["protocol"],
        "reason": "Não vou conseguir receber no horário.",
    }
    alert = OperatorAlert.objects.get(
        type="customer_cancellation_requested",
        order_ref=order_paid.ref,
    )
    assert alert.audience == "orders"
    assert request["protocol"] in alert.message
    assert "eventual estorno" in alert.message


def test_request_is_idempotent_and_tracking_keeps_the_same_protocol(client, order_paid):
    first = _request(client, order_paid.ref, key="same-intention")
    second = _request(client, order_paid.ref, key="same-intention")
    tracking = client.get(f"/api/v1/tracking/{order_paid.ref}/")

    assert first.status_code == second.status_code == tracking.status_code == 200
    protocol = first.json()["cancellation_request"]["protocol"]
    assert second.json()["cancellation_request"]["protocol"] == protocol
    assert tracking.json()["cancellation_request"]["protocol"] == protocol
    assert OrderEvent.objects.filter(order=order_paid, type=EVENT_TYPE).count() == 1
    assert OperatorAlert.objects.filter(
        type="customer_cancellation_requested",
        order_ref=order_paid.ref,
    ).count() == 1


def test_request_is_not_an_order_existence_oracle(client, order_paid):
    stranger = type(client)()

    response = _request(stranger, order_paid.ref)

    assert response.status_code == 404
    assert not OrderEvent.objects.filter(order=order_paid, type=EVENT_TYPE).exists()


def test_terminal_outcome_resolves_the_operator_alert(
    client,
    order_paid,
    django_capture_on_commit_callbacks,
):
    from shopman.shop.handlers.cancellation_requests import on_order_changed

    assert _request(client, order_paid.ref).status_code == 200
    alert = OperatorAlert.objects.get(
        type="customer_cancellation_requested",
        order_ref=order_paid.ref,
    )
    order_paid.status = "cancelled"

    with django_capture_on_commit_callbacks(execute=True):
        on_order_changed(
            sender=type(order_paid),
            order=order_paid,
            event_type="status_changed",
            actor="operator:test",
        )

    alert.refresh_from_db()
    assert alert.acknowledged is True
    assert alert.resolved_at is not None
    assert alert.resolved_by == "order-status:operator:test"
