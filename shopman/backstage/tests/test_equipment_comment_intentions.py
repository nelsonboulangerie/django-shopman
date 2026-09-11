"""Completed order custody stays actionable; comments and returns have one receipt."""
import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from shopman.orderman.models import Order

from shopman.shop.models import Shop
from shopman.shop.services.operator_orders import operational_revision

pytestmark = pytest.mark.django_db


@pytest.fixture
def context(client, django_user_model):
    Shop.objects.create(name="Synthetic custody lab")
    user = django_user_model.objects.create_user(username="custody-lab", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    order = Order.objects.create(ref="COMPLETED-CUSTODY", status="completed", data={
        "dispatch": {"equipment": ["card_machine"], "equipment_out_at": "2026-09-10T12:00:00Z"}})
    return user, order


@pytest.mark.parametrize("operation,field,inputs,event", [("equipment-back", "equipment", {}, "equipment_returned"), ("comment", "comment", {"note": "Synthetic note"}, "operator_comment")])
def test_receipt_prevents_repeated_custody_or_comment(client, context, operation, field, inputs, event):
    user, order = context
    url = reverse(f"api-backstage-order-{operation}", args=[order.ref])
    body = {"expected_actor_id": user.pk, "base_revision": operational_revision(order, field=field), **inputs}
    first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="same-intention")
    assert first.status_code == 200, first.content
    repeated = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="same-intention")
    assert repeated.status_code == 200
    assert repeated.json()["replayed"]
    receipt = client.get(url, {"idempotency_key": "same-intention"})
    assert receipt.json()["outcome"] == "applied"
    assert order.events.filter(type=event).count() == 1


def test_completed_custody_has_its_own_authorized_action_in_queue(client, context):
    user, order = context
    queue = client.get(reverse("api-backstage-orders")).json()["queue"]
    row = next(row for row in queue["equipment_out"] if row["order_ref"] == order.ref)
    action = next(action for action in row["actions"] if action["ref"] == "equipment-back")
    assert action["enabled"]
    assert action["payload_schema"]["expected_actor_id"] == user.pk
    response = client.post(reverse("api-backstage-order-equipment-back", args=[order.ref]),
        action["payload_schema"], content_type="application/json", HTTP_IDEMPOTENCY_KEY="return-after-completion")
    assert response.status_code == 200
    assert client.get(reverse("api-backstage-orders")).json()["queue"]["equipment_out"] == []
