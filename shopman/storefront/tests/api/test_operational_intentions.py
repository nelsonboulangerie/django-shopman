from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from django.utils import timezone
from shopman.orderman.models import Order, OrderItem

from shopman.shop.services import remote_mutations
from shopman.storefront.services.pickup_slots import get_slots
from shopman.storefront.tests._checkout_baseline import with_baseline
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_request_throttle():
    from django.core.cache import cache

    cache.clear()


def test_legacy_x_header_is_accepted():
    req = RequestFactory().post("/", HTTP_X_IDEMPOTENCY_KEY="intention-A")
    assert remote_mutations.idempotency_key_from_request(req, fallback="fallback") == "intention-A"


def test_checkout_response_loss_recovers_same_order(client):
    _seed_surface()
    assert client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 1}, content_type="application/json").status_code == 200
    payload = with_baseline(
        client,
        {
            "name": "Ana",
            "phone": "+5543999990001",
            "fulfillment_type": "pickup",
            "delivery_time_slot": get_slots()[-1]["ref"],
            "delivery_date": timezone.localdate().isoformat(),
            "payment_method": "cash",
            "idempotency_key": "checkout-audit-one",
        },
    )
    first = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert first.status_code == 201, first.content
    second = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert second.status_code == 201, second.content
    assert second.json() == first.json()
    assert Order.objects.filter(ref=first.json()["order_ref"]).count() == 1


def test_new_reorder_intent_changes_real_cart(client):
    _seed_surface()
    o = Order.objects.create(ref="AUDIT-REORDER", channel_ref="web", status="completed", total_q=100, data={})
    OrderItem.objects.create(
        order=o, line_id="1", sku="PAO-FRANCES", name="Pao", qty=1, unit_price_q=100, line_total_q=100
    )
    with patch("shopman.storefront.services.orders.get_accessible_order", return_value=o):
        one = client.post(
            f"/api/v1/orders/{o.ref}/reorder/",
            {"mode": "append"},
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY="first",
        )
        assert one.status_code == 200, one.content
        assert (
            client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 0}, content_type="application/json").status_code == 200
        )
        two = client.post(
            f"/api/v1/orders/{o.ref}/reorder/",
            {"mode": "append"},
            content_type="application/json",
            HTTP_X_IDEMPOTENCY_KEY="second",
        )
        assert two.status_code == 200, two.content
        actual = client.get("/api/v1/storefront/cart/").json()["cart"]
        assert two.json()["cart"]["is_empty"] is False
        assert actual["is_empty"] is False


def test_post_commit_defaults_failure_is_recoverable(client):
    _seed_surface()
    assert client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 1}, content_type="application/json").status_code == 200
    payload = with_baseline(
        client,
        {
            "name": "Ana",
            "phone": "+5543999990001",
            "fulfillment_type": "pickup",
            "delivery_time_slot": get_slots()[-1]["ref"],
            "delivery_date": timezone.localdate().isoformat(),
            "payment_method": "cash",
            "idempotency_key": "side-effect",
        },
    )
    with patch("shopman.shop.services.checkout.save_defaults", side_effect=RuntimeError("synthetic failure")):
        result = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert result.status_code == 201, result.content
    assert result.json()["convenience_pending"] == ["defaults"]
    from shopman.orderman.models import Directive

    from shopman.shop.services.checkout import recover_convenience_effect

    job = Directive.objects.get(topic="checkout.convenience", payload__effect="defaults")
    with patch("shopman.shop.services.checkout.save_defaults") as save:
        recover_convenience_effect(job)
        recover_convenience_effect(job)
    assert save.call_count == 1
    assert Order.objects.filter(ref=result.json()["order_ref"]).count() == 1


def test_explicit_notification_retry_preserves_choice():
    from shopman.guestman.services import customer as customers

    from shopman.shop.services.account import set_notification_consent

    c = customers.create(ref="AUDIT-C", first_name="Ana", phone="+5543999990001")
    assert "whatsapp" not in set_notification_consent(c.ref, "whatsapp", enabled=False)
    assert "whatsapp" not in set_notification_consent(c.ref, "whatsapp", enabled=False)


