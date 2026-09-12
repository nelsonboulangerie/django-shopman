"""Local fiscal retry must report whether work was actually queued."""
from unittest.mock import patch

import pytest
from shopman.orderman.models import Order

from shopman.backstage.services import orders
from shopman.backstage.services.exceptions import OrderError

pytestmark = pytest.mark.django_db


def test_no_backend_and_no_directive_cannot_claim_requeue():
    order = Order.objects.create(ref="FISCAL-NO-QUEUE", status="completed", total_q=1000,
        data={"fiscal": {"issue_document": True}})
    with patch("shopman.shop.services.fiscal.fiscal_pool.get_backend", return_value=None):
        with pytest.raises(OrderError):
            orders.requeue_fiscal_emission(order, actor="lab")
    assert not order.events.filter(type="fiscal_requeued").exists()


@pytest.fixture
def context(client, django_user_model):
    from django.contrib.auth.models import Permission

    from shopman.shop.models import Shop

    Shop.objects.create(name="Synthetic fiscal and link lab")
    user = django_user_model.objects.create_user(username="local-effects", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="manage_orders", content_type__app_label="shop"))
    client.force_login(user)
    return user


@pytest.mark.parametrize("operation", ["requeue-fiscal", "resend-payment-link"])
def test_lost_response_receipt_and_replay_enqueue_once(client, context, operation):
    from django.urls import reverse
    from shopman.orderman.models import Directive

    from shopman.shop.directives import FISCAL_EMIT_NFCE
    from shopman.shop.services import notification

    order = Order.objects.create(ref="ONE-LOCAL-EFFECT", status="completed", total_q=1000,
        data={"fiscal": {"issue_document": True}, "payment": {"method": "link", "checkout_url": "https://example.invalid/synthetic"}})
    if operation == "requeue-fiscal":
        directive = Directive.objects.create(topic=FISCAL_EMIT_NFCE, payload={"order_ref": order.ref}, status="failed")
        revision = orders.fiscal_revision(order)
    else:
        revision = notification.payment_link_revision(order)
    url = reverse(f"api-backstage-order-{operation}", args=[order.ref])
    body = {"expected_actor_id": context.pk, "base_revision": revision}
    first = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="same-effect")
    assert first.status_code == 200, first.content
    assert first.json()["effect_status"] == "queued"
    receipt = client.get(url, {"idempotency_key": "same-effect"})
    assert receipt.json()["outcome"] == "applied"
    assert receipt.json()["directive_id"] == first.json()["directive_id"]
    repeated = client.post(url, body, content_type="application/json", HTTP_IDEMPOTENCY_KEY="same-effect")
    assert repeated.status_code == 200, repeated.content
    assert repeated.json()["replayed"]
    assert Directive.objects.filter(payload__order_ref=order.ref).count() == 1
    if operation == "requeue-fiscal":
        directive.refresh_from_db()
        assert directive.status == "queued"
        assert order.events.filter(type="fiscal_requeued").count() == 1
    else:
        # A new intention cannot bypass the established resend cadence.
        second = client.post(url, {**body, "base_revision": notification.payment_link_revision(order)},
            content_type="application/json", HTTP_IDEMPOTENCY_KEY="another-effect")
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "payment_link_send_pending"


@pytest.mark.parametrize("operation", ["requeue-fiscal", "resend-payment-link"])
def test_changed_effect_context_refuses_without_enqueue(client, context, operation):
    from django.urls import reverse
    from shopman.orderman.models import Directive

    from shopman.shop.services import notification

    order = Order.objects.create(ref="CHANGED-EFFECT", status="completed", total_q=1000,
        data={"fiscal": {"issue_document": True}, "payment": {"method": "link", "checkout_url": "https://example.invalid/old"}})
    revision = orders.fiscal_revision(order) if operation == "requeue-fiscal" else notification.payment_link_revision(order)
    order.data["payment"]["checkout_url"] = "https://example.invalid/new"
    order.save(update_fields=["data"])
    response = client.post(reverse(f"api-backstage-order-{operation}", args=[order.ref]),
        {"expected_actor_id": context.pk, "base_revision": revision}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="stale-effect")
    assert response.status_code == 409, response.content
    assert response.json()["outcome"] == "not_applied"
    assert not Directive.objects.filter(payload__order_ref=order.ref).exists()


def test_retry_refreshes_corrected_fiscal_data_and_preserves_failure_history():
    from shopman.orderman.models import Directive

    from shopman.shop.directives import FISCAL_EMIT_NFCE

    order = Order.objects.create(ref="CORRECT-FISCAL", status="completed", total_q=1000, data={
        "fiscal": {"issue_document": True, "tax_id": "52998224725"},
        "fulfillment_type": "delivery", "delivery_address_structured": {"route": "Rua corrigida", "neighborhood": "Bairro real"},
        "payment": {"method": "cash", "amount_q": 1000},
    })
    directive = Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", attempts=1,
        last_error="Entrega a domicílio: confira bairro.", payload={"order_ref": order.ref, "delivery": {"address": {}}})
    orders.requeue_fiscal_emission(order, actor="manager")
    directive.refresh_from_db()
    assert directive.status == "queued"
    assert directive.payload["delivery"]["address"]["neighborhood"] == "Bairro real"
    assert directive.payload["customer"]["tax_id"] == "52998224725"
    assert directive.payload["payment"]["amount_q"] == 1000
    assert directive.attempts == 1
    assert Directive.objects.filter(payload__order_ref=order.ref).count() == 1
    event = order.events.get(type="fiscal_requeued")
    assert "bairro" in event.payload["previous_error"]


def test_retry_never_rebuilds_authorized_document():
    from shopman.orderman.models import Directive

    from shopman.shop.directives import FISCAL_EMIT_NFCE

    order = Order.objects.create(ref="ALREADY-AUTHORIZED", status="completed", total_q=1000,
        data={"nfce_access_key": "AUTHORIZED", "fiscal": {"issue_document": True}})
    directive = Directive.objects.create(topic=FISCAL_EMIT_NFCE, status="failed", payload={"order_ref": order.ref, "sealed": True})
    with patch("shopman.shop.services.fiscal.build_emission_payload") as rebuild:
        with pytest.raises(OrderError, match="já autorizada"):
            orders.requeue_fiscal_emission(order, actor="manager")
    rebuild.assert_not_called()
    directive.refresh_from_db()
    assert directive.status == "failed"
    assert directive.payload["sealed"] is True
