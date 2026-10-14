"""Cartão autorizado e ninguém aceita: a reserva vence no Stripe (P1-4).

O cartão da loja online autoriza no checkout e só cobra no aceite. Sem aceite,
o pedido ficava em ``new`` para sempre: o ``payment.timeout`` não cancela quem
pagou, e o Stripe cancelava a autorização no sétimo dia sem ninguém saber. O
dinheiro sumia do pedido em silêncio.

Aqui: o prazo é calculado e exposto, o Gestor é avisado com antecedência (com o
prazo), a recusa anula a autorização (e grita se o Stripe recusar), e o
vencimento põe o pedido num estado coerente (cancelado, nada cobrado, crítico).
Stripe sempre dublado: nenhuma chamada de rede.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Channel
from shopman.shop.tests.test_stripe_checkout_session import (
    PAYMENT_ADAPTERS_STRIPE_CARD,
    _commit_card_order,
)

STRIPE_MANUAL = {
    "secret_key": "sk_test_fake",
    "webhook_secret": "whsec_test_fake",
    "capture_method": "manual",
    "domain": "https://shop.example.com",
}

TOPIC = "payment.card_authorization_watch"


class FakeStripe:
    """Dublê do SDK: sessão concluída, PaymentIntent em ``requires_capture``."""

    def __init__(self) -> None:
        self.pi_status = "requires_capture"
        self.cancel_raises = False
        self.cancelled: list[str] = []
        outer = self

        session = MagicMock()
        session.id = "cs_test_auth"
        session.url = "https://checkout.stripe.com/c/pay/cs_test_auth"
        session.payment_intent = "pi_test_auth"
        session.status = "complete"
        self.session = session

        class _Session:
            @staticmethod
            def create(**kwargs):
                return outer.session

            @staticmethod
            def retrieve(sid):
                return outer.session

            @staticmethod
            def expire(sid):
                return outer.session

        class _Checkout:
            Session = _Session

        class _PaymentIntent:
            @staticmethod
            def retrieve(pid, **kwargs):
                pi = MagicMock()
                pi.id = "pi_test_auth"
                pi.status = outer.pi_status
                pi.amount_received = 0
                return pi

            @staticmethod
            def cancel(pid, **kwargs):
                if outer.cancel_raises:
                    raise RuntimeError("stripe indisponível")
                outer.cancelled.append(pid)
                outer.pi_status = "canceled"
                pi = MagicMock()
                pi.id = pid
                pi.status = "canceled"
                return pi

        self.checkout = _Checkout
        self.PaymentIntent = _PaymentIntent


@override_settings(
    SHOPMAN_STRIPE=STRIPE_MANUAL,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
    DEBUG=False,
)
class CardAuthorizationWithoutAcceptTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Channel.objects.update_or_create(
            ref="web",
            defaults={
                "name": "Loja online",
                "is_active": True,
                "config": {
                    "confirmation": {"mode": "manual", "stale_new_alert_minutes": 10},
                    "payment": {
                        "method": ["pix", "card"],
                        "timing": "post_commit",
                        "timeout_minutes": 10,
                    },
                },
            },
        )
        self.stripe = FakeStripe()
        from shopman.shop.adapters import payment_stripe

        patcher = patch.object(payment_stripe, "_get_stripe", return_value=self.stripe)
        patcher.start()
        self.addCleanup(patcher.stop)

    # ── helpers ──

    def _authorized_order(self, *, authorized_ago: timedelta = timedelta(0)) -> Order:
        """Pedido novo cujo cartão o cliente autorizou (o webhook chegou)."""
        from shopman.shop.webhooks.stripe import StripeWebhookView

        with self.captureOnCommitCallbacks(execute=True):
            order = _commit_card_order()
        order.refresh_from_db()
        intent_ref = order.data["payment"]["intent_ref"]
        PaymentService.authorize(intent_ref, gateway_id="pi_test_auth")
        PaymentIntent.objects.filter(ref=intent_ref).update(
            authorized_at=timezone.now() - authorized_ago,
        )
        with self.captureOnCommitCallbacks(execute=True):
            StripeWebhookView()._trigger_order_hooks(intent_ref)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)
        return order

    def _run_watch(self, order: Order) -> Directive:
        from shopman.shop.handlers.card_authorization import CardAuthorizationWatchHandler

        directive = Directive.objects.get(topic=TOPIC, payload__order_ref=order.ref)
        with self.captureOnCommitCallbacks(execute=True):
            CardAuthorizationWatchHandler().handle(message=directive, ctx={})
        directive.refresh_from_db()
        return directive

    # ── o prazo existe e é exposto ──

    def test_authorization_schedules_the_watch_with_the_stripe_deadline(self) -> None:
        order = self._authorized_order()
        intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
        expected = intent.authorized_at + timedelta(days=7)

        directive = Directive.objects.get(topic=TOPIC, payload__order_ref=order.ref)
        self.assertEqual(directive.payload["expires_at"], expected.isoformat())
        # O primeiro aviso vem depois do aviso normal de pedido parado.
        self.assertGreater(directive.available_at, timezone.now() + timedelta(minutes=30))

        # Um segundo webhook não agenda outro vigia.
        from shopman.shop.webhooks.stripe import StripeWebhookView

        StripeWebhookView()._trigger_order_hooks(intent.ref)
        self.assertEqual(Directive.objects.filter(topic=TOPIC).count(), 1)

    def test_gateway_capture_before_wins_over_the_default_window(self) -> None:
        from shopman.shop.services import card_authorization

        order = self._authorized_order()
        intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
        stripe_deadline = timezone.now() + timedelta(days=3)
        intent.gateway_data = {**(intent.gateway_data or {}), "capture_before": int(stripe_deadline.timestamp())}
        intent.save(update_fields=["gateway_data"])

        got = card_authorization.expires_at(order)
        self.assertEqual(int(got.timestamp()), int(stripe_deadline.timestamp()))

    def test_the_gestor_card_and_detail_show_the_deadline(self) -> None:
        from django.contrib.auth import get_user_model

        from shopman.backstage.projections.order_queue import build_operator_order, build_order_card

        order = self._authorized_order()
        intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
        expected = (intent.authorized_at + timedelta(days=7)).isoformat()

        user = get_user_model().objects.create_superuser("gestor", "g@example.com", "x")
        card = build_order_card(order, user=user)
        self.assertEqual(card.card_authorization_expires_iso, expected)
        detail = build_operator_order(order, user=user)
        self.assertEqual(detail.card_authorization_expires_iso, expected)

    # ── avisos com antecedência ──

    def test_a_stuck_order_gets_a_warning_with_the_deadline(self) -> None:
        # Autorizado há 2 h: o vigia nasce vencido e o worker o roda na hora.
        order = self._authorized_order(authorized_ago=timedelta(hours=2))
        directive = Directive.objects.get(topic=TOPIC, payload__order_ref=order.ref)

        alert = OperatorAlert.objects.get(type="card_authorization_expiring", order_ref=order.ref)
        self.assertEqual(alert.severity, "warning")
        self.assertIn("vence em", alert.message)
        self.assertEqual(alert.audience, "orders")
        # E o vigia volta 24 h antes do vencimento.
        self.assertEqual(directive.status, "queued")
        self.assertEqual(directive.payload["stage"], "last_call")
        intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
        self.assertEqual(directive.available_at, intent.authorized_at + timedelta(days=6))

        # Rodar de novo antes da hora não avisa outra vez nem adianta o último aviso.
        directive = self._run_watch(order)
        self.assertEqual(
            OperatorAlert.objects.filter(type="card_authorization_expiring", order_ref=order.ref).count(), 1,
        )
        self.assertEqual(directive.payload["stage"], "last_call")

    def test_the_last_day_alert_carries_the_deadline_without_duplicating(self) -> None:
        # Autorizado há 6 dias e 2 h (webhook atrasado): os dois avisos saem juntos.
        order = self._authorized_order(authorized_ago=timedelta(days=6, hours=2))
        directive = Directive.objects.get(topic=TOPIC, payload__order_ref=order.ref)

        alerts = OperatorAlert.objects.filter(type="card_authorization_expiring", order_ref=order.ref)
        last_call = alerts.get(severity="error")
        intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
        self.assertEqual(last_call.respond_by, intent.authorized_at + timedelta(days=7))
        self.assertEqual(directive.payload["stage"], "expire")

        # Rodar de novo antes do vencimento não cria outro aviso.
        directive.payload = {**directive.payload, "stage": "last_call"}
        directive.save(update_fields=["payload"])
        self._run_watch(order)
        self.assertEqual(
            OperatorAlert.objects.filter(type="card_authorization_expiring", order_ref=order.ref).count(),
            alerts.count(),
        )

    def test_accepting_resolves_the_warning(self) -> None:
        order = self._authorized_order(authorized_ago=timedelta(hours=2))
        self.assertTrue(OperatorAlert.objects.filter(type="card_authorization_expiring", order_ref=order.ref).exists())

        with self.captureOnCommitCallbacks(execute=True):
            order.transition_status(Order.Status.ACCEPTED, actor="gestor")

        alert = OperatorAlert.objects.get(type="card_authorization_expiring", order_ref=order.ref)
        self.assertIsNotNone(alert.resolved_at)

    # ── recusar libera a autorização ──

    def test_rejecting_releases_the_authorization_at_stripe(self) -> None:
        from shopman.shop.services.cancellation import cancel

        order = self._authorized_order()
        with self.captureOnCommitCallbacks(execute=True):
            cancel(order, reason="operator_rejected", actor="gestor")

        self.assertEqual(self.stripe.cancelled, ["pi_test_auth"])
        intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
        self.assertEqual(intent.status, "cancelled")
        self.assertFalse(OperatorAlert.objects.filter(type="card_authorization_release_failed").exists())

    def test_a_release_the_gateway_refuses_is_a_critical_alert(self) -> None:
        from shopman.shop.services.cancellation import cancel

        order = self._authorized_order()
        self.stripe.cancel_raises = True
        with self.captureOnCommitCallbacks(execute=True):
            cancel(order, reason="operator_rejected", actor="gestor")

        alert = OperatorAlert.objects.get(type="card_authorization_release_failed", order_ref=order.ref)
        self.assertEqual(alert.severity, "critical")
        self.assertIn("painel do Stripe", alert.message)

    # ── venceu mesmo assim ──

    def test_an_expired_authorization_cancels_the_order_without_charge(self) -> None:
        order = self._authorized_order(authorized_ago=timedelta(days=7, minutes=5))
        directive = Directive.objects.get(topic=TOPIC, payload__order_ref=order.ref)
        directive.payload = {**directive.payload, "stage": "expire"}
        directive.save(update_fields=["payload"])
        self.stripe.pi_status = "canceled"  # o Stripe já cancelou a autorização

        with patch("shopman.shop.services.notification.send") as send:
            self._run_watch(order)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.data["cancellation_reason"], "card_authorization_expired")
        intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
        self.assertEqual(intent.status, "cancelled")
        self.assertEqual(intent.captured_at, None)
        alert = OperatorAlert.objects.get(type="card_authorization_expired", order_ref=order.ref)
        self.assertEqual(alert.severity, "critical")
        self.assertIn("nada foi cobrado", alert.message)
        # O cliente é avisado pelo fluxo normal do cancelamento, com o motivo.
        templates = [call.args[1] for call in send.call_args_list]
        self.assertIn("order_cancelled", templates)
        # Sem anular de novo o que o Stripe já cancelou, e sem o falso alarme.
        self.assertEqual(self.stripe.cancelled, [])
        self.assertFalse(OperatorAlert.objects.filter(type="card_authorization_release_failed").exists())

    def test_stripe_still_holding_the_authorization_asks_again_later(self) -> None:
        order = self._authorized_order(authorized_ago=timedelta(days=7, minutes=5))
        directive = Directive.objects.get(topic=TOPIC, payload__order_ref=order.ref)
        directive.payload = {**directive.payload, "stage": "expire"}
        directive.save(update_fields=["payload"])

        directive = self._run_watch(order)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)
        self.assertEqual(directive.status, "queued")
        self.assertGreater(directive.available_at, timezone.now() + timedelta(minutes=30))
