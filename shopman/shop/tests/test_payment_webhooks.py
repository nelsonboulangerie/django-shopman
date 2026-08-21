"""
Tests for payment webhooks — Stripe and EFI/PIX.

Covers:
- Stripe happy path (payment_intent.succeeded → order confirmed)
- EFI/PIX happy path (pix notification → order confirmed)
- Idempotency (duplicate webhook = single state change)
- Race condition (payment after cancellation → graceful handling)
- Invalid signature → 400
- Order not found → graceful ignore
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import IdempotencyKey, Order, Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.services.modify import ModifyService
from shopman.payman import PaymentService, PaymentTransaction

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Channel

STRIPE_SETTINGS = {
    "SECRET_KEY": "sk_test_fake",
    "WEBHOOK_SECRET": "whsec_test_fake",
    "CAPTURE_METHOD": "automatic",
}

EFI_WEBHOOK_SETTINGS = {
    "webhook_token": "test-efi-token",
}


def _create_order_with_payment(channel_ref: str = "web", payment_method: str = "card") -> Order:
    """Helper: create a committed order with a payment intent."""
    session_key = generate_session_key()
    Session.objects.create(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
        pricing_policy="fixed",
        edit_policy="open",
        handle_type="guest",
        handle_ref="test-guest",
        data={"origin_channel": "web"},
    )
    ModifyService.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[
            {"op": "add_line", "sku": "TEST-SKU", "qty": 1, "unit_price_q": 1000},
            {"op": "set_data", "path": "payment.method", "value": payment_method},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
        ctx={"actor": "test"},
    )
    result = CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=generate_idempotency_key(),
        ctx={"actor": "test"},
    )
    return Order.objects.get(ref=result.order_ref)


def _create_pix_intent(order: Order) -> object:
    """Create a PIX PaymentIntent attached to the order."""
    intent = PaymentService.create_intent(
        order_ref=order.ref,
        amount_q=order.total_q,
        method="pix",
        gateway="efi",
        gateway_data={},
    )
    intent.gateway_id = "txid_test_abc123"
    intent.save(update_fields=["gateway_id"])
    # Link intent to order
    order.data.setdefault("payment", {})["intent_ref"] = intent.ref
    order.save(update_fields=["data", "updated_at"])
    return intent


def _create_card_intent(order: Order, stripe_pi_id: str = "pi_test_stripe_abc") -> object:
    """Create a card PaymentIntent attached to the order."""
    intent = PaymentService.create_intent(
        order_ref=order.ref,
        amount_q=order.total_q,
        method="card",
        gateway="stripe",
        gateway_data={},
    )
    intent.gateway_id = stripe_pi_id
    intent.save(update_fields=["gateway_id"])
    order.data.setdefault("payment", {})["intent_ref"] = intent.ref
    order.save(update_fields=["data", "updated_at"])
    return intent


class _StripeObjectMetadata:
    """Minimal StripeObject-like metadata mapping without a .get() method."""

    def __init__(self, **values: str) -> None:
        self._values = values

    def __getitem__(self, key: str) -> str:
        return self._values[key]

    def __bool__(self) -> bool:
        return bool(self._values)


# ══════════════════════════════════════════════════════════════
# Fixtures / setUp helpers
# ══════════════════════════════════════════════════════════════


class WebhookTestBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.web_channel = Channel.objects.create(
            ref="web",
            name="Web",
            is_active=True,
        )


# ══════════════════════════════════════════════════════════════
# Stripe Webhook Tests
# ══════════════════════════════════════════════════════════════


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
class StripeWebhookTests(WebhookTestBase):
    """Tests for /api/webhooks/stripe/."""

    URL = "/api/webhooks/stripe/"

    def _make_event(self, event_type: str, stripe_pi_id: str, shopman_ref: str) -> dict:
        """Build a minimal Stripe webhook event payload."""
        return {
            "type": event_type,
            "data": {
                "object": {
                    "id": stripe_pi_id,
                    "object": "payment_intent",
                    "status": "succeeded",
                    "amount": 1000,
                    "currency": "brl",
                    "metadata": {
                        "shopman_ref": shopman_ref,
                        "order_ref": "ORD-TEST",
                    },
                    "last_payment_error": None,
                }
            },
        }

    def _post_webhook(self, event: dict, sig: str = "valid-sig") -> object:
        payload = json.dumps(event).encode()
        return self.client.post(
            self.URL,
            data=payload,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE=sig,
        )

    def _mock_stripe_construct(self, event_dict: dict):
        """Return a mock Stripe Event object matching event_dict."""
        mock_event = MagicMock()
        mock_event.type = event_dict["type"]
        obj = event_dict["data"]["object"]
        mock_pi = MagicMock()
        mock_pi.id = obj["id"]
        mock_pi.status = obj["status"]
        mock_pi.metadata = obj["metadata"]
        mock_pi.last_payment_error = obj.get("last_payment_error")
        mock_event.data.object = mock_pi
        return mock_event

    def _mock_charge_refunded_event(
        self,
        *,
        event_id: str,
        stripe_pi_id: str,
        amount_q: int,
        amount_refunded_q: int,
        charge_id: str = "ch_test_refund",
    ):
        """Return a Stripe charge.refunded event.

        Stripe's amount_refunded is cumulative, not the delta for this event.
        """
        mock_event = MagicMock()
        mock_event.id = event_id
        mock_event.type = "charge.refunded"
        charge = MagicMock()
        charge.id = charge_id
        charge.payment_intent = stripe_pi_id
        charge.amount = amount_q
        charge.amount_captured = amount_q
        charge.amount_refunded = amount_refunded_q
        mock_event.data.object = charge
        return mock_event

    # ── Happy path ────────────────────────────────────────────

    def test_stripe_payment_succeeded_captures_intent(self) -> None:
        """payment_intent.succeeded → PaymentIntent captured."""
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)
        event_dict = self._make_event(
            "payment_intent.succeeded",
            intent.gateway_id,
            intent.ref,
        )

        mock_event = self._mock_stripe_construct(event_dict)
        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            resp = self._post_webhook(event_dict)

        self.assertEqual(resp.status_code, 200, resp.data)

        # Intent should be captured
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    def test_stripe_payment_succeeded_captures_payman_intent(self) -> None:
        """payment_intent.succeeded → Payman intent.status == 'captured'.

        Status is NOT written to order.data["payment"] — Payman is the canonical source.
        """
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)
        event_dict = self._make_event("payment_intent.succeeded", intent.gateway_id, intent.ref)
        mock_event = self._mock_stripe_construct(event_dict)

        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            self._post_webhook(event_dict)

        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")
        order.refresh_from_db()
        self.assertNotIn("status", order.data.get("payment", {}))

    def test_stripe_payment_succeeded_accepts_stripe_object_metadata(self) -> None:
        """Stripe SDK metadata objects are accepted, not only dict metadata."""
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)
        event_dict = self._make_event("payment_intent.succeeded", intent.gateway_id, intent.ref)
        mock_event = self._mock_stripe_construct(event_dict)
        mock_event.data.object.metadata = _StripeObjectMetadata(
            shopman_ref=intent.ref,
            order_ref=order.ref,
        )

        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            resp = self._post_webhook(event_dict)

        self.assertEqual(resp.status_code, 200, resp.data)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    def test_stripe_checkout_completed_accepts_stripe_object_metadata(self) -> None:
        """checkout.session.completed accepts Stripe SDK metadata objects."""
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order, stripe_pi_id="cs_test_checkout")
        event_dict = {
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_checkout", "object": "checkout.session"}},
        }
        mock_event = MagicMock()
        mock_event.type = "checkout.session.completed"
        mock_session = MagicMock()
        mock_session.payment_intent = "pi_test_checkout_completed"
        mock_session.metadata = _StripeObjectMetadata(
            shopman_ref=intent.ref,
            order_ref=order.ref,
        )
        mock_event.data.object = mock_session

        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            resp = self._post_webhook(event_dict)

        self.assertEqual(resp.status_code, 200, resp.data)
        intent.refresh_from_db()
        self.assertEqual(intent.gateway_id, "pi_test_checkout_completed")
        self.assertEqual(intent.status, "authorized")

    # ── Idempotency ───────────────────────────────────────────

    def test_stripe_duplicate_webhook_idempotent(self) -> None:
        """Same webhook twice → PaymentIntent captured once, downstream hook once."""
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)
        event_dict = self._make_event("payment_intent.succeeded", intent.gateway_id, intent.ref)
        mock_event = self._mock_stripe_construct(event_dict)

        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            with patch(
                "shopman.shop.webhooks.stripe.StripeWebhookView._trigger_order_hooks"
            ) as mock_hooks:
                resp1 = self._post_webhook(event_dict)
                resp2 = self._post_webhook(event_dict)

        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(mock_hooks.call_count, 1)
        self.assertEqual(IdempotencyKey.objects.filter(scope="webhook:stripe").count(), 1)

        # Status still captured (not double-captured)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    def test_stripe_charge_refunded_reconciles_cumulative_amounts(self) -> None:
        """Stripe refund events report cumulative totals; Payman records deltas."""
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)
        PaymentService.authorize(intent.ref, gateway_id=intent.gateway_id)
        PaymentService.capture(intent.ref, gateway_id="ch_test_refund")

        first_event = self._mock_charge_refunded_event(
            event_id="evt_refund_1",
            stripe_pi_id=intent.gateway_id,
            amount_q=1000,
            amount_refunded_q=400,
        )
        second_event = self._mock_charge_refunded_event(
            event_id="evt_refund_2",
            stripe_pi_id=intent.gateway_id,
            amount_q=1000,
            amount_refunded_q=1000,
        )

        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.side_effect = [first_event, second_event]
            mock_get_stripe.return_value = mock_stripe

            resp1 = self._post_webhook({"id": "evt_refund_1", "type": "charge.refunded"})
            resp2 = self._post_webhook({"id": "evt_refund_2", "type": "charge.refunded"})

        self.assertEqual(resp1.status_code, 200, resp1.data)
        self.assertEqual(resp2.status_code, 200, resp2.data)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 1000)

        refunds = list(
            PaymentTransaction.objects.filter(
                intent__ref=intent.ref,
                type=PaymentTransaction.Type.REFUND,
            )
            .order_by("created_at")
            .values_list("amount_q", flat=True)
        )
        self.assertEqual(refunds, [400, 600])

    # ── Disputas (chargeback) ─────────────────────────────────

    def _captured_card_intent(self, amount_q: int = 1000):
        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)
        PaymentService.authorize(intent.ref, gateway_id=intent.gateway_id)
        PaymentService.capture(intent.ref, gateway_id="ch_test_dispute")
        return order, intent

    def _mock_dispute_event(
        self,
        *,
        event_id: str,
        event_type: str,
        stripe_pi_id: str,
        status: str,
        amount_q: int,
        dispute_id: str = "du_test_dispute",
    ):
        """Return a Stripe `charge.dispute.*` event."""
        mock_event = MagicMock()
        mock_event.id = event_id
        mock_event.type = event_type
        dispute = MagicMock()
        dispute.id = dispute_id
        dispute.payment_intent = stripe_pi_id
        dispute.charge = "ch_test_dispute"
        dispute.status = status
        dispute.amount = amount_q
        dispute.currency = "brl"
        dispute.reason = "fraudulent"
        dispute.evidence_details.due_by = 1789000000
        mock_event.data.object = dispute
        return mock_event

    def _post_dispute(self, events: list) -> list:
        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.side_effect = events
            mock_get_stripe.return_value = mock_stripe
            return [
                self._post_webhook({"id": event.id, "type": event.type})
                for event in events
            ]

    def _chargebacks(self, intent_ref: str) -> list[int]:
        return list(
            PaymentTransaction.objects.filter(
                intent__ref=intent_ref,
                type=PaymentTransaction.Type.CHARGEBACK,
            )
            .order_by("created_at")
            .values_list("amount_q", flat=True)
        )

    def test_stripe_dispute_created_registers_risk_without_booking_chargeback(self) -> None:
        """Disputa aberta é dinheiro em RISCO, não perdido: nada no livro ainda."""
        _order, intent = self._captured_card_intent()

        responses = self._post_dispute([
            self._mock_dispute_event(
                event_id="evt_dispute_created",
                event_type="charge.dispute.created",
                stripe_pi_id=intent.gateway_id,
                status="needs_response",
                amount_q=1000,
            ),
        ])

        self.assertEqual(responses[0].status_code, 200, responses[0].data)
        self.assertEqual(self._chargebacks(intent.ref), [])
        self.assertEqual(PaymentService.chargeback_total(intent.ref), 0)

        intent.refresh_from_db()
        record = intent.gateway_data["disputes"]["du_test_dispute"]
        self.assertEqual(record["status"], "needs_response")
        self.assertEqual(record["amount_q"], 1000)
        self.assertTrue(
            OperatorAlert.objects.filter(type="payment_disputed", severity="error").exists()
        )

    def test_stripe_dispute_won_never_becomes_chargeback(self) -> None:
        """`closed` com status `won` devolve o dinheiro — não é chargeback."""
        _order, intent = self._captured_card_intent()

        self._post_dispute([
            self._mock_dispute_event(
                event_id="evt_dispute_open",
                event_type="charge.dispute.created",
                stripe_pi_id=intent.gateway_id,
                status="needs_response",
                amount_q=1000,
            ),
            self._mock_dispute_event(
                event_id="evt_dispute_won",
                event_type="charge.dispute.closed",
                stripe_pi_id=intent.gateway_id,
                status="won",
                amount_q=1000,
            ),
        ])

        self.assertEqual(self._chargebacks(intent.ref), [])
        self.assertEqual(PaymentService.chargeback_total(intent.ref), 0)
        intent.refresh_from_db()
        self.assertEqual(intent.gateway_data["disputes"]["du_test_dispute"]["status"], "won")

    def test_stripe_dispute_lost_books_chargeback(self) -> None:
        """`closed` com status `lost`: o dinheiro saiu e não volta — vira livro."""
        _order, intent = self._captured_card_intent()

        self._post_dispute([
            self._mock_dispute_event(
                event_id="evt_dispute_open",
                event_type="charge.dispute.created",
                stripe_pi_id=intent.gateway_id,
                status="needs_response",
                amount_q=1000,
            ),
            self._mock_dispute_event(
                event_id="evt_dispute_lost",
                event_type="charge.dispute.closed",
                stripe_pi_id=intent.gateway_id,
                status="lost",
                amount_q=1000,
            ),
        ])

        self.assertEqual(self._chargebacks(intent.ref), [1000])
        self.assertEqual(PaymentService.chargeback_total(intent.ref), 1000)
        # Chargeback não é reembolso, e não mexe no status do intent.
        self.assertEqual(PaymentService.refunded_total(intent.ref), 0)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")
        self.assertTrue(
            OperatorAlert.objects.filter(type="payment_disputed", severity="critical").exists()
        )

    def test_stripe_dispute_lost_delivered_twice_books_once(self) -> None:
        """Entrega at-least-once: o mesmo `lost` reapresentado dá delta zero."""
        _order, intent = self._captured_card_intent()

        self._post_dispute([
            self._mock_dispute_event(
                event_id="evt_dispute_lost_1",
                event_type="charge.dispute.closed",
                stripe_pi_id=intent.gateway_id,
                status="lost",
                amount_q=1000,
            ),
            self._mock_dispute_event(
                event_id="evt_dispute_lost_2",
                event_type="charge.dispute.closed",
                stripe_pi_id=intent.gateway_id,
                status="lost",
                amount_q=1000,
            ),
        ])

        self.assertEqual(self._chargebacks(intent.ref), [1000])

    def test_stripe_dispute_created_arriving_after_closed_does_not_reopen(self) -> None:
        """Fora de ordem: `created` atrasado não reabre disputa já encerrada."""
        _order, intent = self._captured_card_intent()

        self._post_dispute([
            self._mock_dispute_event(
                event_id="evt_dispute_lost",
                event_type="charge.dispute.closed",
                stripe_pi_id=intent.gateway_id,
                status="lost",
                amount_q=1000,
            ),
            self._mock_dispute_event(
                event_id="evt_dispute_created_late",
                event_type="charge.dispute.created",
                stripe_pi_id=intent.gateway_id,
                status="needs_response",
                amount_q=1000,
            ),
        ])

        self.assertEqual(self._chargebacks(intent.ref), [1000])
        intent.refresh_from_db()
        self.assertEqual(intent.gateway_data["disputes"]["du_test_dispute"]["status"], "lost")

    def test_stripe_dispute_inquiry_closed_is_not_chargeback(self) -> None:
        """`warning_closed` é consulta encerrada sem disputa formal: zero."""
        _order, intent = self._captured_card_intent()

        self._post_dispute([
            self._mock_dispute_event(
                event_id="evt_inquiry",
                event_type="charge.dispute.closed",
                stripe_pi_id=intent.gateway_id,
                status="warning_closed",
                amount_q=1000,
            ),
        ])

        self.assertEqual(self._chargebacks(intent.ref), [])
        self.assertFalse(OperatorAlert.objects.filter(type="payment_disputed").exists())

    def test_stripe_dispute_for_unknown_charge_is_ignored(self) -> None:
        """Disputa de cobrança que não é nossa não pode derrubar o webhook."""
        responses = self._post_dispute([
            self._mock_dispute_event(
                event_id="evt_dispute_unknown",
                event_type="charge.dispute.created",
                stripe_pi_id="pi_not_ours",
                status="needs_response",
                amount_q=1000,
            ),
        ])

        self.assertEqual(responses[0].status_code, 200, responses[0].data)
        self.assertEqual(
            PaymentTransaction.objects.filter(type=PaymentTransaction.Type.CHARGEBACK).count(),
            0,
        )

    def test_stripe_dispute_above_capture_alerts_instead_of_booking(self) -> None:
        """Disputa maior que o capturado é deriva: alerta, e o livro não mente."""
        _order, intent = self._captured_card_intent()

        self._post_dispute([
            self._mock_dispute_event(
                event_id="evt_dispute_oversized",
                event_type="charge.dispute.closed",
                stripe_pi_id=intent.gateway_id,
                status="lost",
                amount_q=1500,
            ),
        ])

        self.assertEqual(self._chargebacks(intent.ref), [])
        self.assertTrue(
            OperatorAlert.objects.filter(type="payment_reconciliation_failed").exists()
        )

    # ── Race condition ────────────────────────────────────────

    def test_stripe_payment_after_cancel_handled_gracefully(self) -> None:
        """Webhook for cancelled order → no crash, returns 200."""

        order = _create_order_with_payment("web", "card")
        intent = _create_card_intent(order)

        # Cancel the order before payment arrives
        order.transition_status("cancelled", actor="test")

        event_dict = self._make_event("payment_intent.succeeded", intent.gateway_id, intent.ref)
        mock_event = self._mock_stripe_construct(event_dict)

        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe

            resp = self._post_webhook(event_dict)

        # Should not crash
        self.assertEqual(resp.status_code, 200)

    # ── Invalid signature ─────────────────────────────────────

    def test_stripe_missing_signature_returns_400(self) -> None:
        """Request without Stripe-Signature header → 400."""
        resp = self.client.post(
            self.URL,
            data=b'{"type": "test"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_stripe_invalid_signature_returns_400(self) -> None:
        """Request with invalid Stripe-Signature → 400."""
        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.side_effect = Exception("Signature invalid")
            mock_get_stripe.return_value = mock_stripe

            resp = self._post_webhook({"type": "test"}, sig="bad-sig")

        self.assertEqual(resp.status_code, 400)

    def test_stripe_processing_failure_creates_operator_alert(self) -> None:
        """Verified webhook that crashes during processing creates an ops alert."""
        event_dict = self._make_event("payment_intent.succeeded", "pi_alert", "PAY-ALERT")
        mock_event = self._mock_stripe_construct(event_dict)

        with (
            patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe,
            patch(
                "shopman.shop.adapters.payment_stripe.handle_webhook_event",
                side_effect=RuntimeError("gateway drift"),
            ),
        ):
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe
            resp = self._post_webhook(event_dict)

        self.assertEqual(resp.status_code, 500)
        alert = OperatorAlert.objects.get(type="webhook_failed")
        self.assertEqual(alert.severity, "error")
        self.assertEqual(alert.order_ref, "ORD-TEST")
        self.assertIn("Webhook stripe falhou", alert.message)
        self.assertIn("payment_intent.succeeded", alert.message)

    # ── Unconfigured ──────────────────────────────────────────

    @override_settings(SHOPMAN_STRIPE={})
    def test_stripe_webhook_not_configured_returns_500(self) -> None:
        """No WEBHOOK_SECRET configured → 500."""
        resp = self._post_webhook({"type": "test"}, sig="any-sig")
        self.assertEqual(resp.status_code, 500)


# ══════════════════════════════════════════════════════════════
# EFI PIX Webhook Tests
# ══════════════════════════════════════════════════════════════


@override_settings(SHOPMAN_EFI_WEBHOOK=EFI_WEBHOOK_SETTINGS)
class EfiPixWebhookTests(WebhookTestBase):
    """Tests for /api/webhooks/efi/pix/."""

    URL = "/api/webhooks/efi/pix/"
    AUTH_HEADER = {"HTTP_X_EFI_WEBHOOK_TOKEN": "test-efi-token"}

    def _post(self, payload: dict, **headers) -> object:
        combined = {**self.AUTH_HEADER, **headers}
        return self.client.post(self.URL, payload, format="json", **combined)

    # ── GET health check ──────────────────────────────────────

    def test_efi_get_health_check(self) -> None:
        """GET /webhook/efi-pix/ → 200 (health check for EFI)."""
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)

    # ── Happy path ────────────────────────────────────────────

    def test_efi_pix_payment_captures_intent(self) -> None:
        """PIX notification → PaymentIntent captured."""
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        payload = {
            "pix": [
                {
                    "txid": intent.gateway_id,
                    "endToEndId": "E1234567890",
                    "valor": f"{order.total_q / 100:.2f}",
                }
            ]
        }

        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200, resp.data)

        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    def test_efi_pix_payment_records_e2e_id(self) -> None:
        """PIX notification → order.data['payment']['e2e_id'] recorded, Payman intent captured.

        Status is NOT written to order.data["payment"] — Payman is the canonical source.
        """
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        payload = {
            "pix": [
                {
                    "txid": intent.gateway_id,
                    "endToEndId": "E9999999999",
                    "valor": "10.00",
                }
            ]
        }
        self._post(payload)

        order.refresh_from_db()
        self.assertEqual(order.data.get("payment", {}).get("e2e_id"), "E9999999999")
        self.assertNotIn("status", order.data.get("payment", {}))
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    # ── Idempotency ───────────────────────────────────────────

    def test_efi_duplicate_webhook_idempotent(self) -> None:
        """Same PIX notification twice → intent captured once."""
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        payload = {
            "pix": [
                {
                    "txid": intent.gateway_id,
                    "endToEndId": "E_IDEM_TEST",
                    "valor": "10.00",
                }
            ]
        }

        resp1 = self._post(payload)
        resp2 = self._post(payload)

        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.data["processed"], 1)
        self.assertEqual(resp2.data["replays"], 1)
        self.assertEqual(IdempotencyKey.objects.filter(scope="webhook:efi-pix").count(), 1)

        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    def test_efi_same_e2e_cannot_capture_another_txid(self) -> None:
        """A replayed PIX e2e id is global, not scoped only to a txid."""
        order_1 = _create_order_with_payment("web", "pix")
        intent_1 = _create_pix_intent(order_1)
        order_2 = _create_order_with_payment("web", "pix")
        intent_2 = PaymentService.create_intent(
            order_ref=order_2.ref,
            amount_q=order_2.total_q,
            method="pix",
            gateway="efi",
            gateway_data={},
        )
        intent_2.gateway_id = "txid_second_order"
        intent_2.save(update_fields=["gateway_id"])
        order_2.data.setdefault("payment", {})["intent_ref"] = intent_2.ref
        order_2.save(update_fields=["data", "updated_at"])

        e2e_id = "E_GLOBAL_REPLAY"
        resp1 = self._post(
            {"pix": [{"txid": intent_1.gateway_id, "endToEndId": e2e_id, "valor": "10.00"}]}
        )
        resp2 = self._post(
            {"pix": [{"txid": intent_2.gateway_id, "endToEndId": e2e_id, "valor": "10.00"}]}
        )

        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data["replays"], 1)
        intent_2.refresh_from_db()
        self.assertEqual(intent_2.status, "pending")

    def test_efi_in_progress_replay_returns_409(self) -> None:
        from shopman.shop.services.webhook_idempotency import stable_webhook_key

        IdempotencyKey.objects.create(
            scope="webhook:efi-pix",
            key=f"txid:{stable_webhook_key('txid_busy')}",
            status="in_progress",
        )

        resp = self._post(
            {"pix": [{"txid": "txid_busy", "endToEndId": "", "valor": "10.00"}]}
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["in_progress"], 1)

    def test_confirm_pix_without_e2e_is_still_order_idempotent(self) -> None:
        """Legacy callers without e2e_id must not dispatch on_paid twice."""
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid=intent.gateway_id, amount="10.00")
            confirm_pix(txid=intent.gateway_id, amount="10.00")

        self.assertEqual(mock_dispatch.call_count, 1)

    # ── Race condition ────────────────────────────────────────

    def test_efi_payment_after_cancel_refunds_and_alerts(self) -> None:
        """Pedido cancelado com a cobrança ainda de pé: captura, estorna e alerta.

        Este teste só afirmava "200, sem crash" — e 200 sem crash era
        exatamente o que o pedido cancelado devolvia enquanto o dinheiro ficava
        na conta da loja. O que prova o conserto é o LIVRO (capturado e
        devolvido) e o alerta certo.
        """
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)
        order.transition_status("cancelled", actor="test")

        payload = {
            "pix": [
                {
                    "txid": intent.gateway_id,
                    "endToEndId": "E_RACE",
                    "valor": "10.00",
                }
            ]
        }
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(PaymentService.captured_total(intent.ref), 1000)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 1000)
        self.assertTrue(
            OperatorAlert.objects.filter(
                type="payment_after_cancel", order_ref=order.ref,
            ).exists()
        )
        self.assertFalse(
            OperatorAlert.objects.filter(
                type="payment_insufficient", order_ref=order.ref,
            ).exists()
        )

    # ── Order not found ───────────────────────────────────────

    def test_efi_unknown_txid_ignored_gracefully(self) -> None:
        """PIX notification for unknown txid → 200, no crash."""
        payload = {
            "pix": [
                {
                    "txid": "nonexistent_txid_xyz",
                    "endToEndId": "E_UNKNOWN",
                    "valor": "50.00",
                }
            ]
        }
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)

    # ── Missing pix data ──────────────────────────────────────

    def test_efi_empty_payload_returns_200_for_registration_check(self) -> None:
        """Authenticated empty POST is accepted for EFI webhook registration checks."""
        resp = self._post({})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["check"], "accepted")

    def test_efi_registration_test_event_returns_200(self) -> None:
        """EFI sends evento=teste_webhook while registering the webhook URL."""
        resp = self._post({"evento": "teste_webhook", "data_criacao": "2026-05-21T13:24:06.791Z"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["check"], "accepted")

    def test_efi_empty_pix_list_returns_400(self) -> None:
        """POST with empty pix list → 400."""
        resp = self._post({"pix": []})
        self.assertEqual(resp.status_code, 400)

    def test_efi_missing_pix_field_returns_400(self) -> None:
        """POST without pix key → 400."""
        resp = self._post({"other": "data"})
        self.assertEqual(resp.status_code, 400)

    # ── Auth ──────────────────────────────────────────────────

    def test_efi_invalid_token_returns_401(self) -> None:
        """Request with wrong token → 401."""
        resp = self.client.post(
            self.URL,
            {"pix": [{"txid": "abc", "endToEndId": "E1", "valor": "10.00"}]},
            format="json",
            HTTP_X_EFI_WEBHOOK_TOKEN="wrong-token",
        )
        self.assertEqual(resp.status_code, 401)

    def test_efi_missing_token_returns_401(self) -> None:
        """Request without any token → 401."""
        resp = self.client.post(
            self.URL,
            {"pix": [{"txid": "abc", "endToEndId": "E1", "valor": "10.00"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_efi_token_in_query_string_is_accepted(self) -> None:
        """A Efí NÃO envia cabeçalho customizado.

        Os mecanismos documentados dela são mTLS, allowlist de IP e hash no fim
        da URL registrada. Recusar a query aqui derrubaria o PIX de produção
        inteiro (401 em todo webhook). O vazamento em log é tratado onde dá
        para tratar: o `before_send` do Sentry corta a query string, e o token
        é rotacionado como credencial que vaza por desenho."""
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)
        resp = self.client.post(
            f"{self.URL}?token=test-efi-token",
            {"pix": [{"txid": intent.gateway_id, "endToEndId": "E_QS", "valor": "10.00"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")

    def test_efi_wrong_token_in_query_string_returns_401(self) -> None:
        resp = self.client.post(
            f"{self.URL}?token=nope",
            {"pix": [{"txid": "abc", "endToEndId": "E1", "valor": "10.00"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_efi_wrong_header_is_not_rescued_by_the_query(self) -> None:
        """Header presente e errado decide: não cai para a query."""
        resp = self.client.post(
            f"{self.URL}?token=test-efi-token",
            {"pix": [{"txid": "abc", "endToEndId": "E1", "valor": "10.00"}]},
            format="json",
            HTTP_X_EFI_WEBHOOK_TOKEN="wrong-token",
        )
        self.assertEqual(resp.status_code, 401)

    @override_settings(SHOPMAN_EFI_WEBHOOK={"webhook_token": ""})
    def test_efi_unconfigured_token_rejects_all_requests(self) -> None:
        """Unconfigured webhook_token → every request is rejected, including
        ones that would otherwise match. There is no bypass path."""
        resp = self.client.post(
            self.URL,
            {"pix": [{"txid": "abc", "endToEndId": "E1", "valor": "10.00"}]},
            format="json",
            HTTP_X_EFI_WEBHOOK_TOKEN="any-token",
        )
        self.assertEqual(resp.status_code, 401)


@override_settings(SHOPMAN_EFI_WEBHOOK=EFI_WEBHOOK_SETTINGS)
class EfiPixWebhookIpAllowlistTests(WebhookTestBase):
    """A allowlist de IP é a terceira camada da Efí, e ela é opt-in.

    Lista vazia (o default) passa tudo: configuração ausente não pode ser o
    motivo de a loja parar de receber notificação de pagamento. Configurada,
    o endereço avaliado é a ÚLTIMA entrada do ``X-Forwarded-For`` — a que a
    borda da plataforma acrescentou, e a única que o chamador não forja.
    """

    URL = "/api/webhooks/efi/pix/"

    def _post(self, txid: str = "abc", **extra):
        return self.client.post(
            self.URL,
            {"pix": [{"txid": txid, "endToEndId": "E-IP", "valor": "10.00"}]},
            format="json",
            HTTP_X_EFI_WEBHOOK_TOKEN="test-efi-token",
            **extra,
        )

    def test_empty_allowlist_accepts_any_source(self) -> None:
        resp = self._post(REMOTE_ADDR="203.0.113.77")
        self.assertEqual(resp.status_code, 200, resp.data)

    @override_settings(
        SHOPMAN_EFI_WEBHOOK={"webhook_token": "test-efi-token", "ip_allowlist": ("198.51.100.0/24",)}
    )
    def test_allowlisted_source_is_accepted(self) -> None:
        resp = self._post(REMOTE_ADDR="198.51.100.9")
        self.assertEqual(resp.status_code, 200, resp.data)

    @override_settings(
        SHOPMAN_EFI_WEBHOOK={"webhook_token": "test-efi-token", "ip_allowlist": ("198.51.100.0/24",)}
    )
    def test_source_outside_allowlist_is_rejected(self) -> None:
        resp = self._post(REMOTE_ADDR="203.0.113.77")
        self.assertEqual(resp.status_code, 401)

    @override_settings(
        SHOPMAN_EFI_WEBHOOK={"webhook_token": "test-efi-token", "ip_allowlist": ("198.51.100.0/24",)}
    )
    def test_forwarded_for_uses_the_last_hop(self) -> None:
        """Atrás do proxy da plataforma, quem vale é o último salto."""
        resp = self._post(
            HTTP_X_FORWARDED_FOR="203.0.113.77, 198.51.100.9",
            REMOTE_ADDR="10.0.0.1",
        )
        self.assertEqual(resp.status_code, 200, resp.data)

    @override_settings(
        SHOPMAN_EFI_WEBHOOK={"webhook_token": "test-efi-token", "ip_allowlist": ("198.51.100.0/24",)}
    )
    def test_spoofed_forwarded_for_does_not_pass(self) -> None:
        """Chamador que prepende um IP da lista continua de fora."""
        resp = self._post(
            HTTP_X_FORWARDED_FOR="198.51.100.9, 203.0.113.77",
            REMOTE_ADDR="10.0.0.1",
        )
        self.assertEqual(resp.status_code, 401)

    @override_settings(
        SHOPMAN_EFI_WEBHOOK={"webhook_token": "test-efi-token", "ip_allowlist": ("198.51.100.0/24",)}
    )
    def test_allowlist_is_checked_before_the_token(self) -> None:
        """Token certo não resgata origem errada."""
        resp = self.client.post(
            f"{self.URL}?token=test-efi-token",
            {"pix": [{"txid": "abc", "endToEndId": "E-IP", "valor": "10.00"}]},
            format="json",
            REMOTE_ADDR="203.0.113.77",
        )
        self.assertEqual(resp.status_code, 401)

    @override_settings(
        SHOPMAN_EFI_WEBHOOK={"webhook_token": "test-efi-token", "ip_allowlist": ("nao-e-cidr",)}
    )
    def test_broken_cidr_does_not_open_the_door(self) -> None:
        """Entrada inválida na lista é logada e ignorada — não vira 'passa tudo'."""
        resp = self._post(REMOTE_ADDR="198.51.100.9")
        self.assertEqual(resp.status_code, 401)


# ══════════════════════════════════════════════════════════════
# PIX capture sufficiency (confirm_pix ↔ Stripe parity)
# ══════════════════════════════════════════════════════════════


class PixCaptureSufficiencyTests(WebhookTestBase):
    """O dinheiro do Pix nunca é engolido, e o alerta nunca mente.

    Três defeitos moravam aqui, e cada um tem o seu caso:

    * captura parcial queimava a cobrança (o Payman admite UMA captura por
      intent, então o segundo Pix não tinha mais onde entrar);
    * Pix sem valor era lido como "cobre o total";
    * sem intent no livro, o pedido era achado por ``icontains`` e a
      suficiência vinha do valor que o próprio webhook declarava.
    """

    def test_partial_pix_does_not_capture_the_charge(self) -> None:
        """Abaixo do total: nada de captura, e a cobrança segue de pé.

        Capturar R$ 5,00 de uma cobrança de R$ 10,00 mandava o intent para
        ``captured`` e o Pix que completasse o valor não teria mais onde
        entrar: o cliente desembolsava R$ 10,00 e o livro registrava R$ 5,00.
        """
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = _create_order_with_payment("web", "pix")  # total_q = 1000
        intent = _create_pix_intent(order)

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid=intent.gateway_id, e2e_id="E_PARTIAL", amount="5.00")

        mock_dispatch.assert_not_called()
        intent.refresh_from_db()
        self.assertEqual(intent.status, "pending")
        self.assertEqual(PaymentService.captured_total(intent.ref), 0)

        order.refresh_from_db()
        payment_data = order.data["payment"]
        self.assertEqual(payment_data["paid_amount_q"], 500)
        self.assertNotIn("captured_at", payment_data)

        alert = OperatorAlert.objects.get(
            type="payment_insufficient", order_ref=order.ref, acknowledged=False,
        )
        self.assertIn("R$ 5,00 de R$ 10,00", alert.message)
        self.assertIn("Faltam R$ 5,00", alert.message)

    def test_two_partial_pix_complete_the_charge(self) -> None:
        """Dois Pix parciais SOMAM e capturam a cobrança inteira.

        Este é o caso medido: R$ 1,00 + R$ 8,00 numa cobrança de R$ 9,00. O
        livro registrava R$ 1,00 e o pedido ficava ``accepted`` para sempre.
        """
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = _create_order_with_payment("web", "pix")  # total_q = 1000
        intent = _create_pix_intent(order)

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid=intent.gateway_id, e2e_id="E_PART_1", amount="4.00")
            confirm_pix(txid=intent.gateway_id, e2e_id="E_PART_2", amount="6.00")

        mock_dispatch.assert_called_once_with(order, "on_paid")
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")
        self.assertEqual(PaymentService.captured_total(intent.ref), 1000)

        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["paid_amount_q"], 1000)
        self.assertIn("captured_at", order.data["payment"])

        # O alerta do parcial descrevia um quadro que deixou de existir.
        self.assertFalse(
            OperatorAlert.objects.filter(
                type="payment_insufficient", order_ref=order.ref, acknowledged=False,
            ).exists()
        )

    def test_replayed_partial_pix_counts_once(self) -> None:
        """O MESMO Pix reapresentado não vira dinheiro novo."""
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid=intent.gateway_id, e2e_id="E_PART_SAME", amount="5.00")
            confirm_pix(txid=intent.gateway_id, e2e_id="E_PART_SAME", amount="5.00")

        mock_dispatch.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["paid_amount_q"], 500)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "pending")
        self.assertEqual(
            OperatorAlert.objects.filter(
                type="payment_insufficient", order_ref=order.ref,
            ).count(),
            1,
        )

    def test_second_partial_pix_alerts_again_with_the_new_amount(self) -> None:
        """O debounce de 15 min escondia o segundo Pix parcial.

        O quadro mudou (agora faltam R$ 2,00, não R$ 7,00), e um alerta que
        descreve o quadro antigo é um alerta errado.
        """
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        confirm_pix(txid=intent.gateway_id, e2e_id="E_STEP_1", amount="3.00")
        confirm_pix(txid=intent.gateway_id, e2e_id="E_STEP_2", amount="5.00")

        messages = list(
            OperatorAlert.objects.filter(
                type="payment_insufficient", order_ref=order.ref,
            ).values_list("message", flat=True)
        )
        self.assertEqual(len(messages), 2)
        self.assertTrue(any("R$ 3,00 de R$ 10,00" in m for m in messages))
        self.assertTrue(any("R$ 8,00 de R$ 10,00" in m for m in messages))

    def test_full_pix_dispatches_on_paid_and_records_captured_at(self) -> None:
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid=intent.gateway_id, e2e_id="E_FULL", amount="10.00")

        mock_dispatch.assert_called_once_with(order, "on_paid")
        order.refresh_from_db()
        self.assertIn("captured_at", order.data["payment"])
        self.assertFalse(
            OperatorAlert.objects.filter(
                type="payment_insufficient", order_ref=order.ref,
            ).exists()
        )

    def test_pix_without_amount_never_counts_as_full_payment(self) -> None:
        """Webhook autenticado sem o valor pago não é prova de pagamento.

        (Na EFI o campo se chama ``valor``; para dentro ele viaja como
        ``amount``.)

        A ausência caía num default igual ao valor da cobrança, então o Pix
        sem valor capturava o total e despachava ``on_paid``: pedido entregue
        sem que ninguém conferisse um centavo. Valor ausente é indeterminado,
        e indeterminado espera.
        """
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid=intent.gateway_id, e2e_id="E_NO_AMOUNT", amount="")

        mock_dispatch.assert_not_called()
        intent.refresh_from_db()
        self.assertEqual(intent.status, "pending")
        order.refresh_from_db()
        self.assertNotIn("captured_at", order.data["payment"])

        alert = OperatorAlert.objects.get(
            type="payment_reconciliation_failed", order_ref=order.ref,
        )
        self.assertIn("sem o valor pago", alert.message)

    # ── txid casado por fragmento ─────────────────────────────

    def test_txid_fragment_never_touches_another_order(self) -> None:
        """``icontains`` fazia ``"PAY-"`` casar com o pedido de qualquer um.

        Controle positivo junto: o MESMO pedido é encontrado quando o txid é
        exatamente o ``intent_ref`` gravado nele, então a ausência de efeito
        no caso do fragmento não é "a busca nunca acha nada".
        """
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = Order.objects.create(
            ref="PIX-FRAGMENT",
            channel_ref="web",
            status="accepted",
            total_q=1000,
            data={"payment": {"method": "pix", "intent_ref": "PAY-FRAGMENT-1"}},
        )

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid="PAY-", e2e_id="E_FRAGMENT", amount="10.00")

        mock_dispatch.assert_not_called()
        order.refresh_from_db()
        self.assertNotIn("paid_amount_q", order.data["payment"])
        self.assertNotIn("captured_at", order.data["payment"])
        self.assertFalse(OperatorAlert.objects.filter(order_ref=order.ref).exists())

        # Controle positivo: com o valor exato, o pedido É alcançado.
        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid="PAY-FRAGMENT-1", e2e_id="E_EXACT", amount="10.00")

        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["paid_amount_q"], 1000)

    def test_pix_without_charge_in_the_book_never_confirms_payment(self) -> None:
        """Sem intent no Payman não há contrapartida: registra e chama gente.

        O valor declarado pelo próprio webhook era aceito como prova de
        suficiência: gravava ``captured_at`` e despachava ``on_paid``. E como
        ``captured_at`` é o guard de idempotência, o pagamento de verdade que
        chegasse depois capturava no Payman e não disparava mais nada.
        """
        from shopman.shop.services.pix_confirmation import confirm_pix

        order = Order.objects.create(
            ref="PIX-NO-CHARGE",
            channel_ref="web",
            status="accepted",
            total_q=1000,
            data={"payment": {"method": "pix", "intent_ref": "PAY-NO-CHARGE"}},
        )

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            confirm_pix(txid="PAY-NO-CHARGE", e2e_id="E_NO_CHARGE", amount="10.00")

        mock_dispatch.assert_not_called()
        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["paid_amount_q"], 1000)
        self.assertNotIn("captured_at", order.data["payment"])

        alert = OperatorAlert.objects.get(
            type="payment_reconciliation_failed", order_ref=order.ref,
        )
        self.assertIn("sem cobrança correspondente no livro", alert.message)


# ══════════════════════════════════════════════════════════════
# EFI PIX — as bordas do dinheiro, pelo webhook de verdade
# ══════════════════════════════════════════════════════════════


@override_settings(SHOPMAN_EFI_WEBHOOK=EFI_WEBHOOK_SETTINGS)
class EfiPixWebhookMoneyTests(WebhookTestBase):
    """Sem valor, a mais, a menos, com vírgula, replay e depois do cancelamento.

    Cada caso cobra duas coisas: o efeito no Payman (o livro) e um alerta que
    descreve o que de fato aconteceu. Alerta que descreve outra coisa é metade
    do defeito.
    """

    URL = "/api/webhooks/efi/pix/"
    AUTH_HEADER = {"HTTP_X_EFI_WEBHOOK_TOKEN": "test-efi-token"}

    def _post_pix(self, **pix_item) -> object:
        return self.client.post(
            self.URL, {"pix": [pix_item]}, format="json", **self.AUTH_HEADER,
        )

    def test_webhook_without_valor_captures_nothing(self) -> None:
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        resp = self._post_pix(txid=intent.gateway_id, endToEndId="E_WH_NO_VALOR")

        self.assertEqual(resp.status_code, 200, resp.data)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "pending")
        self.assertEqual(PaymentService.captured_total(intent.ref), 0)
        self.assertIn(
            "sem o valor pago",
            OperatorAlert.objects.get(
                type="payment_reconciliation_failed", order_ref=order.ref,
            ).message,
        )

    def test_webhook_valor_above_total_captures_the_authorized_amount(self) -> None:
        """Pix a maior levantava ``capture_exceeds_authorized``.

        O webhook respondia 500, a Efí reentregava, a falha se repetia para
        sempre e o pedido ficava travado. Captura-se o AUTORIZADO, e a
        diferença vira tarefa de gente com o valor na mão.
        """
        order = _create_order_with_payment("web", "pix")  # total_q = 1000
        intent = _create_pix_intent(order)

        resp = self._post_pix(
            txid=intent.gateway_id, endToEndId="E_WH_ABOVE", valor="12.00",
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")
        self.assertEqual(PaymentService.captured_total(intent.ref), 1000)
        self.assertEqual(
            PaymentTransaction.objects.filter(intent=intent, type="capture").count(), 1,
        )
        alert = OperatorAlert.objects.get(
            type="payment_reconciliation_failed", order_ref=order.ref,
        )
        self.assertIn("acima do total: R$ 12,00 de R$ 10,00", alert.message)
        self.assertIn("devolva R$ 2,00", alert.message)

    def test_webhook_valor_below_total_keeps_the_charge_capturable(self) -> None:
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        resp = self._post_pix(
            txid=intent.gateway_id, endToEndId="E_WH_BELOW", valor="5.00",
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "pending")
        order.refresh_from_db()
        self.assertNotIn("captured_at", order.data["payment"])
        self.assertIn(
            "Faltam R$ 5,00",
            OperatorAlert.objects.get(
                type="payment_insufficient", order_ref=order.ref,
            ).message,
        )

    def test_webhook_valor_with_comma_is_understood(self) -> None:
        """``"10,00"`` explodia no ``Decimal`` e virava 500 eterno."""
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        resp = self._post_pix(
            txid=intent.gateway_id, endToEndId="E_WH_COMMA", valor="10,00",
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")
        self.assertEqual(PaymentService.captured_total(intent.ref), 1000)

    def test_webhook_replay_does_not_double_the_money(self) -> None:
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)

        first = self._post_pix(
            txid=intent.gateway_id, endToEndId="E_WH_REPLAY", valor="10.00",
        )
        second = self._post_pix(
            txid=intent.gateway_id, endToEndId="E_WH_REPLAY", valor="10.00",
        )

        self.assertEqual(first.data["processed"], 1)
        self.assertEqual(second.data["replays"], 1)
        self.assertEqual(PaymentService.captured_total(intent.ref), 1000)
        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["paid_amount_q"], 1000)

    def test_pix_after_cancel_is_booked_refunded_and_alerted(self) -> None:
        """O dinheiro que cai depois do cancelamento era engolido em silêncio.

        A cobrança cancelada não casava com nenhum ramo de captura, o Payman
        respondia "não capturado" à checagem seguinte, e o operador recebia um
        alerta dizendo que o cliente havia pago A MENOS e que "o pedido segue
        aguardando pagamento" — com o pedido cancelado e o dinheiro parado na
        conta da loja, sem estorno.
        """
        from shopman.shop.services import payment as payment_service

        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)
        PaymentService.authorize(intent.ref, gateway_id=intent.gateway_id)

        payment_service.cancel(order, reason="order_cancelled")
        order.transition_status("cancelled", actor="test")
        intent.refresh_from_db()
        self.assertEqual(intent.status, "cancelled")

        resp = self._post_pix(
            txid=intent.gateway_id, endToEndId="E_WH_AFTER_CANCEL", valor="10.00",
        )

        self.assertEqual(resp.status_code, 200, resp.data)

        # O dinheiro está no livro, e voltou.
        booked = [
            i
            for i in PaymentService.get_by_order(order.ref)
            if (i.gateway_data or {}).get("booked_by") == "pix_confirmation"
        ]
        self.assertEqual(len(booked), 1)
        self.assertEqual(PaymentService.captured_total(booked[0].ref), 1000)
        self.assertEqual(PaymentService.refunded_total(booked[0].ref), 1000)

        # O alerta diz o que aconteceu, e o que MENTIA não existe.
        self.assertTrue(
            OperatorAlert.objects.filter(
                type="payment_after_cancel", order_ref=order.ref,
            ).exists()
        )
        self.assertFalse(
            OperatorAlert.objects.filter(
                type="payment_insufficient", order_ref=order.ref,
            ).exists()
        )

        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.data["payment"]["paid_amount_q"], 1000)

    def test_pix_on_a_dead_charge_of_a_live_order_is_booked_not_confirmed(self) -> None:
        """Cobrança morta com pedido vivo: cliente pagou o QR velho, ou pagou duas vezes.

        Máquina nenhuma distingue os dois, e os dois precisam de gente. O que
        não pode faltar é o dinheiro estar no livro e alguém saber.
        """
        order = _create_order_with_payment("web", "pix")
        intent = _create_pix_intent(order)
        PaymentService.cancel(intent.ref, reason="superseded_by_captured_payment")

        resp = self._post_pix(
            txid=intent.gateway_id, endToEndId="E_WH_DEAD_LIVE", valor="10.00",
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        booked = [
            i
            for i in PaymentService.get_by_order(order.ref)
            if (i.gateway_data or {}).get("booked_by") == "pix_confirmation"
        ]
        self.assertEqual(len(booked), 1)
        self.assertEqual(PaymentService.captured_total(booked[0].ref), 1000)
        self.assertEqual(PaymentService.refunded_total(booked[0].ref), 0)

        order.refresh_from_db()
        self.assertNotIn("captured_at", order.data["payment"])
        alert = OperatorAlert.objects.get(
            type="payment_reconciliation_failed", order_ref=order.ref,
        )
        self.assertIn("cobrança já encerrada (cancelada)", alert.message)
