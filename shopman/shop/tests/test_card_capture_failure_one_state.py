"""Cartão autorizado cuja cobrança falha DEPOIS do aceite.

Beta 06/11: a captura no aceite foi recusada e cliente e Gestor viam estados
contraditórios ("Cartão autorizado" de um lado, "Autorizado" + "Aguardando
pagamento · link gerado" do outro).

Decisão do dono (07/11/2026): "pede pra pagar de novo, pedido deveria ficar em
standby, transparente para operadores, só segue assim que o pagamento for
confirmado". Aqui, de ponta a ponta:

- a captura falha → a autorização velha é anulada no Stripe e nasce uma
  cobrança nova, com prazo; o pedido fica aceito, fora da cozinha;
- o cliente lê por que paga de novo; o Gestor lê "Aguardando novo pagamento";
- o pagamento novo confirma → o pedido segue sozinho do aceite para o preparo;
- o prazo vence sem pagamento → cancela pelo motivo canônico, com texto honesto;
- a anulação falha → nada novo nasce (duas reservas no cartão é pior), e o
  pedido fica em "Cobrança recusada" com o cancelar pronto.

Stripe dublado no SDK: nenhuma chamada de rede.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.shop.models import Channel
from shopman.shop.tests.test_card_settles_without_the_customer import STRIPE_MANUAL
from shopman.shop.tests.test_stripe_checkout_session import (
    PAYMENT_ADAPTERS_STRIPE_CARD,
    _commit_card_order,
)


class FakeStripe:
    """SDK do Stripe com uma sessão por cobrança e captura recusada sob comando."""

    def __init__(self) -> None:
        self.sessions: dict[str, MagicMock] = {}
        self.pi_status: dict[str, str] = {}
        self.capture_refused: set[str] = set()
        self.cancel_raises = False
        self.cancelled: list[str] = []
        outer = self

        class _Session:
            @staticmethod
            def create(**kwargs):
                n = len(outer.sessions) + 1
                session = MagicMock()
                session.id = f"cs_test_{n}"
                session.url = f"https://checkout.stripe.com/c/pay/cs_test_{n}"
                session.payment_intent = None
                session.status = "open"
                outer.sessions[session.id] = session
                return session

            @staticmethod
            def retrieve(sid):
                return outer.sessions[sid]

            @staticmethod
            def expire(sid):
                outer.sessions[sid].status = "expired"
                return outer.sessions[sid]

        class _Checkout:
            Session = _Session

        def _pi(pid: str):
            pi = MagicMock()
            pi.id = pid
            pi.status = outer.pi_status.get(pid, "requires_payment_method")
            pi.amount_received = 1000 if pi.status == "succeeded" else 0
            pi.latest_charge = None
            pi.last_payment_error = None
            return pi

        class _PaymentIntent:
            @staticmethod
            def retrieve(pid, **kwargs):
                return _pi(pid)

            @staticmethod
            def capture(pid, **kwargs):
                if pid in outer.capture_refused:
                    raise RuntimeError("charge_expired_for_capture")
                outer.pi_status[pid] = "succeeded"
                return _pi(pid)

            @staticmethod
            def cancel(pid, **kwargs):
                if outer.cancel_raises:
                    raise RuntimeError("stripe indisponível")
                outer.cancelled.append(pid)
                outer.pi_status[pid] = "canceled"
                return _pi(pid)

        self.checkout = _Checkout
        self.PaymentIntent = _PaymentIntent

    def complete_checkout(self, session_id: str, pi_id: str) -> None:
        """O cliente concluiu o cartão no Stripe: a sessão aponta o PaymentIntent autorizado."""
        session = self.sessions[session_id]
        session.status = "complete"
        session.payment_intent = pi_id
        self.pi_status[pi_id] = "requires_capture"


@override_settings(
    SHOPMAN_STRIPE=STRIPE_MANUAL,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
    DEBUG=False,
)
class CardCaptureFailsAfterAcceptTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Channel.objects.get_or_create(
            ref="web",
            defaults={
                "name": "Loja online",
                "is_active": True,
                "config": {
                    "confirmation": {"mode": "manual"},
                    "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 30},
                },
            },
        )
        self.stripe = FakeStripe()
        from shopman.shop.adapters import payment_stripe

        patcher = patch.object(payment_stripe, "_get_stripe", return_value=self.stripe)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ── helpers ──

    def _authorize(self, order: Order, *, session_id: str, pi_id: str) -> str:
        from shopman.shop.webhooks.stripe import StripeWebhookView

        intent_ref = order.data["payment"]["intent_ref"]
        self.stripe.complete_checkout(session_id, pi_id)
        PaymentService.authorize(intent_ref, gateway_id=pi_id)
        with self.captureOnCommitCallbacks(execute=True):
            StripeWebhookView()._trigger_order_hooks(intent_ref)
        order.refresh_from_db()
        return intent_ref

    def _accepted_with_failed_capture(self) -> tuple[Order, str]:
        with self.captureOnCommitCallbacks(execute=True):
            order = _commit_card_order()
        order.refresh_from_db()
        old_intent = self._authorize(order, session_id="cs_test_1", pi_id="pi_test_1")
        self.assertEqual(order.status, Order.Status.NEW)
        self.stripe.capture_refused.add("pi_test_1")
        with self.assertLogs("shopman.shop.services.payment", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                order.transition_status(Order.Status.ACCEPTED, actor="operator")
        order.refresh_from_db()
        return order, old_intent

    # ── a espera ──

    def test_a_failed_capture_puts_the_order_on_hold_with_a_new_charge(self) -> None:
        from shopman.shop.services import operator_orders
        from shopman.shop.services import payment as payment_service

        order, old_intent = self._accepted_with_failed_capture()

        self.assertEqual(order.status, Order.Status.ACCEPTED)
        # A reserva velha saiu do cartão do cliente.
        self.assertIn("pi_test_1", self.stripe.cancelled)
        self.assertEqual(PaymentIntent.objects.get(ref=old_intent).status, "cancelled")
        # Uma cobrança nova, aberta e com prazo.
        payment = order.data["payment"]
        self.assertNotEqual(payment["intent_ref"], old_intent)
        self.assertEqual(PaymentIntent.objects.get(ref=payment["intent_ref"]).status, "pending")
        self.assertTrue(payment["checkout_url"].endswith("cs_test_2"))
        self.assertTrue(payment.get("expires_at"))
        self.assertIsNotNone(payment_service.awaiting_repayment(order))
        self.assertTrue(
            Directive.objects.filter(topic="payment.timeout", payload__intent_ref=payment["intent_ref"]).exists()
        )
        # Em espera: nada vai para a cozinha nem avança.
        self.assertEqual(operator_orders.advance_block(order), operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED)
        self.assertFalse(order.data.get("kds_dispatched_at"))
        # O pedido de novo pagamento sai ao cliente, e o histórico conta o que houve.
        self.assertTrue(
            Directive.objects.filter(topic="notification.send", payload__template="payment_requested").exists()
        )
        self.assertTrue(order.events.filter(type="payment.capture_failed").exists())
        self.assertTrue(order.events.filter(type="payment.repayment_requested").exists())

    def test_the_customer_is_asked_to_pay_again_with_the_deadline(self) -> None:
        from shopman.storefront.presentation.order_tracking import build_order_tracking

        order, _ = self._accepted_with_failed_capture()
        promise = build_order_tracking(order).promise
        self.assertEqual(promise.state, "payment_card_ready")
        self.assertEqual(promise.title, "A cobrança no cartão não passou")
        self.assertTrue(promise.message.startswith("Nada foi cobrado. Pague com outro cartão até "))
        self.assertIn(" às ", promise.message)
        self.assertEqual(promise.checkout_url, order.data["payment"]["checkout_url"])
        self.assertTrue(any(action.href == promise.checkout_url for action in promise.actions))

    def test_the_gestor_reads_awaiting_new_payment(self) -> None:
        from django.contrib.auth import get_user_model

        from shopman.backstage.projections.order_queue import (
            AWAITING_REPAYMENT_LABEL,
            build_operator_order,
            build_order_card,
        )

        order, _ = self._accepted_with_failed_capture()
        user = get_user_model().objects.create_superuser("gestor", "g@example.com", "x")
        for projection in (build_operator_order(order, user=user), build_order_card(order, user=user)):
            self.assertEqual(projection.payment_status_label, AWAITING_REPAYMENT_LABEL)
            self.assertEqual(projection.advance_block_label, AWAITING_REPAYMENT_LABEL)
            self.assertIn("nada foi cobrado", projection.advance_block_reason)
            self.assertIn("vence às", projection.advance_block_reason)
            # O cancelar pronto não é o caminho principal: a espera resolve sozinha.
            self.assertFalse(projection.payment_lapsed)

    # ── o pagamento novo confirma: segue sozinho ──

    def test_the_new_payment_resumes_the_order_into_preparation(self) -> None:
        from shopman.shop.services import operator_orders
        from shopman.shop.services import payment as payment_service

        order, _ = self._accepted_with_failed_capture()
        self._authorize(order, session_id="cs_test_2", pi_id="pi_test_2")

        self.assertIs(payment_service.has_sufficient_captured_payment(order), True)
        self.assertIsNone(payment_service.awaiting_repayment(order))
        self.assertNotEqual(operator_orders.advance_block(order), operator_orders.AdvanceBlock.PAYMENT_NOT_CAPTURED)
        self.assertTrue(order.events.filter(type="payment.captured").exists())
        self.assertIn(order.status, {Order.Status.ACCEPTED, Order.Status.PREPARING})
        if order.status == Order.Status.ACCEPTED:
            self.assertEqual(operator_orders.next_status_for(order), Order.Status.PREPARING)

    # ── o prazo vence sem pagamento ──

    def test_an_unpaid_new_charge_cancels_at_the_deadline_honestly(self) -> None:
        from shopman.shop.handlers.payment_timeout import PaymentTimeoutHandler
        from shopman.shop.services import cancel_reasons
        from shopman.storefront.presentation.order_tracking import build_order_tracking

        order, _ = self._accepted_with_failed_capture()
        new_intent = order.data["payment"]["intent_ref"]
        directive = Directive.objects.get(topic="payment.timeout", payload__intent_ref=new_intent)
        directive.payload = {**directive.payload, "expires_at": (timezone.now() - timedelta(minutes=1)).isoformat()}
        directive.save(update_fields=["payload"])
        self.stripe.sessions["cs_test_2"].status = "expired"

        with self.captureOnCommitCallbacks(execute=True):
            PaymentTimeoutHandler().handle(message=directive, ctx={})
        order.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CANCELLED)
        text = cancel_reasons.customer_text(order.data)
        self.assertIn("nada foi cobrado", text)
        tracking = build_order_tracking(order)
        self.assertEqual(tracking.promise.state, "payment_expired")
        self.assertIn("nada foi cobrado", tracking.cancellation_money_line)

    # ── a anulação falha: nada novo nasce ──

    def test_when_the_old_hold_cannot_be_voided_no_second_charge_is_opened(self) -> None:
        from django.contrib.auth import get_user_model

        from shopman.backstage.projections.order_queue import CARD_CAPTURE_FAILED_LABEL, build_operator_order
        from shopman.storefront.presentation.order_tracking import build_order_tracking

        self.stripe.cancel_raises = True
        order, old_intent = self._accepted_with_failed_capture()

        self.assertEqual(order.data["payment"]["intent_ref"], old_intent)
        self.assertEqual(len(self.stripe.sessions), 1)
        self.assertEqual(build_order_tracking(order).promise.state, "payment_capture_failed")
        user = get_user_model().objects.create_superuser("gestor", "g@example.com", "x")
        detail = build_operator_order(order, user=user)
        self.assertEqual(detail.advance_block_label, CARD_CAPTURE_FAILED_LABEL)
        self.assertTrue(detail.payment_lapsed)

    # ── o cancelamento pelo operador ──

    def test_cancelling_while_waiting_says_nothing_was_charged_and_the_hold_was_released(self) -> None:
        from shopman.shop.services import cancel_reasons, operator_orders

        order, _ = self._accepted_with_failed_capture()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                operator_orders.cancel_order(order, reason="operator", actor="gestor", reason_key="payment_not_confirmed")
            )
        order.refresh_from_db()
        text = cancel_reasons.customer_text(order.data)
        self.assertNotIn("a tempo", text)
        self.assertIn("Nada foi cobrado", text)
        self.assertIn("desfeita", text)

    def test_when_the_void_fails_the_customer_is_not_told_the_hold_was_released(self) -> None:
        """Nunca afirmar falso: o Stripe não anulou, a reserva segue no cartão."""
        from shopman.backstage.models import OperatorAlert
        from shopman.shop.services import cancel_reasons, operator_orders
        from shopman.storefront.presentation.order_tracking import build_order_tracking

        self.stripe.cancel_raises = True
        order, _ = self._accepted_with_failed_capture()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(
                operator_orders.cancel_order(order, reason="operator", actor="gestor", reason_key="payment_not_confirmed")
            )
        order.refresh_from_db()
        self.assertTrue(order.data["payment"].get("hold_release_failed_at"))
        self.assertTrue(
            OperatorAlert.objects.filter(order_ref=order.ref, type="card_authorization_release_failed").exists()
        )
        text = cancel_reasons.customer_text(order.data)
        self.assertIn("Nada foi cobrado", text)
        self.assertIn("a loja vai liberar a reserva", text)
        self.assertNotIn("desfeita", text)
        tracking = build_order_tracking(order)
        self.assertEqual(tracking.cancellation_note, text)
        self.assertNotIn("desfeita", tracking.cancellation_money_line)
