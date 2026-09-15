from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.shop.models import Channel
from shopman.shop.services import payment

pytestmark = pytest.mark.django_db

EFI_ADAPTERS = {"pix": "shopman.shop.adapters.payment_efi"}
MOCK_ADAPTERS = {"pix": "shopman.shop.adapters.payment_mock"}


def _intent(*, ref: str, gateway: str, status: str = "pending"):
    intent = PaymentService.create_intent(
        order_ref=f"ORD-{ref}",
        amount_q=500,
        method="pix",
        gateway=gateway,
        gateway_data={"provider_environment": "sandbox"} if gateway == "efi" else {},
        ref=ref,
    )
    if status == "captured":
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        intent.refresh_from_db()
    elif status != "pending":
        intent.status = status
        intent.save(update_fields=["status"])
    return intent


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS)
def test_flip_to_efi_keeps_old_mock_intent_on_mock_adapter():
    intent = _intent(ref="PIX-MOCK-OLD", gateway="mock")

    adapter = payment._adapter_for_persisted_intent(intent.ref, method="pix")

    assert adapter.__name__ == "shopman.shop.adapters.payment_mock"


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS)
def test_rollback_to_mock_keeps_old_efi_intent_on_efi_adapter():
    intent = _intent(ref="PIX-EFI-OLD", gateway="efi")

    adapter = payment._adapter_for_persisted_intent(intent.ref, method="pix")

    assert adapter.__name__ == "shopman.shop.adapters.payment_efi"


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS)
def test_orphan_or_unknown_gateway_never_falls_through_to_current_provider():
    unknown = _intent(ref="PIX-UNKNOWN", gateway="custom-provider")

    assert payment._adapter_for_persisted_intent("DOES-NOT-EXIST", method="pix") is None
    assert payment._adapter_for_persisted_intent(unknown.ref, method="pix") is None


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS)
def test_pending_mock_intent_is_not_reused_after_efi_flip_but_captured_fact_is_preserved():
    order = SimpleNamespace(ref="ORD-ROUTE", total_q=500)
    pending = _intent(ref="PIX-PENDING-MOCK", gateway="mock")
    pending.order_ref = order.ref
    pending.save(update_fields=["order_ref"])

    assert payment._existing_active_intent(
        order, method="pix", amount_q=500, gateway="efi",
    ) is None

    PaymentService.authorize(pending.ref)
    PaymentService.capture(pending.ref)
    restored = payment._existing_active_intent(
        order, method="pix", amount_q=500, gateway="efi",
    )
    assert restored is not None
    assert restored.intent_ref == pending.ref


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS)
def test_existing_pending_mock_ref_stops_for_reconciliation_without_calling_either_provider():
    Channel.objects.create(ref="web", name="Web")
    intent = _intent(ref="PIX-MOCK-BOUND", gateway="mock")
    order = Order.objects.create(
        ref=intent.order_ref,
        channel_ref="web",
        total_q=500,
        data={"payment": {"method": "pix", "intent_ref": intent.ref}},
    )

    with (
        patch("shopman.shop.adapters.payment_efi.create_intent") as efi_create,
        patch("shopman.shop.adapters.payment_mock.create_intent") as mock_create,
    ):
        payment.initiate(order)

    efi_create.assert_not_called()
    mock_create.assert_not_called()
    order.refresh_from_db()
    assert "gateway mock" in order.data["payment"]["error"]
    assert order.data["payment"]["intent_ref"] == intent.ref


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS)
def test_cancel_after_flip_calls_gateway_persisted_on_intent():
    Channel.objects.create(ref="web", name="Web")
    intent = _intent(ref="PIX-MOCK-CANCEL", gateway="mock")
    order = Order.objects.create(
        ref=intent.order_ref,
        channel_ref="web",
        total_q=500,
        data={"payment": {"method": "pix", "intent_ref": intent.ref}},
    )
    success = SimpleNamespace(success=True)

    with (
        patch("shopman.shop.adapters.payment_mock.cancel", return_value=success) as mock_cancel,
        patch("shopman.shop.adapters.payment_efi.cancel") as efi_cancel,
    ):
        payment.cancel(order)

    mock_cancel.assert_called_once_with(intent.ref, reason="order_cancelled")
    efi_cancel.assert_not_called()


