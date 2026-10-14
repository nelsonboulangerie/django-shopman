"""Loja online: o cliente paga ao pedir (decisão do dono, 14/10/2026, L1=1 e L2=1).

Antes o pagamento do site nascia no aceite da loja, e o Pix vencia em 10 min: quem
pedia à noite e não via o aviso de manhã perdia o pedido (P1-5). Agora, como no
WhatsApp:

- o Pix/cartão nasce no pedido (``payment.timing = "at_commit"``), sem "pagar na
  entrega" no site;
- a loja tem um prazo para aceitar, contado em horário de loja aberta
  (``confirmation.mode = "auto_cancel"``); antes dele, o Gestor é avisado;
- se a loja recusa ou o prazo passa, o pedido é cancelado e o dinheiro volta
  sozinho: o Pix é estornado, a autorização do cartão é anulada no Stripe (o
  mesmo caminho do #1732), e o cliente é avisado do cancelamento e do estorno.

Nota do dono: "se os estornos ficarem constantes, reavaliar".
"""

from __future__ import annotations

import importlib
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.apps import apps
from django.test import TestCase, override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman import PaymentService
from shopman.payman.models import PaymentIntent

from shopman.shop.models import Channel, Shop
from shopman.shop.tests.test_card_authorization_expiry import STRIPE_MANUAL, FakeStripe
from shopman.shop.tests.test_stripe_checkout_session import (
    PAYMENT_ADAPTERS_STRIPE_CARD,
    _commit_card_order,
)

WEB_PAYS_AT_ORDER = {
    "confirmation": {"mode": "auto_cancel", "timeout_minutes": 30, "stale_new_alert_minutes": 10},
    "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
}


# ── O canal ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_seed_a_loja_online_cobra_no_pedido_com_prazo_de_aceite():
    from config.management.commands.seed import Command
    from shopman.shop.config import ChannelConfig

    Shop.objects.create(name="Seed Test Shop")
    command = Command()
    command.stdout = StringIO()
    channels = command._seed_channels()

    web = ChannelConfig.for_channel(channels["web"])
    assert web.payment.timing == "at_commit"
    # L2=1: sem "pagar na entrega" no site.
    assert web.payment.available_methods == ["pix", "card"]
    assert web.confirmation.mode == "auto_cancel"
    assert web.confirmation.timeout_minutes == 30
    assert web.confirmation.stale_new_alert_minutes == 10
    assert web.confirmation.stale_new_alert_minutes < web.confirmation.timeout_minutes


@pytest.mark.django_db
def test_migracao_passa_a_loja_online_a_cobrar_no_pedido():
    Shop.objects.create(name="Test Shop")
    web = Channel.objects.create(
        ref="web",
        name="Loja online",
        config={
            "short_name": "Site",
            "confirmation": {"mode": "manual", "stale_new_alert_minutes": 10},
            "payment": {"method": ["pix", "card"], "timing": "post_commit", "timeout_minutes": 10},
        },
    )
    whatsapp = Channel.objects.create(
        ref="whatsapp",
        name="WhatsApp",
        config={
            "confirmation": {"mode": "manual", "stale_new_alert_minutes": 10},
            "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
        },
    )
    whatsapp_before = dict(whatsapp.config)

    migration = importlib.import_module("shopman.shop.migrations.0094_loja_online_paga_ao_pedir")
    migration.forwards(apps, None)
    migration.forwards(apps, None)  # idempotente

    web.refresh_from_db()
    whatsapp.refresh_from_db()
    assert web.config == {
        "short_name": "Site",
        "confirmation": {"mode": "auto_cancel", "timeout_minutes": 30, "stale_new_alert_minutes": 10},
        "payment": {"method": ["pix", "card"], "timing": "at_commit", "timeout_minutes": 10},
    }
    assert whatsapp.config == whatsapp_before


@pytest.mark.django_db
def test_migracao_nao_esmaga_configuracao_feita_a_mao():
    Shop.objects.create(name="Test Shop")
    web = Channel.objects.create(
        ref="web",
        name="Loja online",
        config={
            "confirmation": {"mode": "auto_cancel", "timeout_minutes": 45, "stale_new_alert_minutes": 15},
            "payment": {"method": ["pix"], "timing": "at_commit"},
        },
    )
    before = dict(web.config)

    migration = importlib.import_module("shopman.shop.migrations.0094_loja_online_paga_ao_pedir")
    migration.forwards(apps, None)

    web.refresh_from_db()
    assert web.config == before


# ── Pix e cartão no pedido, prazo de aceite ─────────────────────────────────


def _web_channel():
    Channel.objects.update_or_create(
        ref="web",
        defaults={"name": "Loja online", "is_active": True, "config": WEB_PAYS_AT_ORDER},
    )


