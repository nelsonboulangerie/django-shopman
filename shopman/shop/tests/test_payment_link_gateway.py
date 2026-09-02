"""O link de pagamento passa pelo gateway — e o gateway tem que fechar o ciclo.

Três defeitos do link, todos com a mesma causa: cada rede do sistema perguntava
``method == "card"`` cravado, e o link ficava de fora.

1. O link herdava o ``capture_method`` do bloco ``SHOPMAN_STRIPE`` (``manual``):
   o cliente pagava, o intent ficava ``authorized``, a autorização vencia no
   Stripe em ~7 dias e a padaria NUNCA recebia.
2. O webhook do Stripe só capturava ``card`` autorizado.
3. ``reconcile_payments`` — a rede contra webhook perdido — só perguntava ao
   gateway por ``card``.

Aqui, o link captura sozinho (``automatic``, sempre), o webhook e a
reconciliação alcançam toda sessão hospedada (``HOSTED_CHECKOUT_METHODS``), e
o cartão da loja continua obedecendo ``STRIPE_CAPTURE_METHOD``.
"""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.orderman.models import Order
from shopman.payman import PaymentService

from shopman.shop.models import Channel
from shopman.shop.tests.test_card_settles_without_the_customer import FakeStripe

#: O bloco do Stripe com captura MANUAL — o default do deploy, e o que o link
#: herdava. É de propósito: o link tem que dizer ``automatic`` APESAR disto.
STRIPE_MANUAL = {
    "secret_key": "sk_test_fake",
    "webhook_secret": "whsec_test_fake",
    "capture_method": "manual",
    "domain": "https://shop.example.com",
}

PAYMENT_ADAPTERS_STRIPE_LINK = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_stripe",
    "link": "shopman.shop.adapters.payment_stripe",
}


def _remote_order(ref: str, *, method: str = "link", status: str = "accepted") -> Order:
    """Pedido remoto anotado no balcão (canal ``pdv``), fora do lifecycle."""
    return Order.objects.create(
        ref=ref,
        channel_ref="pdv",
        status=status,
        total_q=1500,
        handle_type="phone",
        handle_ref="5543000000009",
        data={"payment": {"method": method}},
    )


def _hosted_intent(order: Order, *, gateway_id: str):
    """Intent pendente da sessão hospedada, como o ``initiate`` deixa."""
    intent = PaymentService.create_intent(
        order_ref=order.ref,
        amount_q=order.total_q,
        method=order.data["payment"]["method"],
        gateway="stripe",
        gateway_data={},
    )
    intent.gateway_id = gateway_id
    intent.save(update_fields=["gateway_id"])
    order.data["payment"]["intent_ref"] = intent.ref
    order.save(update_fields=["data", "updated_at"])
    return intent


@override_settings(
    SHOPMAN_STRIPE=STRIPE_MANUAL,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_LINK,
    DEBUG=False,
)
class LinkCapturesByItselfTests(TestCase):
    """Defeito 1: o link nasce com captura automática, sempre."""

    def setUp(self) -> None:
        super().setUp()
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)

    def test_adapter_config_forces_automatic_capture_for_link(self) -> None:
        from shopman.shop.services import payment as payment_service

        order = _remote_order("ORD-LINK-CFG-001")
        config = payment_service._adapter_config(order, method="link")

        # `SHOPMAN_STRIPE` diz `manual` e o link ignora: não é botão de env, é
        # a natureza da forma — a venda do balcão já fechou quando a URL nasce.
        self.assertEqual(config["capture_method"], "automatic")

    def test_card_keeps_following_stripe_settings(self) -> None:
        from shopman.shop.services import payment as payment_service

        order = _remote_order("ORD-LINK-CFG-002", method="card")

        self.assertEqual(payment_service._adapter_config(order, method="card")["capture_method"], "manual")
        with override_settings(SHOPMAN_STRIPE={**STRIPE_MANUAL, "capture_method": "automatic"}):
            self.assertEqual(payment_service._adapter_config(order, method="card")["capture_method"], "automatic")
        # Valor irreconhecível cai no lado seguro (não cobrar antes do aceite).
        with override_settings(SHOPMAN_STRIPE={**STRIPE_MANUAL, "capture_method": "whatever"}):
            self.assertEqual(payment_service._adapter_config(order, method="card")["capture_method"], "manual")

    def test_initiate_sends_automatic_capture_to_stripe_for_link(self) -> None:
        """Ponta a ponta: o que chega ao ``Session.create`` do Stripe é ``automatic``."""
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        order = _remote_order("ORD-LINK-INIT-001", status="new")
        with patch.object(payment_stripe, "_get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            session = MagicMock()
            session.id = "cs_test_link"
            session.url = "https://checkout.stripe.com/c/pay/cs_test_link"
            session.payment_intent = None
            mock_stripe.checkout.Session.create.return_value = session
            mock_get_stripe.return_value = mock_stripe

            payment_service.initiate(order)

        kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        self.assertEqual(kwargs["payment_intent_data"]["capture_method"], "automatic")
        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["checkout_url"], "https://checkout.stripe.com/c/pay/cs_test_link")
        # E o Payman sabe que é LINK, não cartão.
        self.assertEqual(PaymentService.get(order.data["payment"]["intent_ref"]).method, "link")