def test_stock_notice_checks_global_optout():
    _seed_surface()
    from shopman.guestman import ConsentService
    from shopman.guestman.services import customer as customers

    from shopman.shop.protocols import NotificationResult
    from shopman.storefront.models import StockAlertDelivery
    from shopman.storefront.services import stock_alerts
    from shopman.storefront.stock_alert_delivery import StockAlertDeliveryHandler

    c = customers.create(ref="AUDIT-S", first_name="Ana", phone="+5543999990002")
    sub = stock_alerts.subscribe("AUDIT-SKU", customer=c, alert_type="stock_back")
    ConsentService.revoke_consent(c.ref, "whatsapp")
    with (
        patch("shopman.shop.notifications.notify", return_value=NotificationResult(success=True)) as send,
        patch.object(stock_alerts, "_image_url", return_value=""),
    ):
        with patch(
            "shopman.storefront.services.sku_state.resolve",
            return_value=MagicMock(can_add_to_cart=True, available_qty=1),
        ):
            assert stock_alerts.notify_back_in_stock(sub.sku, source_ref="audit-move") == 1
            delivery = StockAlertDelivery.objects.get()
            StockAlertDeliveryHandler().handle(message=MagicMock(payload={"delivery_id": delivery.pk}), ctx={})
    assert send.call_count == 0


def test_edit_between_price_check_and_commit_cannot_change_confirmed_total(client):
    from shopman.shop.services import checkout

    _seed_surface()
    assert client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 1}, content_type="application/json").status_code == 200
    payload = with_baseline(
        client,
        {
            "name": "Ana",
            "phone": "+5543999990001",
            "fulfillment_type": "pickup",
            "delivery_time_slot": get_slots()[-1]["ref"],
            "delivery_date": timezone.localdate().isoformat(),
            "payment_method": "cash",
            "idempotency_key": "race-total",
        },
    )
    original = checkout._ensure_total_matches

    def concurrent_edit(session_key, channel_ref, expected):
        original(session_key, channel_ref, expected)
        changed = client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 2}, content_type="application/json")
        assert changed.status_code == 200, changed.content

    with patch.object(checkout, "_ensure_total_matches", side_effect=concurrent_edit):
        result = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert result.status_code == 400, result.content
    assert result.json()["error_code"] == "total_changed"
    assert Order.objects.count() == 0


def _checkout_payload(client, key="operational-test"):
    _seed_surface()
    assert client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 1}, content_type="application/json").status_code == 200
    return with_baseline(
        client,
        {
            "name": "Ana",
            "phone": "+5543999990001",
            "fulfillment_type": "pickup",
            "delivery_time_slot": get_slots()[-1]["ref"],
            "delivery_date": timezone.localdate().isoformat(),
            "payment_method": "cash",
            "idempotency_key": key,
        },
    )


def test_replay_with_original_cookie_and_read_recovery(client):
    from django.test import Client

    payload = _checkout_payload(client)
    original_cookie = client.cookies["sessionid"].value
    first = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert first.status_code == 201, first.content
    browser = Client()
    browser.cookies["sessionid"] = original_cookie
    read = browser.get("/api/v1/checkout/", HTTP_IDEMPOTENCY_KEY=payload["idempotency_key"])
    assert read.json()["order_ref"] == first.json()["order_ref"]
    repeated = browser.post("/api/v1/checkout/", payload, content_type="application/json")
    assert repeated.status_code == 201
    assert repeated.json()["order_ref"] == first.json()["order_ref"]
    stranger = Client()
    assert stranger.get("/api/v1/checkout/", HTTP_IDEMPOTENCY_KEY=payload["idempotency_key"]).status_code == 204
    assert Order.objects.count() == 1


def test_reused_key_with_different_payload_is_conflict(client):
    payload = _checkout_payload(client)
    assert client.post("/api/v1/checkout/", payload, content_type="application/json").status_code == 201
    result = client.post("/api/v1/checkout/", {**payload, "notes": "Different choice"}, content_type="application/json")
    assert result.status_code == 409
    assert result.json()["error_code"] == "idempotency_conflict"
    assert Order.objects.count() == 1


def test_same_total_material_revision_is_rejected(client):
    from shopman.shop.services import sessions

    payload = _checkout_payload(client)
    key = client.session["cart_session_key"]
    sessions.modify_session(
        session_key=key, channel_ref="web", ops=[{"op": "set_data", "path": "order_notes", "value": "Other tab"}]
    )
    result = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert result.status_code == 409, result.content
    assert result.json()["error_code"] == "revision_changed"
    assert not Order.objects.exists()


def test_legacy_checkout_requires_review_update_without_effect(client):
    payload = _checkout_payload(client)
    payload.pop("expected_revision")
    result = client.post("/api/v1/checkout/", payload, content_type="application/json")
    assert result.status_code == 400
    assert result.json()["field"] == "expected_revision"
    assert not Order.objects.exists()


