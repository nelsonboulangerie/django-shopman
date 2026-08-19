"""
HP2-06 Hardening tests — 4 drift fixes.

1. get_active_intent() excludes expired intents.
2. gateway_id unique constraint (gateway, gateway_id) WHERE gateway_id != ''.
3. PaymentTransaction QuerySet mutation guards.
4. cancel() reason persisted to cancel_reason field.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from shopman.payman.exceptions import PaymentError
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService


def _make_intent(ref: str, **kwargs) -> PaymentIntent:
    return PaymentService.create_intent(f"ORD-{ref}", 5000, "pix", ref=f"PAY-{ref}", **kwargs)


# ---------------------------------------------------------------------------
# Fix 1 — get_active_intent() excludes expired intents
# ---------------------------------------------------------------------------

class GetActiveIntentExpiryTests(TestCase):
    """get_active_intent() must not return expired intents, even if non-terminal."""

    def test_active_intent_without_expiry_returned(self) -> None:
        _make_intent("ACT-NOEXP")
        result = PaymentService.get_active_intent("ORD-ACT-NOEXP")
        self.assertIsNotNone(result)

    def test_active_intent_with_future_expiry_returned(self) -> None:
        future = timezone.now() + timedelta(minutes=30)
        _make_intent("ACT-FUTEXP", expires_at=future)
        result = PaymentService.get_active_intent("ORD-ACT-FUTEXP")
        self.assertIsNotNone(result)

    def test_expired_intent_not_returned(self) -> None:
        past = timezone.now() - timedelta(seconds=1)
        _make_intent("ACT-PASTEXP", expires_at=past)
        result = PaymentService.get_active_intent("ORD-ACT-PASTEXP")
        self.assertIsNone(result)

    def test_expired_intent_ignored_even_if_pending(self) -> None:
        """PENDING + expired must not be returned (previously it would be)."""
        past = timezone.now() - timedelta(hours=1)
        intent = _make_intent("ACT-PENDEXP", expires_at=past)
        self.assertEqual(intent.status, PaymentIntent.Status.PENDING)

        result = PaymentService.get_active_intent("ORD-ACT-PENDEXP")
        self.assertIsNone(result)

    def test_fresh_intent_returned_when_expired_one_also_exists(self) -> None:
        """The non-expired intent wins over the expired one for the same order."""
        past = timezone.now() - timedelta(hours=1)
        PaymentService.create_intent("ORD-ACT-MIXED", 5000, "pix", ref="PAY-OLD-EXP", expires_at=past)
        PaymentService.create_intent("ORD-ACT-MIXED", 5000, "pix", ref="PAY-NEW-OK")

        result = PaymentService.get_active_intent("ORD-ACT-MIXED")
        self.assertIsNotNone(result)
        self.assertEqual(result.ref, "PAY-NEW-OK")

    def test_terminal_status_still_excluded(self) -> None:
        """Cancelled intent still excluded (terminal, regardless of expiry)."""
        intent = _make_intent("ACT-TERM")
        PaymentService.cancel(intent.ref)
        self.assertIsNone(PaymentService.get_active_intent("ORD-ACT-TERM"))


# ---------------------------------------------------------------------------
# Fix 2 — gateway_id unique constraint
# ---------------------------------------------------------------------------

class GatewayIdUniqueTests(TestCase):
    """UniqueConstraint(gateway, gateway_id) WHERE gateway_id != '' prevents duplicates."""

    def test_same_gateway_id_same_gateway_raises(self) -> None:
        PaymentService.create_intent(
            "ORD-GW-A", 5000, "pix", ref="PAY-GW-A",
            gateway="efi", gateway_id="txid_001",
        )
        with self.assertRaises((IntegrityError, Exception)):
            with transaction.atomic():
                PaymentService.create_intent(
                    "ORD-GW-B", 5000, "pix", ref="PAY-GW-B",
                    gateway="efi", gateway_id="txid_001",
                )

    def test_same_gateway_id_different_gateway_allowed(self) -> None:
        PaymentService.create_intent(
            "ORD-GW-C", 5000, "pix", ref="PAY-GW-C",
            gateway="efi", gateway_id="txid_shared",
        )
        intent2 = PaymentService.create_intent(
            "ORD-GW-D", 5000, "pix", ref="PAY-GW-D",
            gateway="stripe", gateway_id="txid_shared",
        )
        self.assertEqual(intent2.gateway_id, "txid_shared")

    def test_get_by_gateway_id_can_scope_by_gateway(self) -> None:
        efi = PaymentService.create_intent(
            "ORD-GW-I", 5000, "pix", ref="PAY-GW-I",
            gateway="efi", gateway_id="txid_lookup",
        )
        stripe = PaymentService.create_intent(
            "ORD-GW-J", 5000, "card", ref="PAY-GW-J",
            gateway="stripe", gateway_id="txid_lookup",
        )

        self.assertEqual(PaymentService.get_by_gateway_id("txid_lookup", gateway="efi"), efi)
        self.assertEqual(PaymentService.get_by_gateway_id("txid_lookup", gateway="stripe"), stripe)

    def test_empty_gateway_id_allows_duplicates(self) -> None:
        """Constraint is conditional: empty gateway_id rows are not constrained."""
        PaymentService.create_intent("ORD-GW-E", 5000, "pix", ref="PAY-GW-E", gateway="efi")
        intent2 = PaymentService.create_intent("ORD-GW-F", 5000, "pix", ref="PAY-GW-F", gateway="efi")
        self.assertEqual(intent2.gateway_id, "")

    def test_different_gateway_id_same_gateway_allowed(self) -> None:
        PaymentService.create_intent(
            "ORD-GW-G", 5000, "pix", ref="PAY-GW-G",
            gateway="efi", gateway_id="txid_111",
        )
        intent2 = PaymentService.create_intent(
            "ORD-GW-H", 5000, "pix", ref="PAY-GW-H",
            gateway="efi", gateway_id="txid_222",
        )
        self.assertEqual(intent2.gateway_id, "txid_222")


# ---------------------------------------------------------------------------
# Fix 3 — PaymentTransaction QuerySet.update() guard
# ---------------------------------------------------------------------------

class TransactionQuerySetGuardTests(TestCase):
    """PaymentTransaction.objects.update() must raise to protect immutability."""

    def setUp(self) -> None:
        intent = PaymentService.create_intent("ORD-TXN-GUARD", 10000, "pix", ref="PAY-TXN-GUARD")
        PaymentService.authorize(intent.ref)
        self.txn = PaymentService.capture(intent.ref)

    def test_update_via_queryset_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            PaymentTransaction.objects.filter(pk=self.txn.pk).update(amount_q=1)
        self.assertIn("imutáv", str(ctx.exception).lower())

    def test_update_all_raises(self) -> None:
        with self.assertRaises(ValueError):
            PaymentTransaction.objects.update(gateway_id="tampered")

    def test_delete_via_queryset_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            PaymentTransaction.objects.filter(pk=self.txn.pk).delete()
        self.assertIn("imutáv", str(ctx.exception).lower())

    def test_save_on_existing_raises(self) -> None:
        """save() on an existing record is also guarded."""
        self.txn.gateway_id = "tampered"
        with self.assertRaises(ValueError):
            self.txn.save()

    def test_create_still_works(self) -> None:
        """objects.create() goes through save() (pk=None) — must still work."""
        intent = PaymentService.get("PAY-TXN-GUARD")
        txn = PaymentTransaction.objects.create(
            intent=intent, type="refund", amount_q=5000,
        )
        self.assertIsNotNone(txn.pk)


# ---------------------------------------------------------------------------
# Fix 4 — cancel() reason persisted
# ---------------------------------------------------------------------------

class CancelReasonTests(TestCase):
    """cancel(reason=...) must persist the reason to intent.cancel_reason."""

    def test_cancel_reason_persisted(self) -> None:
        intent = _make_intent("CANC-RSN-1")
        PaymentService.cancel(intent.ref, reason="customer_requested")

        intent.refresh_from_db()
        self.assertEqual(intent.cancel_reason, "customer_requested")

    def test_cancel_without_reason_stores_empty_string(self) -> None:
        intent = _make_intent("CANC-RSN-2")
        PaymentService.cancel(intent.ref)

        intent.refresh_from_db()
        self.assertEqual(intent.cancel_reason, "")

    def test_cancel_reason_field_exists_on_model(self) -> None:
        intent = _make_intent("CANC-RSN-3")
        self.assertTrue(hasattr(intent, "cancel_reason"))
        self.assertEqual(intent.cancel_reason, "")

    def test_cancel_reason_readable_after_cancel(self) -> None:
        intent = _make_intent("CANC-RSN-4")
        result = PaymentService.cancel(intent.ref, reason="payment_gateway_timeout")
        result.refresh_from_db()
        self.assertEqual(result.cancel_reason, "payment_gateway_timeout")

    def test_cancel_reason_accepts_gateway_diagnostic_context(self) -> None:
        reason = "x" * 500
        intent = _make_intent("CANC-RSN-LONG")
        PaymentService.cancel(intent.ref, reason=reason)

        intent.refresh_from_db()
        self.assertEqual(intent.cancel_reason, reason)

    def test_cancel_reason_stored_from_authorized_status(self) -> None:
        """cancel() from AUTHORIZED status also persists the reason."""
        intent = _make_intent("CANC-RSN-5")
        PaymentService.authorize(intent.ref)
        PaymentService.cancel(intent.ref, reason="fraud_detected")

        intent.refresh_from_db()
        self.assertEqual(intent.cancel_reason, "fraud_detected")


# ---------------------------------------------------------------------------
# Fix 5 — refund(reason=...) persistido na transação
# ---------------------------------------------------------------------------

class RefundReasonTests(TestCase):
    """O motivo do reembolso não pode morar só no log.

    Cancelamento é dinheiro que não entrou; reembolso é dinheiro que SAIU — a
    operação sobre a qual auditoria e contador perguntam "por quê". O motivo
    fica na própria linha imutável, ao lado do valor.
    """

    def _captured(self, ref: str) -> PaymentIntent:
        intent = _make_intent(ref)
        PaymentService.authorize(intent.ref)
        PaymentService.capture(intent.ref)
        return intent

    def test_refund_reason_persisted_on_transaction(self) -> None:
        intent = self._captured("REF-RSN-1")
        txn = PaymentService.refund(intent.ref, amount_q=1000, reason="item danificado")

        txn.refresh_from_db()
        self.assertEqual(txn.reason, "item danificado")

    def test_refund_without_reason_stores_empty_string(self) -> None:
        intent = self._captured("REF-RSN-2")
        txn = PaymentService.refund(intent.ref, amount_q=1000)

        txn.refresh_from_db()
        self.assertEqual(txn.reason, "")

    def test_each_partial_refund_keeps_its_own_reason(self) -> None:
        intent = self._captured("REF-RSN-3")
        PaymentService.refund(intent.ref, amount_q=1000, reason="pão queimado")
        PaymentService.refund(intent.ref, amount_q=2000, reason="entrega atrasada")

        reasons = list(
            PaymentTransaction.objects.filter(
                intent=intent, type=PaymentTransaction.Type.REFUND
            )
            .order_by("created_at")
            .values_list("reason", flat=True)
        )
        self.assertEqual(reasons, ["pão queimado", "entrega atrasada"])

    def test_refund_reason_survives_the_immutability_guard(self) -> None:
        """A linha é imutável, e o motivo com ela: não há caminho para reescrever."""
        intent = self._captured("REF-RSN-4")
        txn = PaymentService.refund(intent.ref, amount_q=1000, reason="troco errado")

        with self.assertRaises(ValueError):
            PaymentTransaction.objects.filter(pk=txn.pk).update(reason="outra história")

        txn.refresh_from_db()
        self.assertEqual(txn.reason, "troco errado")

    def test_reconciled_refund_records_its_origin(self) -> None:
        """Reembolso que veio do snapshot do gateway diz de onde veio."""
        intent = self._captured("REF-RSN-5")
        PaymentService.reconcile_gateway_status(
            intent.ref,
            gateway_status="refunded",
            amount_q=5000,
            captured_q=5000,
            refunded_q=5000,
            refund_gateway_id="re_rsn_5",
        )

        txn = PaymentTransaction.objects.get(intent=intent, type=PaymentTransaction.Type.REFUND)
        self.assertEqual(txn.reason, "gateway_reconciliation")


# ---------------------------------------------------------------------------
# Fix 6 — refund(idempotency_key=...) para estorno sem gateway
# ---------------------------------------------------------------------------

class RefundIdempotencyKeyTests(TestCase):
    """Estorno de dinheiro não tem gateway_id — e mesmo assim pode repetir.

    A dedupe do refund era só por ``gateway_id``, que o estorno de balcão nunca
    tem (``""``). Dois disparos (retry de rede, duplo clique que escape do
    guard de UI) criavam DUAS devoluções enquanto houvesse saldo.
    """

    def _captured(self, ref: str, amount_q: int = 5000) -> PaymentIntent:
        intent = PaymentService.settle(f"ORD-{ref}", amount_q, "cash", ref=f"PAY-{ref}")
        return intent

    def test_same_key_twice_refunds_once(self) -> None:
        intent = self._captured("IDEM-1")

        first = PaymentService.refund(intent.ref, amount_q=2000, idempotency_key="order-refund:IDEM-1")
        second = PaymentService.refund(intent.ref, amount_q=2000, idempotency_key="order-refund:IDEM-1")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            PaymentTransaction.objects.filter(intent=intent, type=PaymentTransaction.Type.REFUND).count(),
            1,
        )
        self.assertEqual(PaymentService.refunded_total(intent.ref), 2000)

    def test_without_key_two_calls_still_refund_twice(self) -> None:
        """Sem chave não há o que deduplicar: o contrato exige que o chamador a passe."""
        intent = self._captured("IDEM-2")

        PaymentService.refund(intent.ref, amount_q=1000)
        PaymentService.refund(intent.ref, amount_q=1000)

        self.assertEqual(PaymentService.refunded_total(intent.ref), 2000)

    def test_key_reused_with_other_amount_is_refused(self) -> None:
        intent = self._captured("IDEM-3")
        PaymentService.refund(intent.ref, amount_q=1000, idempotency_key="order-refund:IDEM-3")

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(intent.ref, amount_q=2500, idempotency_key="order-refund:IDEM-3")

        self.assertEqual(ctx.exception.code, "idempotency_key_conflict")
        self.assertIn("amount_q", ctx.exception.context["mismatched"])
        self.assertEqual(PaymentService.refunded_total(intent.ref), 1000)

    def test_key_reused_on_another_intent_is_refused(self) -> None:
        first = self._captured("IDEM-4A")
        second = self._captured("IDEM-4B")
        PaymentService.refund(first.ref, amount_q=1000, idempotency_key="order-refund:IDEM-4")

        with self.assertRaises(PaymentError) as ctx:
            PaymentService.refund(second.ref, amount_q=1000, idempotency_key="order-refund:IDEM-4")

        self.assertEqual(ctx.exception.code, "idempotency_key_conflict")
        self.assertIn("intent_ref", ctx.exception.context["mismatched"])
        self.assertEqual(PaymentService.refunded_total(second.ref), 0)

    def test_key_uniqueness_is_enforced_by_the_database(self) -> None:
        """A trava final é constraint, não o if do service."""
        intent = self._captured("IDEM-5")
        PaymentService.refund(intent.ref, amount_q=1000, idempotency_key="order-refund:IDEM-5")

        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentTransaction.objects.create(
                intent=intent,
                type=PaymentTransaction.Type.REFUND,
                amount_q=1000,
                idempotency_key="order-refund:IDEM-5",
            )

    def test_full_refund_retry_matches_without_explicit_amount(self) -> None:
        """Retry do cancel (estorno total, sem amount_q) devolve a mesma transação."""
        intent = self._captured("IDEM-6")

        first = PaymentService.refund(intent.ref, idempotency_key="order-refund:IDEM-6")
        second = PaymentService.refund(intent.ref, idempotency_key="order-refund:IDEM-6")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PaymentService.refunded_total(intent.ref), 5000)
