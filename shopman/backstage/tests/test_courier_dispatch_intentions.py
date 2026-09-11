"""Operator dispatch is a local queue intention; no provider call is made here."""
import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import COURIER_DISPATCH
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db


@pytest.fixture
def context(client, django_user_model, settings):
    settings.SHOPMAN_COURIER_ADAPTER = "shopman.shop.adapters.courier_mock"
    Shop.objects.create(name="Synthetic dispatch lab")
    user = django_user_model.objects.create_user(username="dispatch-lab", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    order = Order.objects.create(ref="DISPATCH-LAB", status="ready", data={"fulfillment_type": "delivery"})
    return user, order


def observed(client, order):
    from django.contrib.auth import get_user_model

    from shopman.backstage.projections.order_queue import build_operator_order

    user = get_user_model().objects.get(username="dispatch-lab")
    action = next(a for a in build_operator_order(order, user=user).actions if a.ref == "courier-dispatch")
    assert action.enabled
    return action.payload_schema


def test_dispatch_requires_observed_intention(client, context):
    user, order = context
    response = client.post(reverse("api-backstage-order-courier-dispatch", args=[order.ref]), {"expected_actor_id": user.pk}, content_type="application/json")
    assert response.status_code == 400
    assert not Directive.objects.filter(topic=COURIER_DISPATCH).exists()


def test_dispatch_receipt_survives_projection_failure(client, context, monkeypatch):
    _, order = context
    body = observed(client, order)
    url = reverse("api-backstage-order-courier-dispatch", args=[order.ref])
    first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="dispatch-once")
    assert first.status_code == 200, first.content
    task = Directive.objects.get(topic=COURIER_DISPATCH)
    assert first.json()["directive_id"] == task.pk
    assert first.json()["status"] == "queued"
    repeated = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="dispatch-once")
    assert repeated.json()["replayed"]
    monkeypatch.setattr("shopman.backstage.api.operations.build_operator_order", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("projection unavailable")))
    receipt = client.get(url, {"idempotency_key": "dispatch-once"})
    assert receipt.status_code == 200
    assert receipt.json()["outcome"] == "applied"
    assert Directive.objects.filter(topic=COURIER_DISPATCH).count() == 1


def test_dispatch_rejects_changed_destination(client, context):
    _, order = context
    body = observed(client, order)
    order.data["delivery_address_structured"] = {"route": "Other street"}
    order.save(update_fields=["data"])
    response = client.post(reverse("api-backstage-order-courier-dispatch", args=[order.ref]), body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="old-destination")
    assert response.status_code == 409
    assert not Directive.objects.filter(topic=COURIER_DISPATCH).exists()


def test_cancel_queue_receipt_and_observed_ride(client, context):
    user, order = context
    from shopman.shop.services.courier import dispatch_revision

    order.data["courier"] = {"id_mch": "RIDE-CANCEL", "status": "A"}
    order.save(update_fields=["data"])
    body = {"expected_actor_id": user.pk, "base_revision": dispatch_revision(order)}
    url = reverse("api-backstage-order-courier-cancel", args=[order.ref])
    response = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="cancel-once")
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "queued"
    action = next(a for a in response.json()["order"]["actions"] if a["ref"] == "courier-cancel")
    assert not action["enabled"]
    assert not response.json()["order"]["courier"]["can_cancel"]
    assert client.get(url, {"idempotency_key": "cancel-once"}).json()["outcome"] == "applied"
    replay = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="cancel-once")
    assert replay.json()["directive_id"] == response.json()["directive_id"]
    order.data["courier"]["id_mch"] = "OTHER-RIDE"
    order.save(update_fields=["data"])
    stale = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="cancel-another")
    assert stale.status_code == 409


@pytest.mark.parametrize("reason", [True, 1.5, "1", 0, -1])
def test_cancel_does_not_coerce_reason(client, context, reason):
    _, order = context
    response = client.post(reverse("api-backstage-order-courier-cancel", args=[order.ref]),
        {"reason_id": reason}, content_type="application/json")
    assert response.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_quote_preparation_outside_transaction_and_replay_skips_provider(client, context, monkeypatch):
    from unittest.mock import Mock

    from django.db import connection

    from shopman.shop.services.courier import dispatch_revision

    user, order = context
    quote = {"value_q": 1250, "minutes": 15, "km": 4, "value_display": "R$ 12,50"}

    def prepare(observed):
        assert not connection.in_atomic_block
        assert observed.ref == order.ref
        return quote

    provider = Mock(side_effect=prepare)
    monkeypatch.setattr("shopman.backstage.services.orders.courier_quote", provider)
    body = {"expected_actor_id": user.pk, "base_revision": dispatch_revision(order)}
    url = reverse("api-backstage-order-courier-quote", args=[order.ref])
    response = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="quote-once")
    assert response.status_code == 200, response.content
    assert response.json()["quote"] == quote
    again = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="quote-once")
    assert again.json()["replayed"]
    provider.assert_called_once()
    assert client.get(url, {"idempotency_key": "quote-once"}).json()["quote"] == quote
    order.refresh_from_db()
    assert order.data["courier"]["estimate"] == {"value_q": 1250, "minutes": 15, "km": 4}


def test_quote_response_for_changed_destination_is_not_stored(client, context, monkeypatch):
    from shopman.shop.services.courier import dispatch_revision

    user, order = context
    body = {"expected_actor_id": user.pk, "base_revision": dispatch_revision(order)}

    def delayed(observed):
        other = Order.objects.get(pk=order.pk)
        other.data["delivery_address"] = "Different destination"
        other.save(update_fields=["data"])
        return {"value_q": 1250, "minutes": 15, "km": 4}

    monkeypatch.setattr("shopman.backstage.services.orders.courier_quote", delayed)
    response = client.post(reverse("api-backstage-order-courier-quote", args=[order.ref]), body,
        content_type="application/json", HTTP_IDEMPOTENCY_KEY="quote-stale")
    assert response.status_code == 409
    order.refresh_from_db()
    assert "estimate" not in order.data.get("courier", {})