@pytest.mark.parametrize(
    "route,payload",
    [
        ("draft", {"fulfillment_type": {}}),
        ("draft", {"fulfillment_type": "teleport"}),
        ("draft", {"delivery_address_structured": {"latitude": "bad"}}),
        ("loyalty", {"enabled": "false"}),
        ("loyalty", ["invalid"]),
    ],
)
def test_malformed_context_is_refused_without_writing(client, route, payload):
    _seed_surface()
    from shopman.orderman.models import Session

    before = list(Session.objects.values("data", "rev"))
    result = client.patch(f"/api/v1/checkout/{route}/", payload, content_type="application/json")
    assert result.status_code == 400, result.content
    assert list(Session.objects.values("data", "rev")) == before


def test_atomic_mutation_receipt_failure_rolls_back_effect():
    from shopman.orderman.models import IdempotencyKey

    original = IdempotencyKey.save

    def crash_after_effect(row, *args, **kwargs):
        if row.status == "done":
            raise RuntimeError("fault: receipt write")
        return original(row, *args, **kwargs)

    def effect():
        Order.objects.create(ref="ATOMIC-EFFECT", channel_ref="web")
        return {"ok": True}, 200

    with patch.object(IdempotencyKey, "save", crash_after_effect), pytest.raises(RuntimeError):
        remote_mutations.run_idempotent_mutation(
            scope="test-local", key="one", execute=effect, local_atomic=True, payload={"qty": 1}
        )
    assert not Order.objects.filter(ref="ATOMIC-EFFECT").exists()
    assert not IdempotencyKey.objects.filter(scope="test-local").exists()
    result = remote_mutations.run_idempotent_mutation(
        scope="test-local", key="one", execute=effect, local_atomic=True, payload={"qty": 1}
    )
    assert result.response_code == 200
    assert Order.objects.filter(ref="ATOMIC-EFFECT").count() == 1


def test_rating_merges_current_metadata_instead_of_stale_order():
    from shopman.shop.services.customer_orders import save_customer_rating

    order = Order.objects.create(ref="RATE-MERGE", channel_ref="web", data={})
    Order.objects.filter(pk=order.pk).update(data={"courier": {"job": "synthetic"}, "payment": {"status": "paid"}})
    save_customer_rating(order, rating=5, comment="Bom")
    order.refresh_from_db()
    assert order.data["payment"]["status"] == "paid"
    assert order.data["courier"]["job"] == "synthetic"
    assert order.data["customer_rating"]["rating"] == 5


def test_replace_replay_keeps_the_target_cart_and_does_not_reapply(client):
    _seed_surface()
    order = Order.objects.create(ref="REPLACE-INTENT", channel_ref="web", status="completed")
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO-FRANCES", name="Pão", qty=1, unit_price_q=100, line_total_q=100
    )
    client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 2}, content_type="application/json")
    cart_key = client.session["cart_session_key"]
    with patch("shopman.storefront.services.orders.get_accessible_order", return_value=order):
        first = client.post(
            f"/api/v1/orders/{order.ref}/reorder/",
            {"mode": "replace"},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="replace-1",
        )
        assert first.status_code == 200, first.content
        assert client.session["cart_session_key"] == cart_key
        client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 2}, content_type="application/json")
        replay = client.post(
            f"/api/v1/orders/{order.ref}/reorder/",
            {"mode": "replace"},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="replace-1",
        )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["cart"]["items_count"] == 2


def test_stock_claim_prevents_retry_after_unknown_provider_acceptance():
    from unittest.mock import MagicMock

    from shopman.shop.protocols import NotificationResult
    from shopman.storefront.models import StockAlertDelivery
    from shopman.storefront.services import stock_alerts
    from shopman.storefront.stock_alert_delivery import StockAlertDeliveryHandler

    _seed_surface()
    sub = stock_alerts.subscribe("PAO-FRANCES", phone="+5543999990007", alert_type="stock_back")
    with (
        patch(
            "shopman.storefront.services.sku_state.resolve",
            return_value=MagicMock(can_add_to_cart=True, available_qty=3),
        ),
        patch(
            "shopman.shop.notifications.notify",
            return_value=NotificationResult(success=False, error="acceptance_unconfirmed", outcome_unknown=True),
        ) as send,
    ):
        assert stock_alerts.notify_back_in_stock("PAO-FRANCES", source_ref="move-1") == 1
        delivery = StockAlertDelivery.objects.get()
        StockAlertDeliveryHandler().handle(message=MagicMock(payload={"delivery_id": delivery.pk}), ctx={})
        assert stock_alerts.notify_back_in_stock("PAO-FRANCES", source_ref="move-1") == 0
    sub.refresh_from_db()
    assert send.call_count == 1
    delivery.refresh_from_db()
    assert delivery.claimed_at is not None
    assert delivery.status == "indeterminate"
    assert sub.dispatch_accepted_at is None
    assert sub.notified_at is None


