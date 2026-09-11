"""MKT-030 — ManyChat-only and fail-closed persistent-field isolation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.test import override_settings

from shopman.shop import notifications
from shopman.shop.adapters import notification_manychat
from shopman.shop.services import manychat_marketing_safety
from shopman.shop.services.marketing_contracts import MarketingContractError


def test_default_safety_is_an_explicit_non_retryable_block():
    state = manychat_marketing_safety.safety_state()

    assert state.safe is False
    assert state.state == "blocked_unverified"
    assert state.reason_code == "manychat_custom_fields_unverified"
    assert "sandbox" in state.action
    with pytest.raises(MarketingContractError) as caught:
        manychat_marketing_safety.require_safe_delivery()
    assert caught.value.code == state.reason_code
    assert caught.value.retryable is False


@override_settings(DEBUG=False)
def test_two_concurrent_marketing_flows_make_zero_provider_calls(monkeypatch):
    provider_calls = []
    monkeypatch.setattr(
        notification_manychat,
        "_get_config",
        lambda: {"api_token": "synthetic-token", "flow_map": {}},
    )
    monkeypatch.setattr(
        notification_manychat,
        "_resolve_subscriber",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("subscriber resolution crossed the safety boundary")
        ),
    )
    monkeypatch.setattr(
        notification_manychat,
        "_api_call",
        lambda *args, **kwargs: provider_calls.append((args, kwargs)),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(
            lambda product: notification_manychat.send(
                "+5543999990001",
                "announcement_published",
                {"product_name": product},
            ),
            ("Croissant", "Baguete"),
        ))

    assert results == (False, False)
    assert provider_calls == []


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_server_marked_max_one_sandbox_probe_can_collect_future_evidence(
    monkeypatch,
):
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="announcement_published",
        subject="x",
        body="y",
        whatsapp_flow_ns="content_sandbox_only",
    )
    calls = []
    monkeypatch.setattr(
        notification_manychat,
        "_get_config",
        lambda: {"api_token": "synthetic-token", "flow_map": {}},
    )
    monkeypatch.setattr(
        notification_manychat,
        "_resolve_subscriber",
        lambda *args, **kwargs: "synthetic-subscriber",
    )
    monkeypatch.setattr(
        notification_manychat,
        "_api_call",
        lambda endpoint, payload, config: calls.append((endpoint, payload))
        or {"success": True},
    )
    context = manychat_marketing_safety.sandbox_probe_context({
        "product_name": "Croissant sintético",
    })

    assert notification_manychat.send(
        "synthetic-recipient",
        "announcement_published",
        context,
    ) is True

    assert calls[-1][0] == "/sending/sendFlow"
    assert all(
        manychat_marketing_safety._SANDBOX_MARKER_KEY not in payload
        for _endpoint, payload in calls
    )


def test_notification_boundary_never_fabricates_receipt_or_logs_recipient(
    monkeypatch, caplog
):
    class Accepted:
        @staticmethod
        def send(**kwargs):
            return True

    recipient = "+5543999994321"
    monkeypatch.setattr(notifications, "_adapters", {"manychat": Accepted()})

    result = notifications.notify(
        event="order_accepted",
        recipient=recipient,
        context={},
        backend="manychat",
    )

    assert result.success is True
    assert result.message_id is None
    assert recipient not in caplog.text


def test_notification_exception_is_redacted_from_result_and_log(monkeypatch, caplog):
    recipient = "+5543999998765"

    class Explodes:
        @staticmethod
        def send(**kwargs):
            raise RuntimeError(f"vendor leaked {recipient}")

    monkeypatch.setattr(notifications, "_adapters", {"manychat": Explodes()})

    result = notifications.notify(
        event="order_accepted",
        recipient=recipient,
        context={},
        backend="manychat",
    )

    assert result.error == "notification_adapter_error"
    assert result.outcome_unknown is True
    assert recipient not in caplog.text
    assert "vendor leaked" not in caplog.text
