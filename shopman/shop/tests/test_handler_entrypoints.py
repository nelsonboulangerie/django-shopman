"""Direct behavioral contracts for small orchestration entrypoints."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive

from shopman.shop import directives
from shopman.shop.handlers import (
    alert_resolution,
    cancellation_requests,
    catalog_projection,
    kds_alerts,
    production_alerts,
)
from shopman.shop.handlers._resilient import resilient_receiver
from shopman.shop.handlers.accounting import PurchaseToPayableHandler
from shopman.shop.handlers.campaign import (
    AnnouncementHandler,
    AnnouncementNotifyHandler,
    CampaignOccurrenceHandler,
)
from shopman.shop.handlers.card_authorization import CardAuthorizationWatchHandler
from shopman.shop.handlers.catalog_projection import CatalogProjectHandler
from shopman.shop.handlers.confirmation import (
    ConfirmationTimeoutHandler,
    StaleNewOrderAlertHandler,
)
from shopman.shop.handlers.delivery_auto_complete import DeliveryAutoCompleteHandler
from shopman.shop.handlers.fulfillment import (
    FulfillmentCreateHandler,
    FulfillmentUpdateHandler,
)
from shopman.shop.handlers.handoff_commit import HandoffCommitHandler
from shopman.shop.handlers.kds_alerts import KDSTicketLateHandler
from shopman.shop.handlers.lifecycle_phase import LifecyclePhaseHandler
from shopman.shop.handlers.loyalty import LoyaltyEarnHandler, LoyaltyRevokeHandler
from shopman.shop.handlers.payment_refund import PaymentRefundHandler
from shopman.shop.handlers.payment_timeout import PaymentTimeoutHandler
from shopman.shop.handlers.preorder import PreorderActivateHandler
from shopman.shop.handlers.pricing import SessionTotalModifier

pytestmark = pytest.mark.django_db


def test_purchase_to_payable_handler_persists_the_created_entry_receipt():
    backend = MagicMock()
    backend.list_entries.return_value = []
    backend.create_payable.return_value = SimpleNamespace(
        success=True,
        entry_id="payable-42",
        error_message="",
    )
    message = MagicMock()
    message.payload = {
        "description": "Farinha",
        "amount_q": 12_500,
        "due_date": "2026-10-31",
        "category": "supplies",
        "supplier_name": "Moinho",
        "reference": "purchase:42",
        "notes": "NF 42",
    }

    PurchaseToPayableHandler(backend).handle(message=message, ctx={})

    backend.create_payable.assert_called_once_with(
        description="Farinha",
        amount_q=12_500,
        due_date=date(2026, 10, 31),
        category="supplies",
        supplier_name="Moinho",
        reference="purchase:42",
        notes="NF 42",
    )
    assert message.payload["entry_id"] == "payable-42"
    message.save.assert_called_once_with(update_fields=["payload", "updated_at"])


def test_delivery_auto_complete_handler_confirms_the_due_order_once():
    order = MagicMock()
    message = SimpleNamespace(payload={"order_ref": "ORD-AUTO-42"})

    with (
        patch("shopman.orderman.models.Order.objects.get", return_value=order),
        patch("shopman.shop.services.operator_orders.confirm_received") as confirm,
    ):
        DeliveryAutoCompleteHandler().handle(message=message, ctx={})

    confirm.assert_called_once_with(order, actor="delivery.auto_complete")


def test_fulfillment_create_handler_delegates_the_canonical_order():
    order = MagicMock()
    message = SimpleNamespace(payload={"order_ref": "ORD-FUL-42", "channel_ref": "web"})

    with (
        patch("shopman.orderman.models.Order.objects.get", return_value=order),
        patch("shopman.shop.services.fulfillment.create") as create,
    ):
        FulfillmentCreateHandler().handle(message=message, ctx={})

    create.assert_called_once_with(order)


def test_fulfillment_update_handler_updates_syncs_and_notifies():
    order = MagicMock(channel_ref="web")
    fulfillment = MagicMock(status="pending")
    message = SimpleNamespace(
        payload={
            "order_ref": "ORD-FUL-42",
            "fulfillment_id": 42,
            "new_status": "dispatched",
            "tracking_code": "TRACK-42",
            "carrier": "TaOn",
        }
    )
    handler = FulfillmentUpdateHandler()
    locked_orders = MagicMock()
    locked_orders.get.return_value = order
    locked_fulfillments = MagicMock()
    locked_fulfillments.get.return_value = fulfillment
    config = SimpleNamespace(fulfillment=SimpleNamespace(auto_sync=True))

    with (
        patch("shopman.orderman.models.Order.objects.select_for_update", return_value=locked_orders),
        patch(
            "shopman.orderman.models.Fulfillment.objects.select_for_update",
            return_value=locked_fulfillments,
        ),
        patch("shopman.shop.services.fulfillment.update") as update,
        patch("shopman.shop.config.ChannelConfig.for_channel", return_value=config),
        patch.object(handler, "_sync_order_status") as sync,
        patch.object(handler, "_create_notifications") as notify,
    ):
        handler.handle(message=message, ctx={})

    update.assert_called_once_with(fulfillment, "dispatched", "TRACK-42", "TaOn")
    sync.assert_called_once_with(order, "dispatched")
    notify.assert_called_once_with(order, fulfillment, "dispatched")


def test_session_total_modifier_recomputes_the_final_total_without_erasing_pricing():
    session = SimpleNamespace(
        items=[{"line_total_q": 1_250}, {"line_total_q": 750}, {"sku": "SEM-PRECO"}],
        pricing={"manual_discount": {"total_discount_q": 50}},
    )

    SessionTotalModifier().apply(channel=SimpleNamespace(), session=session, ctx={})

    assert session.pricing == {
        "manual_discount": {"total_discount_q": 50},
        "total_q": 2_000,
        "items_count": 3,
    }


def test_directive_queue_carries_the_order_identity_and_explicit_payload():
    order = SimpleNamespace(ref="ORD-QUEUE-42", channel_ref="web")

    queued = directives.queue(
        directives.NOTIFICATION_SEND,
        order,
        template="order_ready",
        context={"source": "direct-test"},
    )

    assert Directive.objects.get(pk=queued.pk).payload == {
        "order_ref": "ORD-QUEUE-42",
        "channel_ref": "web",
        "template": "order_ready",
        "context": {"source": "direct-test"},
    }


def test_alert_resolution_resolves_each_requested_alert_independently():
    with patch("shopman.shop.adapters.alert.resolve") as resolve:
        alert_resolution.resolve("ORD-ALERT-42", ["first", "second"], actor="test")

    assert resolve.call_count == 2


def test_announcement_handler_accepts_a_durable_delivery():
    message = SimpleNamespace(payload={"outbox_ref": "OUT-42"})
    with patch("shopman.shop.handlers.campaign._stage_durable_delivery", return_value=True):
        AnnouncementHandler().handle(message=message, ctx={})


def test_campaign_occurrence_handler_rejects_an_incomplete_occurrence():
    CampaignOccurrenceHandler().handle(
        message=SimpleNamespace(payload={}, pk=42),
        ctx={},
    )


def test_announcement_notify_handler_accepts_a_durable_delivery():
    message = SimpleNamespace(payload={"outbox_ref": "OUT-42"})
    with patch("shopman.shop.handlers.campaign._stage_durable_delivery", return_value=True):
        AnnouncementNotifyHandler().handle(message=message, ctx={})


def test_cancellation_receiver_ignores_non_terminal_status_changes():
    cancellation_requests.on_order_changed(
        sender=object(),
        order=SimpleNamespace(status="accepted", ref="ORD-42"),
        event_type="status_changed",
        actor="operator",
    )


def test_card_authorization_watch_ignores_a_missing_order():
    CardAuthorizationWatchHandler().handle(
        message=SimpleNamespace(payload={}),
        ctx={},
    )


def test_catalog_project_handler_skips_when_no_backend_is_configured():
    handler = CatalogProjectHandler()
    with patch.object(handler, "_resolve_backend", return_value=None):
        handler.handle(
            message=SimpleNamespace(payload={"sku": "SKU-42", "listing_ref": "ifood"}),
            ctx={},
        )


def test_catalog_enqueue_project_delegates_the_public_request():
    expected = object()
    with patch.object(catalog_projection, "_enqueue_project", return_value=expected) as enqueue:
        result = catalog_projection.enqueue_project("SKU-42", "ifood", trigger="manual")

    assert result is expected
    enqueue.assert_called_once_with("SKU-42", "ifood", trigger="manual", extra={})


def test_confirmation_timeout_reschedules_before_expiry():
    expires_at = timezone.now() + timedelta(minutes=5)
    message = MagicMock(
        payload={
            "order_ref": "ORD-42",
            "action": "confirm",
            "expires_at": expires_at.isoformat(),
        }
    )

    ConfirmationTimeoutHandler().handle(message=message, ctx={})

    assert message.status == "queued"
    assert message.available_at == expires_at


def test_stale_new_alert_reschedules_before_alert_time():
    alert_at = timezone.now() + timedelta(minutes=5)
    message = MagicMock(payload={"order_ref": "ORD-42", "alert_at": alert_at.isoformat()})

    StaleNewOrderAlertHandler().handle(message=message, ctx={})

    assert message.status == "queued"
    assert message.available_at == alert_at


def test_kds_receiver_registers_its_reaction_after_commit():
    ticket = SimpleNamespace(pk=42, status="pending")
    with patch("shopman.shop.handlers.kds_alerts.transaction.on_commit") as on_commit:
        kds_alerts.on_ticket_saved(sender=object(), instance=ticket, created=True)

    on_commit.assert_called_once()


def test_kds_late_handler_ignores_an_invalid_ticket_identity():
    KDSTicketLateHandler().handle(
        message=SimpleNamespace(payload={"ticket_pk": "42"}),
        ctx={},
    )


def test_loyalty_earn_requires_an_order_reference():
    with pytest.raises(DirectiveTerminalError, match="missing order_ref"):
        LoyaltyEarnHandler().handle(message=SimpleNamespace(payload={}), ctx={})


def test_loyalty_revoke_requires_an_order_reference():
    with pytest.raises(DirectiveTerminalError, match="missing order_ref"):
        LoyaltyRevokeHandler().handle(message=SimpleNamespace(payload={}), ctx={})


def test_payment_refund_requires_an_order_reference():
    with pytest.raises(DirectiveTerminalError, match="missing order_ref"):
        PaymentRefundHandler().handle(message=SimpleNamespace(payload={}), ctx={})


def test_payment_timeout_ignores_a_missing_order_reference():
    PaymentTimeoutHandler().handle(message=SimpleNamespace(payload={}), ctx={})


def test_preorder_activation_ignores_a_missing_order_reference():
    PreorderActivateHandler().handle(message=SimpleNamespace(payload={}), ctx={})


def test_handoff_commit_handler_delegates_the_pending_handoff_identity():
    message = SimpleNamespace(payload={"order_ref": "ORD-42", "token": "hold-42"})

    with patch("shopman.shop.services.order_undo.commit_handoff") as commit_handoff:
        HandoffCommitHandler().handle(message=message, ctx={})

    commit_handoff.assert_called_once_with("ORD-42", "hold-42")


def test_lifecycle_phase_handler_rejects_an_unknown_phase():
    message = SimpleNamespace(payload={"order_ref": "ORD-42", "phase": "unknown"})

    with pytest.raises(DirectiveTerminalError, match="Unsupported lifecycle phase"):
        LifecyclePhaseHandler().handle(message=message, ctx={})


def test_production_change_receiver_runs_each_lifecycle_concern():
    work_order = SimpleNamespace()
    with (
        patch.object(production_alerts, "ensure_late_check_scheduled") as schedule,
        patch.object(production_alerts, "_resolve_obsolete_alerts") as resolve,
        patch.object(production_alerts, "maybe_create_low_yield_alert") as low_yield,
        patch.object(production_alerts, "notify_quality_reviewers") as notify,
    ):
        production_alerts.on_production_changed(
            sender=object(),
            product_ref="SKU-42",
            date=date(2026, 10, 17),
            action="finished",
            work_order=work_order,
        )

    schedule.assert_called_once_with()
    resolve.assert_called_once_with("finished", work_order)
    low_yield.assert_called_once_with(work_order)
    notify.assert_called_once_with(work_order)


def test_production_stock_shortfall_receiver_delegates_the_alert():
    work_order = SimpleNamespace(ref="WO-42", output_sku="SKU-42")
    shortfalls = [{"sku": "FLOUR", "missing": "2"}]
    with patch.object(production_alerts, "create_stock_shortfall_alert") as create:
        production_alerts.on_production_stock_shortfall(
            sender=object(),
            work_order=work_order,
            shortfalls=shortfalls,
        )

    create.assert_called_once_with(
        work_order_ref="WO-42",
        output_sku="SKU-42",
        shortfalls=shortfalls,
    )


def test_batch_traceability_alert_deduplicates_recent_alerts():
    with (
        patch.object(production_alerts, "_recent_exists", return_value=True),
        patch.object(production_alerts.alert_adapter, "create") as create,
    ):
        production_alerts.create_batch_traceability_alert(
            work_order_ref="WO-42",
            output_sku="SKU-42",
            error="missing lot",
        )

    create.assert_not_called()


def test_resilient_receiver_preserves_the_signal_chain_after_failure():
    def failing_receiver():
        raise RuntimeError("boom")

    wrapped = resilient_receiver(failing_receiver)

    assert wrapped() is None
