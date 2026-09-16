from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import requests
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from pywebpush import WebPushException
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.handlers.notification_push import NotificationPushHandler
from shopman.shop.models import PushSubscription, UserNotification
from shopman.shop.services.user_notifications import push_user_notification

pytestmark = pytest.mark.django_db

VAPID = override_settings(
    VAPID_PRIVATE_KEY="private-key-long-enough-for-tests-123456",
    VAPID_PUBLIC_KEY="public-key-long-enough-for-tests-1234567",
    VAPID_CLAIMS_EMAIL="ops@example.com",
    VAPID_TIMEOUT_SECONDS=7,
)
User = get_user_model()


@pytest.fixture
def owner():
    return User.objects.create_user(username="push-handler-owner", password="x", is_staff=True)


@pytest.fixture
def notification(owner):
    return UserNotification.objects.create(
        user=owner,
        category="campaign",
        severity="warning",
        title="Revisar anúncio",
        message="Fale com ana@example.com ou 11 99999-0000; custa R$ 42,00.",
        action_url="/announcements/7#review",
    )


@pytest.fixture
def subscription(owner):
    return PushSubscription.objects.create(
        user=owner,
        endpoint="https://push.example.test/device",
        p256dh="device-public-key",
        auth="device-auth",
        surface_ref="hub",
        device_label="iPhone",
        categories=["campaign", "order", "report"],
    )


def _directive(notification, **payload):
    return Directive.objects.create(
        topic="notification.push",
        payload={"notification_id": notification.pk, **payload},
    )


@VAPID
def test_handler_delivers_redacted_payload_and_records_success(notification, subscription):
    directive = _directive(notification)

    with patch("shopman.shop.handlers.notification_push.webpush") as webpush:
        NotificationPushHandler().handle(directive)

    call = webpush.call_args.kwargs
    payload = json.loads(call["data"])
    assert payload["action_url"] == "/announcements/7#review"
    assert payload["body"] == "Fale com [email] ou [telefone]; custa [valor]."
    assert "ana@example.com" not in call["data"]
    assert call["ttl"] == 3600
    assert call["headers"] == {"Urgency": "normal"}
    assert call["timeout"] == 7
    subscription.refresh_from_db()
    assert subscription.last_success_at is not None
    assert subscription.failures == 0


@VAPID
def test_financial_payload_is_title_only_and_unsafe_url_is_removed(owner, subscription):
    notification = UserNotification.objects.create(
        user=owner,
        category="order",
        severity="critical",
        title="Pedido precisa de ação",
        message="CPF 123.456.789-01, R$ 999,00",
        action_url="https://evil.example/steal",
    )
    directive = _directive(notification)

    with patch("shopman.shop.handlers.notification_push.webpush") as webpush:
        NotificationPushHandler().handle(directive)

    payload = json.loads(webpush.call_args.kwargs["data"])
    assert payload["body"] == ""
    assert payload["action_url"] == "/"
    assert webpush.call_args.kwargs["headers"] == {"Urgency": "high"}


@VAPID
@override_settings(SHOPMAN_MARKETING_BASE_URL="https://mkt.example.test")
def test_category_link_targets_its_configured_surface(notification, subscription):
    with patch("shopman.shop.handlers.notification_push.webpush") as webpush:
        NotificationPushHandler().handle(_directive(notification))
    payload = json.loads(webpush.call_args.kwargs["data"])
    assert payload["action_url"] == "https://mkt.example.test/announcements/7#review"


@VAPID
@pytest.mark.parametrize("status_code", [404, 410])
def test_gone_endpoint_is_disabled(notification, subscription, status_code):
    response = requests.Response()
    response.status_code = status_code
    with patch(
        "shopman.shop.handlers.notification_push.webpush",
        side_effect=WebPushException("gone", response=response),
    ):
        NotificationPushHandler().handle(_directive(notification))
    subscription.refresh_from_db()
    assert subscription.disabled_at is not None
    assert subscription.failures == 1


@VAPID
@pytest.mark.parametrize(
    "error",
    [
        WebPushException("busy", response=type("Response", (), {"status_code": 503})()),
        requests.ConnectionError("offline"),
    ],
)
def test_transient_transport_failure_requests_retry(notification, subscription, error):
    with patch("shopman.shop.handlers.notification_push.webpush", side_effect=error):
        with pytest.raises(DirectiveTransientError):
            NotificationPushHandler().handle(_directive(notification))
    subscription.refresh_from_db()
    assert subscription.failures == 1
    assert subscription.disabled_at is None


@VAPID
def test_irrelevant_subscription_and_duplicate_delivery_are_skipped(notification, subscription):
    subscription.categories = ["order"]
    subscription.save(update_fields=["categories"])
    with patch("shopman.shop.handlers.notification_push.webpush") as webpush:
        NotificationPushHandler().handle(_directive(notification))
        webpush.assert_not_called()

    subscription.categories = ["campaign"]
    duplicate = _directive(notification)
    subscription.last_success_at = timezone.now()
    subscription.save(update_fields=["categories", "last_success_at"])
    with patch("shopman.shop.handlers.notification_push.webpush") as webpush:
        NotificationPushHandler().handle(duplicate)
        webpush.assert_not_called()


def test_missing_vapid_is_terminal(notification, subscription):
    with override_settings(VAPID_PRIVATE_KEY="", VAPID_PUBLIC_KEY="", VAPID_CLAIMS_EMAIL=""):
        with pytest.raises(DirectiveTerminalError, match="VAPID"):
            NotificationPushHandler().handle(_directive(notification))


def test_invalid_payload_is_terminal():
    directive = Directive.objects.create(topic="notification.push", payload={})
    with pytest.raises(DirectiveTerminalError, match="notification_id"):
        NotificationPushHandler().handle(directive)


@VAPID
def test_service_keeps_sse_and_creates_one_persistent_push_directive(
    notification, subscription
):
    with patch("django_eventstream.send_event") as send_event:
        push_user_notification(notification)
        push_user_notification(notification)

    assert send_event.call_count == 2
    directives = Directive.objects.filter(topic="notification.push")
    assert directives.count() == 1
    assert directives.get().payload == {
        "notification_id": notification.pk,
        "notification_version": notification.version,
    }


def test_service_without_vapid_keeps_sse_but_does_not_enqueue(notification, subscription):
    with override_settings(VAPID_PRIVATE_KEY="", VAPID_PUBLIC_KEY="", VAPID_CLAIMS_EMAIL=""):
        with patch("django_eventstream.send_event") as send_event:
            push_user_notification(notification)
    send_event.assert_called_once()
    assert not Directive.objects.filter(topic="notification.push").exists()
