"""Tests for Payment signals — verify each signal fires with correct kwargs.

Os anúncios saem por ``transaction.on_commit`` (``PaymentService._announce``),
então todo teste que espera receber um sinal executa a ação dentro de
``captureOnCommitCallbacks(execute=True)``: é o COMMIT simulado. Fora dele o
callback fica pendurado na conexão e o receiver nunca é chamado — que é
exatamente o comportamento desejado quando a transação morre.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from django.db import transaction
from django.test import TestCase
from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService
from shopman.payman.signals import (
    payment_authorized,
    payment_cancelled,
    payment_captured,
    payment_failed,
    payment_refunded,
)


class PaymentSignalTests(TestCase):
    def test_payment_authorized_signal(self) -> None:
        handler = MagicMock()
        payment_authorized.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-A", 5000, "pix")
            with self.captureOnCommitCallbacks(execute=True):
                PaymentService.authorize(intent.ref)

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-A")
            self.assertEqual(kwargs["amount_q"], 5000)
            self.assertEqual(kwargs["method"], "pix")
            self.assertIsInstance(kwargs["intent"], PaymentIntent)
        finally:
            payment_authorized.disconnect(handler)

    def test_payment_captured_signal(self) -> None:
        handler = MagicMock()
        payment_captured.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-C", 8000, "card")
            PaymentService.authorize(intent.ref)
            with self.captureOnCommitCallbacks(execute=True):
                PaymentService.capture(intent.ref, amount_q=8000)

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-C")
            self.assertEqual(kwargs["amount_q"], 8000)
            self.assertIsInstance(kwargs["transaction"], PaymentTransaction)
        finally:
            payment_captured.disconnect(handler)

    def test_settle_emits_only_payment_captured(self) -> None:
        """Dinheiro não tem momento de autorização: o único fato é a captura."""
        captured = MagicMock()
        authorized = MagicMock()
        payment_captured.connect(captured)
        payment_authorized.connect(authorized)
        try:
            with self.captureOnCommitCallbacks(execute=True):
                PaymentService.settle("ORD-SIG-CASH", 3200, "cash")

            captured.assert_called_once()
            kwargs = captured.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-CASH")
            self.assertEqual(kwargs["amount_q"], 3200)
            self.assertIsInstance(kwargs["transaction"], PaymentTransaction)
            authorized.assert_not_called()
        finally:
            payment_captured.disconnect(captured)
            payment_authorized.disconnect(authorized)

    def test_payment_refunded_signal(self) -> None:
        handler = MagicMock()
        payment_refunded.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-R", 10000, "pix")
            PaymentService.authorize(intent.ref)
            PaymentService.capture(intent.ref)
            with self.captureOnCommitCallbacks(execute=True):
                PaymentService.refund(intent.ref, amount_q=4000)

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-R")
            self.assertEqual(kwargs["amount_q"], 4000)
            self.assertIsInstance(kwargs["transaction"], PaymentTransaction)
        finally:
            payment_refunded.disconnect(handler)

    def test_payment_cancelled_signal(self) -> None:
        handler = MagicMock()
        payment_cancelled.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-X", 5000, "pix")
            with self.captureOnCommitCallbacks(execute=True):
                PaymentService.cancel(intent.ref)

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-X")
            self.assertIsInstance(kwargs["intent"], PaymentIntent)
        finally:
            payment_cancelled.disconnect(handler)

    def test_payment_failed_signal(self) -> None:
        handler = MagicMock()
        payment_failed.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-F", 5000, "card")
            with self.captureOnCommitCallbacks(execute=True):
                PaymentService.fail(intent.ref, error_code="declined", message="Insufficient funds")

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-F")
            self.assertEqual(kwargs["error_code"], "declined")
            self.assertEqual(kwargs["message"], "Insufficient funds")
        finally:
            payment_failed.disconnect(handler)

    def test_multiple_refund_signals(self) -> None:
        """Each partial refund emits its own signal."""
        handler = MagicMock()
        payment_refunded.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-MR", 10000, "pix")
            PaymentService.authorize(intent.ref)
            PaymentService.capture(intent.ref)

            with self.captureOnCommitCallbacks(execute=True):
                PaymentService.refund(intent.ref, amount_q=3000)
                PaymentService.refund(intent.ref, amount_q=7000)

            self.assertEqual(handler.call_count, 2)
            amounts = [call[1]["amount_q"] for call in handler.call_args_list]
            self.assertEqual(sorted(amounts), [3000, 7000])
        finally:
            payment_refunded.disconnect(handler)


class PaymentSignalCommitBoundaryTests(TestCase):
    """O anúncio é do COMMIT, não da chamada.

    Os dois cenários são os do chamador real: o PDV abre um ``atomic`` em volta
    de ``settle_terminal_tenders`` + escrita da venda no livro do turno
    (``_settle_pos_sale`` em ``shopman/shop/services/pos.py``).
    """

    def test_rollback_does_not_announce_capture(self) -> None:
        """Transação que morre não deixa receiver agindo sobre dinheiro inexistente."""
        handler = MagicMock()
        payment_captured.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-RB", 4500, "pix")
            PaymentService.authorize(intent.ref)

            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(RuntimeError):
                    with transaction.atomic():
                        PaymentService.capture(intent.ref)
                        raise RuntimeError("a venda não pôde ser gravada")

            self.assertEqual(callbacks, [])
            handler.assert_not_called()
            reloaded = PaymentIntent.objects.get(ref=intent.ref)
            self.assertEqual(reloaded.status, PaymentIntent.Status.AUTHORIZED)
            self.assertEqual(PaymentService.captured_total(intent.ref), 0)
        finally:
            payment_captured.disconnect(handler)

    def test_raising_receiver_does_not_abort_capture(self) -> None:
        """Exceção de quem escuta não derruba quem cobra."""

        def boom(**kwargs):
            raise RuntimeError("receiver quebrado")

        payment_captured.connect(boom)
        try:
            intent = PaymentService.create_intent("ORD-SIG-BOOM", 7700, "card")
            PaymentService.authorize(intent.ref)

            with self.assertRaises(RuntimeError):
                with self.captureOnCommitCallbacks(execute=True):
                    PaymentService.capture(intent.ref)

            reloaded = PaymentIntent.objects.get(ref=intent.ref)
            self.assertEqual(reloaded.status, PaymentIntent.Status.CAPTURED)
            self.assertEqual(PaymentService.captured_total(intent.ref), 7700)
        finally:
            payment_captured.disconnect(boom)