def test_non_pix_operations_keep_effective_adapter_registry_semantics():
    configured = SimpleNamespace(name="custom-card-adapter")
    with patch.object(payment, "get_adapter", return_value=configured) as resolve:
        adapter = payment._adapter_for_persisted_intent("ORPHAN-CARD", method="card")

    assert adapter is configured
    resolve.assert_called_once_with("payment", method="card")


def test_matching_custom_pix_gateway_uses_effective_adapter():
    intent = _intent(ref="PIX-CUSTOM-MATCH", gateway="custom-provider")
    configured = SimpleNamespace(PAYMENT_GATEWAY="custom-provider")

    with patch.object(payment, "get_adapter", return_value=configured):
        assert payment._adapter_for_persisted_intent(intent.ref, method="pix") is configured


def test_divergent_custom_pix_gateway_remains_fail_safe():
    intent = _intent(ref="PIX-CUSTOM-DIVERGENT", gateway="custom-provider")
    configured = SimpleNamespace(PAYMENT_GATEWAY="another-provider")

    with patch.object(payment, "get_adapter", return_value=configured):
        assert payment._adapter_for_persisted_intent(intent.ref, method="pix") is None


@pytest.mark.parametrize(
    ("persisted_environment", "runtime_sandbox"),
    [("sandbox", False), ("production", True)],
)
def test_efi_environment_flip_fails_closed_without_loading_provider(
    persisted_environment,
    runtime_sandbox,
):
    from shopman.backstage.models import OperatorAlert

    intent = _intent(ref=f"PIX-EFI-ENV-{persisted_environment}", gateway="efi")
    intent.gateway_data = {"provider_environment": persisted_environment}
    intent.save(update_fields=["gateway_data"])

    with (
        override_settings(SHOPMAN_EFI={"sandbox": runtime_sandbox}),
        patch("shopman.shop.services.payment.import_module") as load_provider,
    ):
        adapter = payment._adapter_for_persisted_intent(intent.ref, method="pix")

    assert adapter is None
    load_provider.assert_not_called()
    assert OperatorAlert.objects.filter(
        type="payment_reconciliation_failed",
        order_ref=intent.order_ref,
    ).exists()


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=EFI_ADAPTERS, SHOPMAN_EFI={"sandbox": True})
def test_unmarked_legacy_efi_intent_fails_closed_for_manual_reconciliation():
    from shopman.backstage.models import OperatorAlert

    intent = _intent(ref="PIX-EFI-ENV-UNKNOWN", gateway="efi")
    intent.gateway_data = {}
    intent.save(update_fields=["gateway_data"])

    with patch("shopman.shop.services.payment.import_module") as load_provider:
        adapter = payment._adapter_for_persisted_intent(intent.ref, method="pix")

    assert adapter is None
    load_provider.assert_not_called()
    assert OperatorAlert.objects.filter(
        type="payment_reconciliation_failed",
        order_ref=intent.order_ref,
    ).exists()


def test_stale_efi_pix_is_cancelled_provider_first_then_locally():
    Channel.objects.create(ref="web", name="Web")
    winner = _intent(ref="PIX-WINNER", gateway="efi", status="captured")
    stale = _intent(ref="PIX-STALE-EFI", gateway="efi")
    stale.order_ref = winner.order_ref
    stale.save(update_fields=["order_ref"])
    order = Order.objects.create(ref=winner.order_ref, channel_ref="web", total_q=500, data={})
    success = SimpleNamespace(success=True)

    with patch("shopman.shop.adapters.payment_efi.cancel", return_value=success) as remote_cancel:
        count = payment.cancel_stale_intents(order, keep_intent_ref=winner.ref)

    remote_cancel.assert_called_once_with(stale.ref, reason="superseded_by_captured_payment")
    stale.refresh_from_db()
    assert stale.status == "cancelled"
    assert count == 1