def test_partial_infrastructure_failure_rolls_back_bundle_without_losing_previous_items(client):
    from shopman.storefront.cart import CartService

    _seed_surface()
    client.put("/api/v1/cart/skus/PAO-FRANCES/", {"qty": 2}, content_type="application/json")
    order = Order.objects.create(ref="BUNDLE-FAIL", channel_ref="web", status="completed")
    for n in range(2):
        OrderItem.objects.create(
            order=order, line_id=str(n), sku="PAO-FRANCES", name="Pão", qty=1, unit_price_q=100, line_total_q=100
        )
    original = CartService.add_item
    calls = []

    def failing_add(*args, **kwargs):
        calls.append(kwargs["sku"])
        if len(calls) == 2:
            raise RuntimeError("fault: second item")
        return original(*args, **kwargs)

    with (
        patch("shopman.storefront.services.orders.get_accessible_order", return_value=order),
        patch.object(CartService, "add_item", side_effect=failing_add),
        pytest.raises(RuntimeError),
    ):
        client.post(
            f"/api/v1/orders/{order.ref}/reorder/",
            {"mode": "replace"},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="bundle-failure",
        )
    assert client.get("/api/v1/storefront/cart/").json()["cart"]["items_count"] == 2
    assert len(calls) == 2


def test_subscription_inventory_is_read_only_and_contains_no_contact_data():
    import io
    import json

    from django.core.management import call_command

    from shopman.storefront.models import StockAlertSubscription

    StockAlertSubscription.objects.create(
        sku="LEGACY",
        contact_phone="+5543999990007",
        target_key="legacy-target",
        evidence_hash="legacy-evidence-active",
    )
    StockAlertSubscription.objects.create(
        sku="LEGACY",
        contact_phone="+5543999990007",
        target_key="legacy-target",
        evidence_hash="legacy-evidence-revoked",
        revoked_at=timezone.now(),
        revoke_reason="legacy_duplicate",
    )
    before = list(StockAlertSubscription.objects.values())
    out = io.StringIO()
    call_command("audit_storefront_subscriptions", stdout=out)
    report = json.loads(out.getvalue())
    assert report["exact_contact_duplicate_groups"] == 0
    assert report["active"] == 0  # legacy rows without verified evidence fail closed
    assert report["mutations"] == 0
    assert "+5543" not in out.getvalue()
    assert list(StockAlertSubscription.objects.values()) == before


def test_draft_context_isolates_identity_strength_and_cart_but_preserves_renewal():
    from types import SimpleNamespace

    from shopman.storefront.identity import checkout_draft_context

    class BrowserSession(dict):
        session_key = "browser-A"

    session = BrowserSession(identity_strength="device")
    request = SimpleNamespace(session=session, customer=SimpleNamespace(uuid="customer-A"))
    first = checkout_draft_context(request, "cart-A")
    session.session_key = "renewed-browser"
    assert checkout_draft_context(request, "cart-A") == first
    request.customer.uuid = "customer-B"
    assert checkout_draft_context(request, "cart-A") != first
    request.customer.uuid = "customer-A"
    session["identity_strength"] = "number"
    assert checkout_draft_context(request, "cart-A") != first
    session["identity_strength"] = "device"
    assert checkout_draft_context(request, "cart-B") != first


def test_cleanup_age_cannot_authorize_repeating_a_bound_intention():
    from datetime import timedelta

    from django.core.management import call_command
    from shopman.orderman.models import IdempotencyKey

    receipt = IdempotencyKey.objects.create(
        scope="local-bound",
        key="retained",
        status="done",
        request_fingerprint="a" * 64,
        response_body={"ok": True},
        expires_at=timezone.now() - timedelta(days=30),
    )
    IdempotencyKey.objects.filter(pk=receipt.pk).update(created_at=timezone.now() - timedelta(days=30))
    call_command("cleanup_idempotency_keys", days=7)
    assert IdempotencyKey.objects.filter(pk=receipt.pk).exists()


def test_expired_indeterminate_bound_receipt_never_repeats_by_age():
    from datetime import timedelta
    from unittest.mock import Mock

    from shopman.orderman.models import IdempotencyKey

    payload = {"qty": 1}
    IdempotencyKey.objects.create(
        scope="uncertain",
        key="retained",
        status="in_progress",
        request_fingerprint=remote_mutations.fingerprint(payload),
        expires_at=timezone.now() - timedelta(days=30),
    )
    effect = Mock()
    with pytest.raises(remote_mutations.RemoteMutationInProgress):
        remote_mutations.run_idempotent_mutation(
            scope="uncertain", key="retained", payload=payload, execute=effect, local_atomic=True
        )
    effect.assert_not_called()
