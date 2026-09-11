"""Confirmation follows the same atomic intention contract as advancing an order."""
import uuid

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from shopman.orderman.models import Order

from shopman.shop.models import Shop
from shopman.shop.services.operator_orders import operational_revision

pytestmark = pytest.mark.django_db


@pytest.fixture
def context(client, django_user_model):
    Shop.objects.create(name="Lab")
    user = django_user_model.objects.create_user(username="confirm-lab", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    order = Order.objects.create(ref="CONFIRM-INTENTION", status="new", data={
        "availability_decision": {"approved": True, "decisions": []}, "payment": {"method": "cash"},
    })
    return user, order, reverse("api-backstage-order-confirm", args=[order.ref])


def test_confirmation_replay_returns_the_same_local_result(client, context):
    user, order, url = context
    key = str(uuid.uuid4())
    body = {"base_revision": operational_revision(order), "expected_actor_id": user.pk}
    first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    second = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
    assert first.status_code == 200, first.content
    assert second.status_code == 200, second.content
    assert second.json()["replayed"] is True
    assert order.events.filter(type="status_changed").count() == 1
    receipt = client.get(url, {"idempotency_key": key})
    assert receipt.json()["outcome"] == "applied"


def test_confirmation_legacy_client_cannot_bypass_intention(client, context):
    _user, order, url = context
    response = client.post(url, {}, content_type="application/json")
    assert response.status_code in {400, 409}
    order.refresh_from_db()
    assert order.status == "new"