@override_settings(
    SHOPMAN_STRIPE=STRIPE_MANUAL,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_LINK,
    DEBUG=False,
)
class LinkWebhookCapturesAuthorizedTests(TestCase):
    """Defeito 2: um link que chega ``authorized`` é capturado pelo webhook.

    O link nasce ``automatic``, mas a rede existe para o que escapa (captura
    manual configurada no painel, sessão antiga): se o gateway o segurar em
    ``requires_capture``, o webhook cobra — como já fazia para ``card``.
    """

    URL = "/api/webhooks/stripe/"

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)

    def _checkout_completed(self, *, intent_ref: str, order_ref: str):
        event = MagicMock()
        event.id = "evt_link_checkout_completed"
        event.type = "checkout.session.completed"
        session = MagicMock()
        session.id = "cs_test_1"
        session.payment_intent = "pi_test_1"
        session.metadata = {"shopman_ref": intent_ref, "order_ref": order_ref}
        event.data.object = session
        return event

    def test_checkout_completed_captures_an_authorized_link(self) -> None:
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        order = _remote_order("ORD-LINK-WH-001")
        intent = _hosted_intent(order, gateway_id="cs_test_1")

        stripe = FakeStripe(amount_q=order.total_q)
        stripe.Webhook = MagicMock()
        stripe.Webhook.construct_event.return_value = self._checkout_completed(
            intent_ref=intent.ref, order_ref=order.ref,
        )

        with (
            patch.object(payment_stripe, "_get_stripe", return_value=stripe),
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                self.URL,
                data=json.dumps({"type": "checkout.session.completed"}).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid-sig",
            )

        self.assertEqual(response.status_code, 200, response.data)
        # O dublê do SDK viu o `PaymentIntent.capture` — a linha que faltava.
        self.assertTrue(stripe.captured)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "captured")
        self.assertIs(payment_service.has_sufficient_captured_payment(order), True)


@override_settings(
    SHOPMAN_STRIPE=STRIPE_MANUAL,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_LINK,
    DEBUG=False,
)
class LinkReconciliationTests(TestCase):
    """Defeito 3: a rede contra webhook perdido alcança o pedido de link.

    O link nem tem "volta" à tela: o cliente paga do celular, num aparelho que
    nunca abriu o acompanhamento. Se o webhook se perde, o worker é a ÚNICA
    porta — e ela filtrava ``method="card"``.
    """

    def setUp(self) -> None:
        super().setUp()
        Channel.objects.create(ref="pdv", name="PDV", is_active=True)

    def test_dry_run_lists_the_open_link_order(self) -> None:
        order = _remote_order("ORD-LINK-REC-001")
        _hosted_intent(order, gateway_id="cs_test_1")

        out = StringIO()
        call_command("reconcile_payments", "--dry-run", stdout=out)

        self.assertIn(order.ref, out.getvalue())

    def test_the_worker_asks_the_gateway_about_a_link_nobody_came_back_for(self) -> None:
        from shopman.shop.adapters import payment_stripe

        order = _remote_order("ORD-LINK-REC-002")
        intent = _hosted_intent(order, gateway_id="cs_test_1")
        self.assertEqual(intent.status, "pending")  # o webhook nunca chegou

        with (
            patch.object(payment_stripe, "_get_stripe", return_value=FakeStripe(amount_q=order.total_q)),
            self.captureOnCommitCallbacks(execute=True),
        ):
            call_command("reconcile_payments", stdout=StringIO())

        intent.refresh_from_db()
        # Autorização registrada ou captura feita: o que importa é que o
        # sistema PERGUNTOU e a verdade do gateway entrou no Payman.
        self.assertIn(intent.status, {"authorized", "captured"})
