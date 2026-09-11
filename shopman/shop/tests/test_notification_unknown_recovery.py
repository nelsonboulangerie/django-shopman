"""Unknown remote delivery is not permission to send through another backend."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.notification import NotificationSendHandler
from shopman.shop.models import Shop
from shopman.shop.services import notification


@pytest.fixture
def context(db, monkeypatch):
    Shop.objects.create(name="Synthetic notification uncertainty lab")
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *args: None)
    order = Order.objects.create(ref="NOTICE-UNKNOWN", status="ready", total_q=1500,
        data={"fulfillment_type": "pickup", "payment": {"method": "cash"}})
    monkeypatch.setattr(notification, "_resolve_backend_chain", lambda order: ["first", "second"])
    monkeypatch.setattr(notification, "_filter_backend_chain", lambda order, chain, **kwargs: chain)
    monkeypatch.setattr(notification, "_resolve_recipient", lambda order, backend: "synthetic-recipient")
    monkeypatch.setattr(notification, "_build_context", lambda *args: {})
    return order


def test_remote_acceptance_then_lost_response_does_not_send_via_fallback(context, monkeypatch):
    accepted = []
    def first(**kwargs):
        accepted.append("first")
        raise TimeoutError("synthetic response lost after acceptance")
    def second(**kwargs):
        accepted.append("second")
        return True
    backends = {"first": SimpleNamespace(send=first), "second": SimpleNamespace(send=second)}
    monkeypatch.setattr("shopman.shop.notifications.get_backend", lambda name: backends[name])
    payload = {"order_ref": context.ref}
    success, error = notification.deliver_order_notification(context, "order_ready", payload)
    assert accepted == ["first"]
    assert success is False
    assert payload["notification_delivery"]["status"] == "unknown"


@pytest.mark.django_db(transaction=True)
def test_crash_after_remote_acceptance_fences_worker_replay(context, monkeypatch):
    accepted = []
    def crash(*args):
        accepted.append("accepted remotely")
        raise SystemExit(17)
    monkeypatch.setattr(notification, "deliver_order_notification", crash)
    task = Directive.objects.create(topic=notification.TOPIC, attempts=1, payload={"order_ref": context.ref, "template": "order_ready"})
    with pytest.raises(SystemExit) as exit_:
        NotificationSendHandler().handle(message=task, ctx={})
    assert exit_.value.code == 17
    task.refresh_from_db()
    assert task.payload["notification_delivery"]["status"] == "started"
    from shopman.orderman.exceptions import DirectiveTerminalError
    with pytest.raises(DirectiveTerminalError):
        NotificationSendHandler().handle(message=task, ctx={})
    assert accepted == ["accepted remotely"]


def test_explicit_rejection_keeps_the_existing_fallback_chain(context, monkeypatch):
    first = Mock(return_value={"success": False, "error": "explicit rejection"})
    second = Mock(return_value=True)
    backends = {"first": SimpleNamespace(send=first), "second": SimpleNamespace(send=second)}
    monkeypatch.setattr("shopman.shop.notifications.get_backend", lambda name: backends[name])
    success, _ = notification.deliver_order_notification(context, "order_ready", {"order_ref": context.ref})
    assert success is True
    first.assert_called_once()
    second.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_concurrent_worker_cannot_repeat_external_effect(context, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import connections
    from shopman.orderman.exceptions import DirectiveTerminalError

    entered, release = Event(), Event()
    effects = []
    def deliver(order, template, payload):
        assert not connections["default"].in_atomic_block
        effects.append(order.ref)
        entered.set()
        assert release.wait(5)
        notification._record_delivery(payload, status="accepted", backend="synthetic", message_id="remote-1")
        return True, None
    monkeypatch.setattr(notification, "deliver_order_notification", deliver)
    task = Directive.objects.create(topic=notification.TOPIC, attempts=1,
        payload={"order_ref": context.ref, "template": "order_ready"})
    def worker():
        try:
            NotificationSendHandler().handle(message=Directive.objects.get(pk=task.pk), ctx={})
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker)
        try:
            assert entered.wait(5)
            with pytest.raises(DirectiveTerminalError):
                NotificationSendHandler().handle(message=task, ctx={})
        finally:
            release.set()
        future.result(timeout=5)
    task.refresh_from_db()
    assert task.payload["notification_delivery"]["status"] == "accepted"
    NotificationSendHandler().handle(message=task, ctx={})
    assert effects == [context.ref]


def test_unknown_blocks_new_resend_and_explains_payment_link(context):
    from shopman.backstage.projections.order_queue import payment_link_notice

    context.data["payment"] = {"method": "link", "checkout_url": "https://synthetic.invalid/pay"}
    task = Directive.objects.create(topic=notification.TOPIC, status="failed",
        payload={"order_ref": context.ref, "template": notification.PAYMENT_LINK_TEMPLATE,
                 "notification_delivery": {"status": "unknown"}})
    with pytest.raises(notification.NotificationResendRefused) as refusal:
        notification.resend(context, notification.PAYMENT_LINK_TEMPLATE, min_interval_seconds=0)
    assert refusal.value.code == "notification_acceptance_unknown"
    assert notification.payment_link_resend_refusal(context).code == refusal.value.code
    assert "não confirmado" in payment_link_notice(context)
    assert Directive.objects.filter(pk=task.pk).count() == 1


@pytest.mark.parametrize("adapter_name", ["whatsapp", "manychat"])
def test_http_transport_uncertainty_survives_adapter_boundary(adapter_name, monkeypatch):
    from importlib import import_module
    from urllib.error import URLError

    adapter = import_module(f"shopman.shop.adapters.notification_{adapter_name}")
    monkeypatch.setattr(adapter, "urlopen", Mock(side_effect=URLError("SECRET synthetic accepted then lost")))
    if adapter_name == "whatsapp":
        result = adapter._api_call({}, {"PHONE_NUMBER_ID": "synthetic", "ACCESS_TOKEN": "synthetic"})
    else:
        result = adapter._api_call("/sending/sendContent", {}, {"api_token": "synthetic"})
    assert result["outcome_unknown"] is True
    assert "SECRET" not in str(result)


@pytest.mark.django_db(transaction=True)
def test_legacy_attempt_without_proof_is_not_retried(context, monkeypatch):
    from shopman.orderman.exceptions import DirectiveTerminalError

    deliver = Mock()
    monkeypatch.setattr(notification, "deliver_order_notification", deliver)
    task = Directive.objects.create(topic=notification.TOPIC, attempts=2,
        payload={"order_ref": context.ref, "template": "order_ready"})
    with pytest.raises(DirectiveTerminalError):
        NotificationSendHandler().handle(message=task, ctx={})
    deliver.assert_not_called()


def test_legacy_failed_notice_does_not_authorize_a_new_key(context):
    Directive.objects.create(topic=notification.TOPIC, status="failed", attempts=5,
        payload={"order_ref": context.ref, "template": "order_ready"})
    with pytest.raises(notification.NotificationResendRefused) as refusal:
        notification.resend(context, "order_ready", min_interval_seconds=0)
    assert refusal.value.code == "notification_acceptance_unknown"


@pytest.mark.parametrize("count,accepted", [(0, False), (1, True)])
def test_email_acceptance_requires_a_sent_message(context, monkeypatch, count, accepted):
    from shopman.shop.adapters import notification_email

    monkeypatch.setattr(notification_email, "send_mail", Mock(return_value=count))
    assert notification_email.send("synthetic@example.invalid", "order_ready", {}) is accepted
