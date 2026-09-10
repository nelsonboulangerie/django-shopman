"""WP-GAP-02 — Stripe Checkout (hosted redirect) coverage.

Covers:
- payment.initiate(method="card") persists checkout_url in order.data["payment"]
- adapter.create_intent calls stripe.checkout.Session.create with the right
  success_url / cancel_url / metadata.
- Webhook event "checkout.session.completed" → PaymentIntent authorized.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services.commit import CommitService
from shopman.orderman.services.modify import ModifyService
from shopman.payman import PaymentService

from shopman.shop.models import Channel

STRIPE_SETTINGS = {
    "secret_key": "sk_test_fake",
    "webhook_secret": "whsec_test_fake",
    "capture_method": "automatic",
    "domain": "https://shop.example.com",
}

PAYMENT_ADAPTERS_STRIPE_CARD = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_stripe",
}


def _commit_card_order(channel_ref: str = "web") -> Order:
    """Helper: commit an order with payment.method=card."""
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
            {"op": "set_data", "path": "payment.method", "value": "card"},
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


# ══════════════════════════════════════════════════════════════
# adapter.create_intent — Stripe Checkout Session
# ══════════════════════════════════════════════════════════════


@override_settings(
    SHOPMAN_STRIPE=STRIPE_SETTINGS,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
    # Origem da LOJA (Nuxt) — distinta da API de propósito, para o teste pegar
    # se alguém voltar a montar a URL de retorno a partir do domínio do Django.
    SHOPMAN_STOREFRONT_BASE_URL="https://loja.example.com",
)
class StripeCreateIntentTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Channel.objects.create(ref="web", name="Web", is_active=True)

    def _mock_session(self, *, session_id="cs_test_abc", url="https://checkout.stripe.com/c/pay/cs_test_abc"):
        session = MagicMock()
        session.id = session_id
        session.url = url
        session.payment_intent = None
        return session

    def test_create_intent_calls_stripe_checkout_session(self) -> None:
        order = _commit_card_order()
        from shopman.shop.adapters import payment_stripe

        with patch.object(payment_stripe, "_get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_session = self._mock_session()
            mock_stripe.checkout.Session.create.return_value = mock_session
            mock_get_stripe.return_value = mock_stripe

            intent = payment_stripe.create_intent(
                order_ref=order.ref,
                amount_q=order.total_q,
                currency="BRL",
                method="card",
                metadata={"method": "card"},
            )

        # Stripe was called with a Checkout Session payload (NOT PaymentIntent).
        mock_stripe.checkout.Session.create.assert_called_once()
        kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["mode"] == "payment"
        assert kwargs["payment_method_types"] == ["card"]
        # O Stripe devolve o cliente para a LOJA, não para a API, e para rotas
        # que existem. As URLs eram montadas à mão a partir de um `domain` local
        # e carregavam três defeitos: origem do Django, barra final que a rota
        # Nuxt não tem, e `/confirmacao/` — tela aposentada quando o yoin migrou
        # para o acompanhamento. Agora saem de `storefront_links`.
        # PAYMENT-TRACKING-MERGE: cancelar no Stripe volta ao acompanhamento
        # (onde o cartão é oferecido inline), não a uma tela de pagamento.
        assert kwargs["success_url"] == f"https://loja.example.com/pedido/{order.ref}"
        assert kwargs["cancel_url"] == f"https://loja.example.com/pedido/{order.ref}"
        assert "/confirmacao" not in kwargs["success_url"]
        assert not kwargs["cancel_url"].endswith("/")
        assert kwargs["metadata"]["order_ref"] == order.ref
        assert kwargs["metadata"]["shopman_ref"] == intent.intent_ref
        line_item = kwargs["line_items"][0]
        assert line_item["price_data"]["currency"] == "brl"
        assert line_item["price_data"]["unit_amount"] == order.total_q

        # The adapter must NOT call stripe.PaymentIntent.create — Checkout Session
        # is now the only path.
        mock_stripe.PaymentIntent.create.assert_not_called()

        # The returned intent carries the hosted URL in metadata.
        assert intent.metadata["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_abc"

    def test_initiate_persists_checkout_url_on_order(self) -> None:
        # Create an order *outside* the lifecycle so payment.initiate isn't
        # auto-triggered during commit. We're testing the orchestrator-side
        # persistence of `checkout_url`, not the lifecycle wiring.
        order = Order.objects.create(
            ref="ORD-CARD-INIT-001",
            channel_ref="web",
            status="new",
            total_q=1500,
            handle_type="phone",
            handle_ref="5543000000001",
            data={"payment": {"method": "card"}},
        )
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_svc

        with patch.object(payment_stripe, "_get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.checkout.Session.create.return_value = self._mock_session(
                session_id="cs_test_persist",
                url="https://checkout.stripe.com/c/pay/cs_test_persist",
            )
            mock_get_stripe.return_value = mock_stripe

            payment_svc.initiate(order)

        order.refresh_from_db()
        payment_data = order.data["payment"]
        assert payment_data["method"] == "card"
        assert payment_data["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_persist"
        # Hosted redirect ⇒ we never expose a client_secret.
        assert "client_secret" not in payment_data

    def test_initiate_uses_configured_capture_method(self) -> None:
        order = Order.objects.create(
            ref="ORD-CARD-CAPTURE-001",
            channel_ref="web",
            status="new",
            total_q=1500,
            handle_type="phone",
            handle_ref="5543000000002",
            data={"payment": {"method": "card"}},
        )
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_svc

        with patch.object(payment_stripe, "_get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.checkout.Session.create.return_value = self._mock_session()
            mock_get_stripe.return_value = mock_stripe

            payment_svc.initiate(order)

        kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        assert kwargs["payment_intent_data"]["capture_method"] == "automatic"


# ══════════════════════════════════════════════════════════════
# Webhook — checkout.session.completed
# ══════════════════════════════════════════════════════════════


@override_settings(
    SHOPMAN_STRIPE=STRIPE_SETTINGS,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
)
class StripeCheckoutSessionWebhookTests(TestCase):
    URL = "/api/webhooks/stripe/"

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        Channel.objects.create(ref="web", name="Web", is_active=True)

    def _mock_event(self, *, shopman_ref: str, payment_intent_id: str | None, session_id: str = "cs_test_xyz"):
        mock_event = MagicMock()
        mock_event.type = "checkout.session.completed"
        session = MagicMock()
        session.id = session_id
        session.payment_intent = payment_intent_id
        session.metadata = {"shopman_ref": shopman_ref}
        mock_event.data.object = session
        return mock_event

    def _post(self, mock_event) -> object:
        with patch("shopman.shop.adapters.payment_stripe._get_stripe") as mock_get_stripe:
            mock_stripe = MagicMock()
            mock_stripe.Webhook.construct_event.return_value = mock_event
            mock_get_stripe.return_value = mock_stripe
            return self.client.post(
                self.URL,
                data=json.dumps({"type": "checkout.session.completed"}).encode(),
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE="valid-sig",
            )

    def test_checkout_session_completed_authorizes_intent(self) -> None:
        order = _commit_card_order()
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="card",
            gateway="stripe",
            gateway_data={},
        )
        intent.gateway_id = "cs_test_xyz"
        intent.save(update_fields=["gateway_id"])
        order.data["payment"] = {
            "method": "card",
            "intent_ref": intent.ref,
            "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_xyz",
        }
        order.save(update_fields=["data", "updated_at"])

        resp = self._post(self._mock_event(
            shopman_ref=intent.ref,
            payment_intent_id="pi_test_promoted",
        ))
        assert resp.status_code == 200, getattr(resp, "data", resp.content)

        intent.refresh_from_db()
        assert intent.status == "authorized"
        # gateway_id was promoted from session id to payment_intent id.
        assert intent.gateway_id == "pi_test_promoted"

    def test_checkout_session_without_payment_intent_still_authorizes(self) -> None:
        """Some Checkout Sessions complete with payment_intent=None (e.g. zero-decimal currencies);
        we must still capture using the session id as gateway anchor."""
        order = _commit_card_order()
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="card",
            gateway="stripe",
            gateway_data={},
        )
        intent.gateway_id = "cs_test_no_pi"
        intent.save(update_fields=["gateway_id"])
        order.data["payment"] = {"method": "card", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])

        resp = self._post(self._mock_event(
            shopman_ref=intent.ref,
            payment_intent_id=None,
            session_id="cs_test_no_pi",
        ))
        assert resp.status_code == 200

        intent.refresh_from_db()
        assert intent.status == "authorized"

    def test_checkout_session_completed_does_not_dispatch_paid_before_capture(self) -> None:
        """Checkout completion authorizes the card; capture happens after store confirmation."""
        order = _commit_card_order()
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="card",
            gateway="stripe",
            gateway_data={},
        )
        intent.gateway_id = "cs_test_dispatch"
        intent.save(update_fields=["gateway_id"])
        order.data["payment"] = {"method": "card", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            self._post(self._mock_event(
                shopman_ref=intent.ref,
                payment_intent_id="pi_dispatch",
                session_id="cs_test_dispatch",
            ))

        mock_dispatch.assert_not_called()


# ══════════════════════════════════════════════════════════════
# A volta do Stripe — reconciliação quando o webhook não chega
# ══════════════════════════════════════════════════════════════
#
# ⚠️ Este bloco existe por um relato de campo: pagamento concluído no ambiente do
# Stripe, cliente de volta na nossa tela, e a tela continuava pedindo para pagar.
# A causa não era o Stripe: era que NADA no sistema jamais perguntava a ele. O
# `get_status` do adapter lia o Payman, o `reconcile_payments` lia o Payman, e a
# única escrita era o webhook. Webhook perdido (endpoint errado no painel, segredo
# de outro ambiente, 400 na assinatura) virava dano permanente e silencioso.
#
# Os testes abaixo travam as três pontas: o verbo de leitura existe e responde,
# a leitura do acompanhamento liquida sozinha, e o guard de timeout não cancela
# mais um pedido de cartão sem antes perguntar.


@override_settings(
    SHOPMAN_STRIPE=STRIPE_SETTINGS,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
    DEBUG=False,
)
class StripeGatewayReadbackTests(TestCase):
    """`check_gateway_status`: o verbo de LEITURA que a Efí tinha e o Stripe não."""

    def _intent(self, order, *, gateway_id: str, gateway_data: dict | None = None):
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="card",
            gateway="stripe",
            gateway_data=gateway_data or {},
        )
        intent.gateway_id = gateway_id
        intent.save(update_fields=["gateway_id"])
        order.data["payment"] = {"method": "card", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])
        return intent

    def test_requires_capture_reads_as_authorized_not_as_pending(self) -> None:
        """`capture_method=manual` é o padrão da casa: o dinheiro fica reservado.

        Achatar `requires_capture` em "pending" diria "não pagou" sobre quem pagou.
        """
        from shopman.shop.adapters import payment_stripe

        order = _commit_card_order()
        intent = self._intent(order, gateway_id="pi_manual_hold")

        stripe = MagicMock()
        stripe.PaymentIntent.retrieve.return_value = MagicMock(
            status="requires_capture", amount_received=0,
        )
        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            assert payment_stripe.check_gateway_status(intent.ref) == "authorized"

    def test_succeeded_reads_as_captured(self) -> None:
        from shopman.shop.adapters import payment_stripe

        order = _commit_card_order()
        intent = self._intent(order, gateway_id="pi_done")

        stripe = MagicMock()
        stripe.PaymentIntent.retrieve.return_value = MagicMock(
            status="succeeded", amount_received=1000,
        )
        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            assert payment_stripe.check_gateway_status(intent.ref) == "captured"

    def test_session_id_still_resolves_to_the_payment_intent(self) -> None:
        """Sem webhook o `gateway_id` continua sendo o `cs_...`, e é preciso resolver.

        É exatamente o caso que a reconciliação existe para atender: se ela
        dependesse do webhook para saber o `pi_`, não serviria para nada.
        """
        from shopman.shop.adapters import payment_stripe

        order = _commit_card_order()
        intent = self._intent(
            order,
            gateway_id="cs_sem_webhook",
            gateway_data={"checkout_session_id": "cs_sem_webhook"},
        )

        stripe = MagicMock()
        stripe.checkout.Session.retrieve.return_value = MagicMock(
            status="complete", payment_intent="pi_resolvido",
        )
        stripe.PaymentIntent.retrieve.return_value = MagicMock(
            status="requires_capture", amount_received=0,
        )
        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            assert payment_stripe.check_gateway_status(intent.ref) == "authorized"
        stripe.PaymentIntent.retrieve.assert_called_once_with("pi_resolvido")

    def test_gateway_silence_is_error_not_unpaid(self) -> None:
        """Gateway mudo é INCERTEZA. Traduzir silêncio em "não pagou" cancela pedido pago."""
        from shopman.shop.adapters import payment_stripe

        order = _commit_card_order()
        intent = self._intent(order, gateway_id="pi_mudo")

        stripe = MagicMock()
        stripe.PaymentIntent.retrieve.side_effect = RuntimeError("timeout")
        with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
            assert payment_stripe.check_gateway_status(intent.ref) == "error"

    def test_missing_credential_is_error_not_unpaid(self) -> None:
        from shopman.shop.adapters import payment_stripe

        order = _commit_card_order()
        intent = self._intent(order, gateway_id="pi_sem_chave")

        with patch.object(
            payment_stripe,
            "_get_stripe",
            side_effect=payment_stripe.StripeNotConfigured("sem chave"),
        ):
            assert payment_stripe.check_gateway_status(intent.ref) == "error"


@override_settings(
    SHOPMAN_STRIPE=STRIPE_SETTINGS,
    SHOPMAN_PAYMENT_ADAPTERS=PAYMENT_ADAPTERS_STRIPE_CARD,
    DEBUG=False,
)
class StripeReturnWithoutWebhookTests(TestCase):
    """O cliente volta do Stripe e a tela tem que contar a verdade."""

    def _order_with_intent(self, *, gateway_id="pi_volta"):
        order = _commit_card_order()
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="card",
            gateway="stripe",
            gateway_data={},
        )
        intent.gateway_id = gateway_id
        intent.save(update_fields=["gateway_id"])
        order.data["payment"] = {"method": "card", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])
        return order, intent

    def test_authorization_lost_with_the_webhook_is_recovered_on_read(self) -> None:
        """Sem isto, quem pagou volta para uma tela que pede pagamento. Para sempre."""
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        order, intent = self._order_with_intent()
        assert intent.status == "pending"  # o webhook nunca chegou

        with patch.object(payment_stripe, "check_gateway_status", return_value="authorized"):
            changed = payment_service.reconcile_with_gateway_if_due(order)

        assert changed is True
        intent.refresh_from_db()
        assert intent.status == "authorized"

    def test_reconciliation_does_not_capture_before_the_store_accepts(self) -> None:
        """Reconciliar não pode virar atalho para cobrar antes do aceite.

        Foi a linha cruzada no caso do pedido E54: capturar sem humano no circuito.
        Quem captura é o lifecycle, quando a loja aceita.
        """
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        order, intent = self._order_with_intent()
        assert order.status == Order.Status.NEW

        with patch.object(payment_stripe, "check_gateway_status", return_value="authorized"):
            payment_service.reconcile_with_gateway_if_due(order)

        assert PaymentService.captured_total(intent.ref) == 0

    def test_a_second_read_does_not_ask_the_gateway_again(self) -> None:
        """O acompanhamento é relido a cada refresh; perguntar sempre viraria enxurrada."""
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        order, _intent = self._order_with_intent()

        with patch.object(
            payment_stripe, "check_gateway_status", return_value="pending",
        ) as asked:
            payment_service.reconcile_with_gateway_if_due(order)
            payment_service.reconcile_with_gateway_if_due(order)

        assert asked.call_count == 1

    def test_a_paid_order_is_not_asked_about_again(self) -> None:
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        order, intent = self._order_with_intent()
        PaymentService.authorize(intent.ref, gateway_id=intent.gateway_id)
        PaymentService.capture(intent.ref, gateway_id=intent.gateway_id)

        with patch.object(payment_stripe, "check_gateway_status") as asked:
            payment_service.reconcile_with_gateway_if_due(order)

        asked.assert_not_called()

    def test_timeout_no_longer_cancels_a_card_order_without_asking(self) -> None:
        """`method != "pix" → "unpaid"` autorizava cancelar pedido de cartão PAGO."""
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        order, _intent = self._order_with_intent()

        with patch.object(payment_stripe, "check_gateway_status", return_value="authorized"):
            assert payment_service.settle_from_gateway(order) == "authorized"

    def test_timeout_still_cancels_when_the_gateway_says_nobody_paid(self) -> None:
        from shopman.shop.adapters import payment_stripe
        from shopman.shop.services import payment as payment_service

        order, _intent = self._order_with_intent()

        with patch.object(payment_stripe, "check_gateway_status", return_value="pending"):
            assert payment_service.settle_from_gateway(order) == "unpaid"


@override_settings(
    SHOPMAN_STRIPE=STRIPE_SETTINGS,
    SHOPMAN_PAYMENT_ADAPTERS={"pix": "shopman.shop.adapters.payment_mock"},
    DEBUG=False,
)
class PixIsNotAskedOnEveryReadTests(TestCase):
    """O PIX fica de fora da pergunta preguiçosa — e isso é decisão, não esquecimento.

    Ele já tem rede: o cliente não sai do site, o webhook empurra por SSE, e no
    vencimento ``settle_from_gateway`` consulta a Efí antes de cancelar. Perguntar
    a cada leitura poria uma chamada à Efí a cada 20 segundos enquanto alguém
    encara o QR code, para cobrir um caso já coberto.
    """

    def test_a_pix_order_does_not_call_the_gateway_on_read(self) -> None:
        from shopman.shop.services import payment as payment_service

        order = _commit_card_order()
        intent = PaymentService.create_intent(
            order_ref=order.ref, amount_q=order.total_q, method="pix", gateway="efi",
        )
        order.data["payment"] = {"method": "pix", "intent_ref": intent.ref}
        order.save(update_fields=["data", "updated_at"])

        with patch.object(payment_service, "settle_from_gateway") as asked:
            assert payment_service.reconcile_with_gateway_if_due(order) is False

        asked.assert_not_called()
