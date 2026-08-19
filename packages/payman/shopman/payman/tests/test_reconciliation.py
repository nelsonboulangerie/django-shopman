"""Gateway reconciliation contracts for Payman."""
from __future__ import annotations

from django.test import TestCase
from shopman.payman.exceptions import PaymentError
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService


class GatewayReconciliationTests(TestCase):
    def test_captured_snapshot_from_pending_authorizes_and_captures(self) -> None:
        intent = PaymentService.create_intent(
            "ORD-REC-CAP",
            10000,
            "card",
            ref="PAY-REC-CAP",
            gateway="stripe",
            gateway_id="pi_rec_cap",
        )

        result = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="succeeded",
            amount_q=10000,
            captured_q=10000,
            refunded_q=0,
            gateway_id="pi_rec_cap",
        )

        intent.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(result.actions, ("authorized", "captured"))
        self.assertEqual(intent.status, PaymentIntent.Status.CAPTURED)
        self.assertEqual(PaymentService.captured_total(intent.ref), 10000)
        self.assertEqual(PaymentTransaction.objects.filter(intent=intent).count(), 1)

        repeat = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="captured",
            amount_q=10000,
            captured_q=10000,
            refunded_q=0,
            gateway_id="pi_rec_cap",
        )
        self.assertFalse(repeat.changed)
        self.assertEqual(repeat.actions, ())
        self.assertEqual(PaymentTransaction.objects.filter(intent=intent).count(), 1)

    def test_cumulative_refunds_apply_only_new_delta(self) -> None:
        intent = PaymentService.create_intent(
            "ORD-REC-REF",
            10000,
            "card",
            ref="PAY-REC-REF",
            gateway="stripe",
            gateway_id="pi_rec_ref",
        )
        PaymentService.authorize(intent.ref, gateway_id="pi_rec_ref")
        PaymentService.capture(intent.ref, gateway_id="ch_rec_ref")

        first = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="refunded",
            amount_q=10000,
            captured_q=10000,
            refunded_q=3000,
            gateway_id="pi_rec_ref",
            refund_gateway_id="ch_rec_ref",
        )
        second = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="refunded",
            amount_q=10000,
            captured_q=10000,
            refunded_q=7000,
            gateway_id="pi_rec_ref",
            refund_gateway_id="ch_rec_ref",
        )
        repeat = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="refunded",
            amount_q=10000,
            captured_q=10000,
            refunded_q=7000,
            gateway_id="pi_rec_ref",
            refund_gateway_id="ch_rec_ref",
        )

        self.assertEqual(first.actions, ("refunded",))
        self.assertEqual(second.actions, ("refunded",))
        self.assertFalse(repeat.changed)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 7000)
        refunds = list(
            PaymentTransaction.objects.filter(
                intent=intent,
                type=PaymentTransaction.Type.REFUND,
            )
            .order_by("created_at")
            .values_list("amount_q", flat=True)
        )
        self.assertEqual(refunds, [3000, 4000])

    def test_rejects_gateway_refund_below_local_total(self) -> None:
        intent = PaymentService.create_intent("ORD-REC-LOW", 10000, "pix", ref="PAY-REC-LOW")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        PaymentService.refund(intent.ref, amount_q=5000)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="refunded",
                amount_q=10000,
                captured_q=10000,
                refunded_q=3000,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_refund_mismatch")

    def test_rejects_gateway_snapshot_that_omits_existing_refund(self) -> None:
        intent = PaymentService.create_intent("ORD-REC-ZERO", 10000, "pix", ref="PAY-REC-ZERO")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        PaymentService.refund(intent.ref, amount_q=1000)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="captured",
                amount_q=10000,
                captured_q=10000,
                refunded_q=0,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_refund_mismatch")

    def test_rejects_gateway_capture_after_local_cancel(self) -> None:
        intent = PaymentService.create_intent("ORD-REC-CANCEL", 5000, "pix", ref="PAY-REC-CANCEL")
        PaymentService.cancel(intent.ref)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="captured",
                amount_q=5000,
                captured_q=5000,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_terminal_drift")

    def test_cumulative_chargebacks_apply_only_new_delta(self) -> None:
        """Cartão: disputa parcial e depois total, snapshot cumulativo."""
        intent = PaymentService.create_intent(
            "ORD-REC-CB",
            10000,
            "card",
            ref="PAY-REC-CB",
            gateway="stripe",
            gateway_id="pi_rec_cb",
        )
        PaymentService.authorize(intent.ref, gateway_id="pi_rec_cb")
        PaymentService.capture(intent.ref, gateway_id="ch_rec_cb")

        first = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="captured",
            amount_q=10000,
            captured_q=10000,
            chargeback_q=4000,
            gateway_id="pi_rec_cb",
            chargeback_gateway_id="du_rec_cb",
        )
        second = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="captured",
            amount_q=10000,
            captured_q=10000,
            chargeback_q=10000,
            gateway_id="pi_rec_cb",
            chargeback_gateway_id="du_rec_cb",
        )
        repeat = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="captured",
            amount_q=10000,
            captured_q=10000,
            chargeback_q=10000,
            gateway_id="pi_rec_cb",
            chargeback_gateway_id="du_rec_cb",
        )

        self.assertEqual(first.actions, ("chargeback",))
        self.assertEqual(second.actions, ("chargeback",))
        self.assertFalse(repeat.changed)
        self.assertEqual(repeat.chargeback_q, 10000)
        self.assertEqual(PaymentService.chargeback_total(intent.ref), 10000)
        chargebacks = list(
            PaymentTransaction.objects.filter(
                intent=intent,
                type=PaymentTransaction.Type.CHARGEBACK,
            )
            .order_by("created_at")
            .values_list("amount_q", flat=True)
        )
        self.assertEqual(chargebacks, [4000, 6000])
        # O status é índice do que a LOJA fez; a disputa é ato de terceiro.
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentIntent.Status.CAPTURED)

    def test_pix_med_chargeback_registers_without_touching_refunds(self) -> None:
        """Pix/MED: a devolução especial entra como chargeback, não como reembolso."""
        intent = PaymentService.create_intent("ORD-REC-MED", 8000, "pix", ref="PAY-REC-MED", gateway="efi")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)

        result = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="captured",
            amount_q=8000,
            captured_q=8000,
            chargeback_q=8000,
            chargeback_gateway_id="med_rec_8000",
        )

        self.assertEqual(result.actions, ("chargeback",))
        self.assertEqual(result.chargeback_q, 8000)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 0)
        txn = PaymentTransaction.objects.get(intent=intent, type=PaymentTransaction.Type.CHARGEBACK)
        self.assertEqual(txn.gateway_id, "med_rec_8000")

    def test_chargeback_consumes_refundable_balance(self) -> None:
        """Dinheiro tomado pelo banco não pode ser estornado de novo."""
        intent = PaymentService.create_intent("ORD-REC-CB-BAL", 5000, "pix", ref="PAY-REC-CB-BAL")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="captured",
            amount_q=5000,
            captured_q=5000,
            chargeback_q=5000,
        )

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref, amount_q=1000)

        self.assertEqual(ctx.exception.code, "already_refunded")
        self.assertEqual(ctx.exception.context["chargeback_q"], 5000)

    def test_rejects_gateway_chargeback_below_local_total(self) -> None:
        """Monotonicidade no outro sentido: o gateway não desfaz o que já registramos."""
        intent = PaymentService.create_intent("ORD-REC-CB-LOW", 9000, "card", ref="PAY-REC-CB-LOW")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="captured",
            amount_q=9000,
            captured_q=9000,
            chargeback_q=6000,
        )

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="captured",
                amount_q=9000,
                captured_q=9000,
                chargeback_q=2000,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_chargeback_mismatch")

    def test_rejects_chargeback_when_gateway_captured_nothing(self) -> None:
        """Chargeback sem captura no próprio snapshot é aritmética impossível."""
        intent = PaymentService.create_intent("ORD-REC-CB-NOCAP", 7000, "card", ref="PAY-REC-CB-NOCAP")
        PaymentService.authorize(intent.ref)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="authorized",
                amount_q=7000,
                captured_q=0,
                chargeback_q=7000,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_chargeback_exceeds_capture")

    def test_rejects_chargeback_for_intent_without_local_capture(self) -> None:
        """Estado corrompido (captura no livro, status parado em autorizado).

        É o mesmo defeito que a reconciliação diária chama de
        ``open_intent_has_capture``; aqui o chargeback recusa em vez de
        empilhar devolução sobre um pagamento cuja captura ninguém confirmou.
        """
        intent = PaymentService.create_intent("ORD-REC-CB-DRIFT", 7000, "card", ref="PAY-REC-CB-DRIFT")
        PaymentService.authorize(intent.ref)
        PaymentTransaction.objects.create(
            intent=intent,
            type=PaymentTransaction.Type.CAPTURE,
            amount_q=7000,
            gateway_id="ch_rec_cb_drift",
        )

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="authorized",
                amount_q=7000,
                captured_q=7000,
                chargeback_q=7000,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_chargeback_drift")

    def test_rejects_refund_plus_chargeback_above_capture(self) -> None:
        intent = PaymentService.create_intent("ORD-REC-CB-OVER", 6000, "card", ref="PAY-REC-CB-OVER")
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.reconcile_gateway_status(
                intent.ref,
                gateway_status="refunded",
                amount_q=6000,
                captured_q=6000,
                refunded_q=4000,
                chargeback_q=4000,
            )

        self.assertEqual(ctx.exception.code, "reconciliation_chargeback_exceeds_capture")

    def test_cancelled_snapshot_cancels_unpaid_intent(self) -> None:
        intent = PaymentService.create_intent("ORD-REC-GW-CANCEL", 5000, "pix", ref="PAY-REC-GW-CANCEL")
        PaymentService.authorize(intent.ref)

        result = PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="cancelled",
            amount_q=5000,
            captured_q=0,
            refunded_q=0,
        )

        intent.refresh_from_db()
        self.assertEqual(result.actions, ("cancelled",))
        self.assertEqual(intent.status, PaymentIntent.Status.CANCELLED)
        self.assertEqual(intent.cancel_reason, "gateway_reconciliation")