def test_stale_efi_remote_failure_keeps_local_intent_open_and_alerts():
    from shopman.backstage.models import OperatorAlert

    Channel.objects.create(ref="web", name="Web")
    winner = _intent(ref="PIX-WINNER-FAIL", gateway="efi", status="captured")
    stale = _intent(ref="PIX-STALE-EFI-FAIL", gateway="efi")
    stale.order_ref = winner.order_ref
    stale.save(update_fields=["order_ref"])
    order = Order.objects.create(ref=winner.order_ref, channel_ref="web", total_q=500, data={})
    failure = SimpleNamespace(success=False, error_code="gateway_down", message="indisponível")

    with patch("shopman.shop.adapters.payment_efi.cancel", return_value=failure):
        count = payment.cancel_stale_intents(order, keep_intent_ref=winner.ref)

    stale.refresh_from_db()
    assert stale.status == "pending"
    assert count == 0
    assert OperatorAlert.objects.filter(
        type="payment_reconciliation_failed",
        order_ref=order.ref,
    ).exists()


def test_persisting_qr_merges_webhook_fields_from_fresh_order_row():
    from shopman.shop.adapters.payment_types import PaymentIntent as AdapterIntent

    Channel.objects.create(ref="web", name="Web")
    order = Order.objects.create(
        ref="ORD-QR-WEBHOOK-RACE",
        channel_ref="web",
        total_q=500,
        data={
            "payment": {
                "method": "pix",
                "intent_ref": "PAY-RACE",
                "captured_at": "2026-09-15T10:00:00+00:00",
                "e2e_id": "E-RACE",
                "confirmation_mode": "provider_simulated",
                "pix_receipts": {"E-RACE": 500},
            }
        },
    )
    adapter_intent = AdapterIntent(
        intent_ref="PAY-RACE",
        status="captured",
        amount_q=500,
        metadata={"qrcode": "copy-paste", "imagemQrcode": "qr-image"},
    )

    payment._persist_intent(
        order,
        payment_data={"method": "pix", "idempotency_key": "stale-snapshot"},
        method="pix",
        amount_q=500,
        intent=adapter_intent,
    )

    order.refresh_from_db()
    persisted = order.data["payment"]
    assert persisted["captured_at"] == "2026-09-15T10:00:00+00:00"
    assert persisted["e2e_id"] == "E-RACE"
    assert persisted["confirmation_mode"] == "provider_simulated"
    assert persisted["pix_receipts"] == {"E-RACE": 500}
    assert persisted["copy_paste"] == "copy-paste"
    assert persisted["qr_code"] == "qr-image"


def test_persisting_pending_efi_intent_marks_sandbox_order_before_webhook():
    from shopman.backstage.projections.bi_explore import build_bi_explore
    from shopman.shop.adapters.payment_types import PaymentIntent as AdapterIntent

    Channel.objects.create(ref="web", name="Web")
    db_intent = _intent(ref="PIX-PENDING-SANDBOX", gateway="efi")
    db_intent.gateway_data = {
        "provider_environment": "sandbox",
        "confirmation_mode": "provider_simulated",
    }
    db_intent.save(update_fields=["gateway_data"])
    order = Order.objects.create(
        ref=db_intent.order_ref,
        channel_ref="web",
        total_q=500,
        data={"payment": {"method": "pix"}},
    )
    adapter_intent = AdapterIntent(
        intent_ref=db_intent.ref,
        status="pending",
        amount_q=500,
        metadata={"qrcode": "sandbox-copy"},
    )

    payment._persist_intent(
        order,
        payment_data={"method": "pix"},
        method="pix",
        amount_q=500,
        intent=adapter_intent,
    )

    order.refresh_from_db()
    assert order.data["payment"]["confirmation_mode"] == "provider_simulated"
    assert order.data["payment"]["provider_environment"] == "sandbox"
    assert order.data["payment"]["is_test_confirmation"] is True
    assert build_bi_explore(metric="payment_received", by="payment_method").rows == ()