@override_settings(
    SHOPMAN_STRIPE=STRIPE_MANUAL,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
    DEBUG=False,
)
class CardPaidAtOrderTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        _web_channel()
        self.stripe = FakeStripe()
        from shopman.shop.adapters import payment_stripe

        patcher = patch.object(payment_stripe, "_get_stripe", return_value=self.stripe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _authorized_order(self) -> Order:
        from shopman.shop.webhooks.stripe import StripeWebhookView

        with self.captureOnCommitCallbacks(execute=True):
            order = _commit_card_order()
        order.refresh_from_db()
        intent_ref = order.data["payment"]["intent_ref"]
        PaymentService.authorize(intent_ref, gateway_id="pi_test_auth")
        with self.captureOnCommitCallbacks(execute=True):
            StripeWebhookView()._trigger_order_hooks(intent_ref)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)
        return order

    def _expire_confirmation(self, order: Order) -> None:
        from shopman.shop.handlers.confirmation import ConfirmationTimeoutHandler

        directive = Directive.objects.get(topic="confirmation.timeout", payload__order_ref=order.ref)
        self.assertEqual(directive.payload["action"], "cancel")
        directive.payload = {**directive.payload, "expires_at": (timezone.now() - timedelta(seconds=1)).isoformat()}
        directive.save(update_fields=["payload"])
        with self.captureOnCommitCallbacks(execute=True):
            ConfirmationTimeoutHandler().handle(message=directive, ctx={})

    def test_cartao_autorizado_no_pedido_pode_ser_aceito_e_e_cobrado_no_aceite(self) -> None:
        from shopman.shop.services import operator_orders

        order = self._authorized_order()
        self.assertEqual(operator_orders.confirmation_block_reason(order), "")

    def test_pedido_nasce_com_prazo_de_aceite(self) -> None:
        order = self._authorized_order()
        directive = Directive.objects.get(topic="confirmation.timeout", payload__order_ref=order.ref)
        self.assertEqual(directive.payload["action"], "cancel")

    def test_prazo_vencido_cancela_e_anula_a_autorizacao_no_stripe(self) -> None:
        order = self._authorized_order()

        with patch("shopman.shop.services.notification.send") as send:
            self._expire_confirmation(order)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.data["cancellation_reason"], "confirmation_timeout")
        self.assertEqual(order.data["cancellation_reason_key"], "store_did_not_confirm")
        self.assertEqual(self.stripe.cancelled, ["pi_test_auth"])
        intent = PaymentIntent.objects.get(ref=order.data["payment"]["intent_ref"])
        self.assertEqual(intent.status, "cancelled")
        templates = [call.args[1] for call in send.call_args_list]
        self.assertIn("order_cancelled", templates)
        cancelled = next(call for call in send.call_args_list if call.args[1] == "order_cancelled")
        self.assertEqual(
            cancelled.kwargs["status_note"],
            "Não conseguimos confirmar seu pedido dentro do prazo.",
        )

    def test_aceito_a_tempo_o_prazo_nao_cancela(self) -> None:
        order = self._authorized_order()
        with self.captureOnCommitCallbacks(execute=True):
            order.transition_status(Order.Status.ACCEPTED, actor="gestor")

        self._expire_confirmation(order)

        order.refresh_from_db()
        self.assertNotEqual(order.status, Order.Status.CANCELLED)


# ── Pix pago, ninguém aceita: estorno ───────────────────────────────────────


@pytest.mark.django_db
def test_pix_pago_e_prazo_vencido_cancela_e_estorna(django_capture_on_commit_callbacks):
    from shopman.shop.handlers.confirmation import ConfirmationTimeoutHandler

    _web_channel()
    order = Order.objects.create(
        ref="WEB-PIX-1",
        channel_ref="web",
        status=Order.Status.NEW,
        total_q=1500,
        data={"payment": {"method": "pix"}},
    )
    directive = Directive.objects.create(
        topic="confirmation.timeout",
        payload={
            "order_ref": order.ref,
            "action": "cancel",
            "expires_at": (timezone.now() - timedelta(seconds=1)).isoformat(),
        },
    )

    with (
        patch("shopman.shop.lifecycle.payment") as payment,
        patch("shopman.shop.lifecycle.notification"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        ConfirmationTimeoutHandler().handle(message=directive, ctx={})

    order.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    payment.refund.assert_called_once()


@pytest.mark.django_db
def test_pago_e_esperando_aceite_avisa_o_gestor_antes_do_prazo():
    """O aviso de pedido parado sai DENTRO do prazo, e diz até quando."""
    from shopman.shop.config import ChannelConfig
    from shopman.shop.lifecycle import _schedule_confirmation_timeout

    _web_channel()
    order = Order.objects.create(ref="WEB-PIX-2", channel_ref="web", status=Order.Status.NEW, total_q=1500)
    config = ChannelConfig.for_channel("web")

    timer = _schedule_confirmation_timeout(order, config, action="cancel", source="payment_confirmed")

    alert = Directive.objects.get(topic="order.stale_new_alert", payload__order_ref=order.ref)
    assert alert.available_at < timer.available_at
    assert alert.payload["deadline_at"] == timer.payload["expires_at"]
    assert timer.available_at - alert.available_at == timedelta(minutes=20)

    # Reagendar (o pagamento chegou) move o aviso junto, sem duplicar.
    _schedule_confirmation_timeout(order, config, action="cancel", source="order_commit")
    assert Directive.objects.filter(topic="order.stale_new_alert", payload__order_ref=order.ref).count() == 1


@pytest.mark.django_db
def test_aviso_de_pedido_parado_diz_o_prazo_e_o_estorno():
    from shopman.backstage.models import OperatorAlert
    from shopman.shop.handlers.confirmation import StaleNewOrderAlertHandler

    _web_channel()
    order = Order.objects.create(ref="WEB-PIX-3", channel_ref="web", status=Order.Status.NEW, total_q=1500)
    deadline = timezone.now() + timedelta(minutes=20)
    directive = Directive.objects.create(
        topic="order.stale_new_alert",
        payload={
            "order_ref": order.ref,
            "alert_at": (timezone.now() - timedelta(seconds=1)).isoformat(),
            "deadline_at": deadline.isoformat(),
        },
    )

    StaleNewOrderAlertHandler().handle(message=directive, ctx={})

    alert = OperatorAlert.objects.get(type="stale_new_order", order_ref=order.ref)
    clock = timezone.localtime(deadline).strftime("%H:%M")
    assert clock in alert.message
    assert "devolvido" in alert.message
