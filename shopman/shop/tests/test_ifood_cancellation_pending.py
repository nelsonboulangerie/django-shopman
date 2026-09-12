"""An accepted HTTP request is not a cancelled marketplace order."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.ifood_status import IFoodStatusCallbackHandler
from shopman.shop.services import cancellation, ifood_callbacks, ifood_cancellation, operator_orders

CFG = {"client_id": "test", "client_secret": "test", "cancellation_default_code": "501"}


@override_settings(SHOPMAN_IFOOD=CFG)
class IFoodCancellationPendingTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(
            ref="IFD-PENDING", channel_ref="ifood", external_ref="ifood-order", status="new",
            data={"payment": {"method": "cash"}, "hold_ids": ["hold-a"]},
        )

    def request(self):
        return cancellation.cancel(self.order, reason="Sem estoque", actor="operator:ana")

    def directive(self):
        return Directive.objects.get(topic="ifood.status_callback", payload__order_ref=self.order.ref)

    def test_request_keeps_status_and_context_until_remote_confirmation(self):
        with patch.object(Order, "transition_status") as transition:
            self.assertTrue(self.request())
        transition.assert_not_called()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "new")
        self.assertNotIn("cancelled_by", self.order.data)
        self.assertNotIn("cancellation_reason", self.order.data)
        self.assertEqual(self.order.data["hold_ids"], ["hold-a"])
        self.assertEqual(self.order.data[ifood_cancellation.KEY]["state"], "queued")
        self.assertEqual(self.directive().payload["cancellation_code"], "501")

    def test_stale_second_request_dedupes_and_preserves_first_decision(self):
        stale = Order.objects.get(pk=self.order.pk)
        self.request()
        cancellation.cancel(stale, reason="Outro motivo", actor="operator:b")
        self.assertEqual(Directive.objects.filter(topic="ifood.status_callback").count(), 1)
        stale.refresh_from_db()
        self.assertEqual(stale.data[ifood_cancellation.KEY]["reason"], "Sem estoque")

    def test_reject_does_not_notify_customer_before_can(self):
        with patch.object(operator_orders, "_validate_operator_cancellation_code", return_value=("ifood", "ifood-order")):
            operator_orders.reject_order(self.order, reason="Sem estoque", actor="operator:a", rejected_by="a", cancellation_code="501")
        self.assertFalse(Directive.objects.filter(topic="notification.send").exists())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "new")

    def test_sent_waits_for_can_and_blocks_accept_and_advance(self):
        self.request()
        with patch.object(ifood_callbacks, "send_for_status", return_value=True) as send:
            IFoodStatusCallbackHandler().handle(message=self.directive(), ctx={})
            IFoodStatusCallbackHandler().handle(message=self.directive(), ctx={})
        send.assert_called_once()
        self.order.refresh_from_db()
        self.assertEqual(self.order.data[ifood_cancellation.KEY]["state"], "sent")
        self.assertEqual(self.order.status, "new")
        self.assertTrue(operator_orders.confirmation_block_reason(self.order))
        with self.assertRaises(operator_orders.OrderStateConflict):
            operator_orders.confirm_order(self.order, actor="operator:a")
        self.assertEqual(operator_orders.advance_block(self.order), operator_orders.AdvanceBlock.IFOOD_CANCELLATION_PENDING)

    def test_can_closes_order_and_prevents_stale_send(self):
        self.request()
        cancellation.cancel(self.order, reason="iFood confirmou", actor="system:ifood", extra_data={"ifood_cancelled": True})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(self.order.data[ifood_cancellation.KEY]["state"], "confirmed")
        with patch.object(ifood_callbacks, "send_for_status") as send:
            IFoodStatusCallbackHandler().handle(message=self.directive(), ctx={})
        send.assert_not_called()

    def test_can_during_network_call_is_not_overwritten_by_success(self):
        self.request()
        def remote_can(*args, **kwargs):
            cancellation.cancel(self.order, reason="iFood confirmou", actor="system:ifood", extra_data={"ifood_cancelled": True})
            return True
        with patch.object(ifood_callbacks, "send_for_status", side_effect=remote_can):
            IFoodStatusCallbackHandler().handle(message=self.directive(), ctx={})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(self.order.data[ifood_cancellation.KEY]["state"], "confirmed")

    def test_transient_failure_keeps_order_open_and_pending_without_raw_error(self):
        self.request()
        with patch.object(ifood_callbacks, "send_for_status", side_effect=ifood_callbacks.IFoodCallbackError("secret provider response")):
            with self.assertRaises(DirectiveTransientError) as raised:
                IFoodStatusCallbackHandler().handle(message=self.directive(), ctx={})
        self.order.refresh_from_db()
        self.assertTrue(ifood_cancellation.is_pending(self.order))
        self.assertEqual(self.order.status, "new")
        self.assertNotIn("secret", str(self.order.data))
        self.assertNotIn("secret", str(raised.exception))

    def test_definite_rejection_releases_gate_and_allows_a_new_request(self):
        self.request()
        old_payload = self.directive().payload
        with patch.object(ifood_callbacks, "send_for_status", side_effect=ifood_callbacks.IFoodCallbackError("bad code", retryable=False)):
            with self.assertRaises(DirectiveTerminalError):
                IFoodStatusCallbackHandler().handle(message=self.directive(), ctx={})
        self.order.refresh_from_db()
        self.assertFalse(ifood_cancellation.is_pending(self.order))
        self.assertEqual(self.order.status, "new")
        self.request()
        self.assertEqual(Directive.objects.filter(topic="ifood.status_callback").count(), 2)
        ifood_cancellation.record_result(old_payload, state="sent")
        self.order.refresh_from_db()
        self.assertEqual(self.order.data[ifood_cancellation.KEY]["state"], "queued")

    def test_removing_credentials_does_not_convert_pending_into_local_cancellation(self):
        self.request()
        with override_settings(SHOPMAN_IFOOD={}):
            self.request()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "new")

    def test_simulation_retains_local_lifecycle(self):
        self.order.external_ref = "IFOOD-SIM-ABC"
        self.order.save(update_fields=["external_ref"])
        self.request()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")

    @override_settings(SHOPMAN_IFOOD={})
    def test_missing_credentials_and_reason_do_not_cancel_real_order_locally(self):
        with self.assertRaisesMessage(ValueError, "Escolha um motivo"):
            self.request()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "new")
        self.assertEqual(self.order.data["hold_ids"], ["hold-a"])
        self.assertFalse(Directive.objects.filter(topic="ifood.status_callback").exists())

    @override_settings(SHOPMAN_IFOOD={})
    def test_missing_credentials_still_queue_remote_decision_with_explicit_reason(self):
        cancellation.cancel(
            self.order, reason="Sem estoque", actor="operator:a", extra_data={"ifood_cancellation_code": "501"},
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "new")
        self.assertTrue(ifood_cancellation.is_pending(self.order))
        self.assertEqual(self.directive().payload["cancellation_code"], "501")

    @override_settings(SHOPMAN_IFOOD={})
    def test_simulation_without_credentials_can_still_cancel_locally(self):
        self.order.external_ref = "IFOOD-SIM-ABC"
        self.order.save(update_fields=["external_ref"])
        self.request()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "cancelled")

    def test_http_failures_have_safe_retry_classification(self):
        for status, retryable in ((400, False), (403, False), (408, True), (429, True), (500, True)):
            with self.subTest(status=status), patch("shopman.shop.services.ifood_auth.authorized_headers", return_value={"Authorization": "token"}), patch("requests.post", return_value=MagicMock(status_code=status, text="secret response")):
                with self.assertRaises(ifood_callbacks.IFoodCallbackError) as raised:
                    ifood_callbacks.send_action("order", "requestCancellation")
                self.assertEqual(raised.exception.retryable, retryable)
                self.assertNotIn("secret", str(raised.exception))
