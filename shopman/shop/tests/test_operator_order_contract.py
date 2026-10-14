"""Operational contract guardrails for order mutations."""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Directive, Order

from shopman.shop.services.cancel_reasons import cancel_reason
from shopman.shop.services.cancellation import cancel
from shopman.shop.services.operator_orders import cancel_order, reject_order


def _order(ref: str, status: str) -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"session-{ref}",
        status=status,
        total_q=1500,
        snapshot={"items": [{"sku": "PAO", "qty": 1}], "data": {}},
        data={
            "customer": {"name": "Cliente"},
            "fulfillment_type": "pickup",
            "payment": {"method": "cash"},
        },
    )


class OperatorOrderContractTests(TestCase):
    def test_reject_uses_canonical_notification_contract(self) -> None:
        order = _order("CONTRACT-REJECT-NEW", Order.Status.NEW)

        reject_order(
            order,
            reason="sem estoque",
            actor="operator:ana",
            rejected_by="ana",
        )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        directive = Directive.objects.get(topic="notification.send", payload__order_ref=order.ref)
        self.assertEqual(directive.payload["template"], "order_rejected")
        self.assertEqual(directive.payload["reason"], "sem estoque")
        self.assertEqual(directive.payload["rejected_by"], "ana")
        self.assertTrue(directive.payload["requires_active_notification"])
        self.assertEqual(directive.dedupe_key, f"notification.send:{order.ref}:order_rejected")

    def test_reject_is_not_a_late_stage_cancel_shortcut(self) -> None:
        order = _order("CONTRACT-REJECT-CONF", Order.Status.ACCEPTED)

        with self.assertRaises(ValueError):
            reject_order(
                order,
                reason="sem estoque",
                actor="operator:ana",
                rejected_by="ana",
            )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ACCEPTED)
        self.assertNotIn("cancellation_reason", order.data)
        self.assertNotIn("rejected_by", order.data)

    def test_cancel_does_not_mutate_orders_that_cannot_transition_to_cancelled(self) -> None:
        for status in (
            Order.Status.READY,
            Order.Status.DISPATCHED,
            Order.Status.DELIVERED,
            Order.Status.COMPLETED,
            Order.Status.RETURNED,
        ):
            with self.subTest(status=str(status)):
                order = _order(f"CONTRACT-CANCEL-{status}", status)

                changed = cancel(order, reason="operator_requested", actor="operator:ana")

                self.assertFalse(changed)
                order.refresh_from_db()
                self.assertEqual(order.status, status)
                self.assertNotIn("cancellation_reason", order.data)
                self.assertNotIn("cancelled_by", order.data)

    def test_cancel_still_applies_when_status_allows_cancellation(self) -> None:
        order = _order("CONTRACT-CANCEL-PREPARING", Order.Status.PREPARING)

        changed = cancel(order, reason="operator_requested", actor="operator:ana")

        self.assertTrue(changed)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.data["cancellation_reason"], "operator_requested")


class CancellationReasonReachesCustomerTests(TestCase):
    """G2: the operator's justification must reach the customer, not a generic notice."""

    def _cancelled_notifications(self, order_ref: str):
        return list(
            Directive.objects.filter(
                topic="notification.send",
                payload__order_ref=order_ref,
                payload__template="order_cancelled",
            )
        )

    def test_operator_cancel_sends_the_reviewed_text_of_the_reason_key(self) -> None:
        order = _order("CONTRACT-CANCEL-REASON", Order.Status.PREPARING)

        with self.captureOnCommitCallbacks(execute=True):
            cancel_order(
                order,
                reason="Acabou um item",
                actor="operator:ana",
                reason_key="out_of_stock",
                internal_note="Faltou farinha",
            )

        order.refresh_from_db()
        self.assertEqual(order.data["cancellation_reason_key"], "out_of_stock")
        self.assertEqual(order.data["cancellation_internal_note"], "Faltou farinha")
        self.assertNotIn("cancellation_note", order.data)
        notes = self._cancelled_notifications(order.ref)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].payload["status_note"], cancel_reason("out_of_stock").customer_text)
        self.assertNotIn("Faltou farinha", str(notes[0].payload))

    def test_operator_cancel_rejects_a_key_outside_the_list(self) -> None:
        order = _order("CONTRACT-CANCEL-BADKEY", Order.Status.PREPARING)

        with self.assertRaises(ValueError):
            cancel_order(order, reason="x", actor="operator:ana", reason_key="acabou")

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PREPARING)

    def test_machine_cancellations_get_a_key_and_never_leak_the_code(self) -> None:
        # Os caminhos automáticos gravam um código de máquina em cancellation_reason;
        # o cliente lê o texto da chave correspondente, nunca "pix_timeout".
        cases = {
            "payment_timeout": "payment_deadline_passed",
            "pix_timeout": "pix_expired",
            "customer_requested": "customer_request",
            "pos_operator": "other",
        }
        for machine_reason, key in cases.items():
            with self.subTest(machine_reason=machine_reason):
                order = _order(f"CONTRACT-CANCEL-{machine_reason}", Order.Status.NEW)

                with self.captureOnCommitCallbacks(execute=True):
                    cancel(order, reason=machine_reason, actor="system")

                order.refresh_from_db()
                self.assertEqual(order.data["cancellation_reason_key"], key)
                notes = self._cancelled_notifications(order.ref)
                self.assertEqual(len(notes), 1)
                self.assertEqual(notes[0].payload["status_note"], cancel_reason(key).customer_text)
                self.assertNotIn(machine_reason, str(notes[0].payload.get("status_note")))

    def test_reject_does_not_also_send_a_generic_cancelled_notification(self) -> None:
        # reject_order queues order_rejected (with the reason). The CANCELLED
        # transition must not double-notify with a generic order_cancelled.
        order = _order("CONTRACT-REJECT-NODUP", Order.Status.NEW)

        with self.captureOnCommitCallbacks(execute=True):
            reject_order(order, reason="Sem estoque", actor="operator:ana", rejected_by="ana")

        self.assertEqual(self._cancelled_notifications(order.ref), [])
        rejected = Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="order_rejected",
        )
        self.assertEqual(rejected.count(), 1)
        self.assertEqual(rejected.first().payload.get("reason"), "Sem estoque")
