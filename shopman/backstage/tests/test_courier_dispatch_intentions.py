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