def test_late_initiate_error_cannot_overwrite_concurrent_capture():
    from shopman.backstage.models import OperatorAlert

    Channel.objects.create(ref="web", name="Web")
    intent = _intent(ref="PIX-CAPTURE-WON", gateway="efi", status="captured")
    order = Order.objects.create(
        ref=intent.order_ref,
        channel_ref="web",
        total_q=500,
        data={
            "payment": {
                "method": "pix",
                "intent_ref": intent.ref,
                "captured_at": "2026-09-15T10:00:00+00:00",
                "e2e_id": "E-WON",
                "confirmation_mode": "provider_simulated",
            }
        },
    )

    payment._record_initiate_error(
        order,
        payment_data={"method": "pix", "intent_ref": intent.ref},
        method="pix",
        amount_q=500,
        error="stale GET timeout",
    )

    order.refresh_from_db()
    assert "error" not in order.data["payment"]
    assert order.data["payment"]["captured_at"] == "2026-09-15T10:00:00+00:00"
    assert order.data["payment"]["e2e_id"] == "E-WON"
    assert not OperatorAlert.objects.filter(type="payment_failed", order_ref=order.ref).exists()


def test_late_initiate_error_yields_to_sufficient_receipt_before_payman_capture():
    from shopman.shop.services.pix_confirmation import confirm_pix

    Channel.objects.create(ref="web", name="Web")
    intent = _intent(ref="PIX-RECEIPT-WON", gateway="efi")
    intent.gateway_id = "TXID-RECEIPT-WON"
    intent.gateway_data = {
        "provider_environment": "sandbox",
        "confirmation_mode": "provider_simulated",
    }
    intent.save(update_fields=["gateway_id", "gateway_data"])
    order = Order.objects.create(
        ref=intent.order_ref,
        channel_ref="web",
        total_q=500,
        data={
            "payment": {
                "method": "pix",
                "intent_ref": intent.ref,
                "amount_q": 500,
                "paid_amount_q": 500,
                "pix_receipts": {"E-RECEIPT-WON": 500},
                "pix_receipt_sources": {
                    "E-RECEIPT-WON": {
                        "provider_environment": "sandbox",
                        "confirmation_mode": "provider_simulated",
                        "is_test_confirmation": True,
                    }
                },
                "provider_environment": "sandbox",
                "confirmation_mode": "provider_simulated",
                "is_test_confirmation": True,
            }
        },
    )

    with (
        patch("shopman.shop.services.payment._create_payment_failed_alert") as alert,
        patch("shopman.shop.services.payment._notify_payment_failed") as notify,
    ):
        payment._record_initiate_error(
            order,
            payment_data={"method": "pix", "intent_ref": intent.ref},
            method="pix",
            amount_q=500,
            error="late QR timeout",
        )

    order.refresh_from_db()
    assert "error" not in order.data["payment"]
    assert order.data["payment"]["pix_receipts"] == {"E-RECEIPT-WON": 500}
    assert intent.status == "pending"
    alert.assert_not_called()
    notify.assert_not_called()

    # Defensive cleanup in the capture claim also removes an older retry error.
    data = dict(order.data)
    data["payment"] = {**data["payment"], "error": "older retry error"}
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    with patch("shopman.shop.lifecycle.dispatch"):
        confirm_pix(txid=intent.gateway_id, e2e_id="E-RECEIPT-WON", amount="5.00")

    order.refresh_from_db()
    intent.refresh_from_db()
    assert intent.status == "captured"
    assert order.data["payment"]["captured_at"]
    assert "error" not in order.data["payment"]
    assert order.data["payment"]["confirmation_mode"] == "provider_simulated"
