"""Cancellation intentions preserve approvals and prepare provider reads outside locks."""
import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.db import connection
from django.urls import reverse
from shopman.orderman.models import IdempotencyKey, Order

from shopman.shop.models import Shop
from shopman.shop.services import cancellation, operator_orders

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def context(client, django_user_model):
    Shop.objects.create(name="Synthetic cancellation lab")
    user = django_user_model.objects.create_user(username="cancel-intention", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    order = Order.objects.create(ref="CANCEL-RECEIPT", status="new", channel_ref="ifood", external_ref="synthetic-order",
        data={"payment": {"method": "cash"}})
    return user, order


@pytest.mark.parametrize("operation", ["cancel", "reject"])
def test_replay_and_receipt_do_not_repeat_provider_preparation(client, context, operation):
    user, order = context
    url = reverse(f"api-backstage-order-{operation}", args=[order.ref])
    body = {"expected_actor_id": user.pk, "base_revision": operator_orders.operational_revision(order),
        "reason": "Motivo sintético", "cancellation_code": "SYNTHETIC"}
    key = str(uuid.uuid4())

    def reasons(_order):
        assert not connection.in_atomic_block
        return [{"code": "SYNTHETIC", "description": "Motivo sintético"}]

    with patch.object(operator_orders, "cancellation_reasons", side_effect=reasons) as lookup:
        first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
        assert first.status_code == 200, first.content
        second = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
        assert second.status_code == 200, second.content
        assert second.json()["replayed"]
        receipt = client.get(url, {"idempotency_key": key})
        assert receipt.json()["outcome"] == "applied"
        conflict = client.post(url, {**body, "reason": "Outra decisão"}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
        assert conflict.status_code == 409
        assert lookup.call_count == 1
    assert order.events.filter(type="status_changed").count() == 1


def test_paid_cancel_preserves_signature_and_never_retains_pin(client, context):
    user, order = context
    order = Order.objects.create(ref="CANCEL-PAID-RECEIPT", status="new", channel_ref="web", data={"payment": {"method": "cash"}})
    url = reverse("api-backstage-order-cancel", args=[order.ref])
    body = {"expected_actor_id": user.pk, "base_revision": operator_orders.operational_revision(order), "reason": "Sintético"}
    key = str(uuid.uuid4())
    paid = cancellation.OperatorCancelPolicy(allowed=True, requires_approval=True)
    with patch.object(cancellation, "operator_cancel_policy", return_value=paid):
        refusal = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
        assert refusal.status_code == 422
        assert refusal.json()["error"]["code"] == "manager_approval_required"
        order.refresh_from_db()
        assert order.status == "new"
        assert not IdempotencyKey.objects.filter(key=key).exists()
        with patch("shopman.backstage.api.operations.pos_tabs_service.validate_manager_override", return_value=user) as signature:
            approved = client.post(url, {**body, "manager_approval": {"pin": "SYNTHETIC-NOT-A-PIN"}}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
            assert approved.status_code == 200, approved.content
            repeated = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)
            assert repeated.status_code == 200
            assert signature.call_count == 1
    assert "SYNTHETIC-NOT-A-PIN" not in str(IdempotencyKey.objects.get(key=key).response_body)


@pytest.mark.parametrize("operation", ["cancel", "reject"])
def test_old_client_has_no_effect(client, context, operation):
    _user, order = context
    url = reverse(f"api-backstage-order-{operation}", args=[order.ref])
    response = client.post(url, {"reason": "Sintético"}, content_type="application/json")
    assert response.status_code in {400, 409}
    order.refresh_from_db()
    assert order.status == "new"
