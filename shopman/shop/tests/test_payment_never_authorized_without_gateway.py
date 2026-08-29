"""O invariante do dinheiro: NADA fica autorizado sem o gateway ter dito que sim.

Nasceu de um P0 do alpha (pedido E54): o cliente escolhia **cartão**, nunca via a
página do Stripe, e o acompanhamento já anunciava "Pagamento autorizado". A
cadeia inteira era:

1. ``SHOPMAN_CARD_ADAPTER`` apontava para ``payment_mock`` (é o default do
   ``settings.py`` e o valor do spec do alpha);
2. ``payment_mock.create_intent`` autorizava o intent no ato (``auto_authorize``
   nascia ``True``), sem gateway nenhum e sem ``checkout_url``;
3. ``projections.order_tracking`` lê ``live_state == "authorized"`` e desenha o
   degrau ``payment_authorized`` — "Cartão autorizado";
4. um minuto depois, a confirmação otimista aceitava o pedido e
   ``lifecycle._on_accepted`` via "cartão + autorizado" e mandava
   ``payment.capture()``, que no mock captura INCONDICIONALMENTE.

Resultado: pedido pago, estoque baixado, pão entregue, zero dinheiro.

Nenhum teste pegou porque todos partiam de um intent já no estado desejado (o
``PaymentService.authorize()`` explícito das fixtures) — ninguém perguntava
*quem tinha direito* de pôr o intent naquele estado. Os testes abaixo perguntam
exatamente isso, e cada um falha com o código anterior ao conserto.
"""

from __future__ import annotations

import pytest
from django.test import TestCase, override_settings
from shopman.orderman.models import Order
from shopman.payman import PaymentService

# Configuração ERRADA de propósito: cartão apontado para o simulador. É o que o
# alpha tinha no dia do E54, e o que estes testes existem para tornar impossível.
MOCK_ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_mock",
    "cash": None,
    "external": None,
}

STRIPE_ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_stripe",
    "cash": None,
    "external": None,
}

NO_ADAPTERS = {"pix": None, "card": None, "cash": None, "external": None}


def _card_order(ref: str, *, total_q: int = 1600) -> Order:
    """Pedido de cartão cru — sem passar pelo lifecycle, que já chama initiate."""
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        status="new",
        total_q=total_q,
        handle_type="phone",
        handle_ref="5543999990000",
        data={"payment": {"method": "card"}},
    )


def _pix_order(ref: str, *, total_q: int = 1600) -> Order:
    order = _card_order(ref, total_q=total_q)
    order.data = {"payment": {"method": "pix"}}
    order.save(update_fields=["data"])
    return order


def _intents(order: Order):
    from shopman.payman.models import PaymentIntent

    return list(PaymentIntent.objects.filter(order_ref=order.ref))


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS)
class MockNeverAuthorizesTests(TestCase):
    """O simulador cria cobrança; quem autoriza é gateway, e ele não é um."""

    def test_mock_card_creates_no_intent_at_all(self) -> None:
        """Cartão no simulador não vira cobrança nenhuma — vira falha visível."""
        from shopman.shop.services import payment as payment_svc

        order = _card_order("ORD-MOCK-CARD-REFUSED")
        payment_svc.initiate(order)

        order.refresh_from_db()
        assert _intents(order) == [], "o simulador criou uma cobrança de cartão"
        assert order.data["payment"].get("error"), (
            "o pedido seguiu sem registrar que o pagamento não pôde ser preparado"
        )

    def test_mock_pix_intent_is_born_pending(self) -> None:
        """Pix idem: o QR existe, o pagamento não — só o app do banco autoriza."""
        from shopman.shop.services import payment as payment_svc

        order = _card_order("ORD-MOCK-PIX-PENDING")
        order.data = {"payment": {"method": "pix"}}
        order.save(update_fields=["data"])
        payment_svc.initiate(order)

        intents = _intents(order)
        assert len(intents) == 1
        assert intents[0].status == "pending"

    def test_mock_card_never_reports_authorized(self) -> None:
        """Nem por acidente: nenhum intent de cartão do simulador é autorizado."""
        from shopman.shop.services import payment as payment_svc

        order = _card_order("ORD-MOCK-CARD-NOAUTH")
        payment_svc.initiate(order)

        assert not any(i.status == "authorized" for i in _intents(order))
        assert not payment_svc.has_sufficient_captured_payment(order)

    def test_tracking_never_says_authorized_for_a_mock_card(self) -> None:
        """O contrato da TELA, não só o do banco.

        Este é o teste que o cliente teria escrito: qualquer que seja o degrau
        mostrado, ele não pode ser ``payment_authorized`` enquanto nenhum gateway
        autorizou nada.
        """
        from shopman.shop.projections import order_tracking
        from shopman.shop.services import payment as payment_svc

        order = _card_order("ORD-MOCK-CARD-PROMISE")
        payment_svc.initiate(order)
        order.refresh_from_db()


        projection = order_tracking.build_tracking(order)
        assert projection.promise.state != "payment_authorized", (
            "a tela anunciou pagamento autorizado sem gateway nenhum ter falado"
        )


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS)
class MockRefusesOutsideDevTests(TestCase):
    """``SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS`` vira porta de RUNTIME, não só check.

    Antes ela só existia para o ``manage.py check --deploy`` (``SHOPMAN_E003``).
    Um deploy de produção com o adapter de cartão no mock subia inteiro e fingia
    pagamento em silêncio.
    """

    @override_settings(DEBUG=False, SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=False)
    def test_create_intent_raises_outside_debug(self) -> None:
        from shopman.shop.adapters import payment_mock

        with pytest.raises(payment_mock.MockGatewayNotAllowed):
            payment_mock.create_intent(order_ref="ORD-X", amount_q=1000, method="pix")

    @override_settings(DEBUG=False, SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=False)
    def test_capture_raises_outside_debug(self) -> None:
        from shopman.shop.adapters import payment_mock

        with pytest.raises(payment_mock.MockGatewayNotAllowed):
            payment_mock.capture("PAY-WHATEVER")

    @override_settings(DEBUG=False, SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=False)
    def test_initiate_fails_closed_and_creates_no_authorization(self) -> None:
        """Falhar fechado: erro explícito no pedido, nenhum intent autorizado."""
        from shopman.shop.services import payment as payment_svc

        order = _pix_order("ORD-MOCK-BLOCKED")
        payment_svc.initiate(order)

        order.refresh_from_db()
        assert order.data["payment"].get("error"), "o pedido não registrou a falha"
        assert not any(i.status == "authorized" for i in _intents(order))

    @override_settings(DEBUG=False, SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True)
    def test_staging_opt_in_still_runs_for_pix(self) -> None:
        """Staging técnico com opt-in explícito continua rodando Pix — pendente."""
        from shopman.shop.services import payment as payment_svc

        order = _pix_order("ORD-MOCK-STAGING")
        payment_svc.initiate(order)

        intents = _intents(order)
        assert len(intents) == 1
        assert intents[0].status == "pending"


class NoAdapterFailsClosedTests(TestCase):
    """"Ninguém configurou gateway" não pode resolver para o simulador."""

    @override_settings(SHOPMAN_PAYMENT_ADAPTERS=NO_ADAPTERS)
    def test_initiate_without_adapter_records_error_and_no_intent(self) -> None:
        from shopman.shop.services import payment as payment_svc

        order = _card_order("ORD-NO-ADAPTER")
        payment_svc.initiate(order)

        order.refresh_from_db()
        assert order.data["payment"].get("error")
        assert _intents(order) == []

    def test_builtin_default_does_not_resolve_to_the_simulator(self) -> None:
        """Sem a setting, o registry não pode cair no mock por conta própria."""
        from shopman.shop.adapters import _DEFAULTS

        assert _DEFAULTS["payment"]["card"] is None
        assert _DEFAULTS["payment"]["pix"] is None


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS)
class AcceptedOrderIsNotCapturedWithoutGatewayTests(TestCase):
    """A segunda metade da perda de receita: o ``_on_accepted`` capturando.

    ``lifecycle._on_accepted`` captura quando vê "cartão + autorizado". Com o
    mock autorizando sozinho, a confirmação otimista (``web`` é
    ``payment.timing=post_commit`` + ``auto_confirm``) capturava a autorização
    de mentira sem humano nenhum no meio.
    """

    def test_accept_does_not_capture_a_pending_card_intent(self) -> None:
        """Cobrança criada no gateway, cliente ainda não pagou: aceitar não captura.

        O intent nasce ``pending`` no Stripe (o cliente ainda vai ao Checkout).
        Só o webhook o promove a ``authorized``. Se o ``_on_accepted`` capturasse
        um ``pending``, ou se algo o autorizasse por dedução, seria a mesma perda
        de dinheiro por outra porta.
        """
        from shopman.shop.lifecycle import dispatch
        from shopman.shop.services import payment as payment_svc

        order = _card_order("ORD-CARD-ACCEPT")
        intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="card",
            gateway="stripe",
            gateway_id="cs_test_pending",
        )
        order.data["payment"]["intent_ref"] = intent.ref
        order.save(update_fields=["data"])

        order.status = "accepted"
        order.save(update_fields=["status"])
        dispatch(order, "on_accepted")

        order.refresh_from_db()
        assert PaymentService.get(intent.ref).status == "pending"
        assert PaymentService.captured_total(intent.ref) == 0, (
            "aceitar o pedido capturou uma cobrança que o cliente nunca pagou"
        )
        assert not payment_svc.has_sufficient_captured_payment(order)


class StripeFailsClosedWithoutCredentialsTests(TestCase):
    """Gateway real sem credencial também falha fechado — e antes da rede."""

    @override_settings(
        SHOPMAN_PAYMENT_ADAPTERS=STRIPE_ADAPTERS,
        SHOPMAN_STRIPE={"secret_key": "", "publishable_key": "", "webhook_secret": ""},
    )
    def test_missing_secret_key_raises_before_any_network_call(self) -> None:
        from shopman.shop.adapters import payment_stripe

        with pytest.raises(payment_stripe.StripeNotConfigured):
            payment_stripe._get_stripe()

    @override_settings(
        SHOPMAN_PAYMENT_ADAPTERS=STRIPE_ADAPTERS,
        SHOPMAN_STRIPE={"secret_key": "", "publishable_key": "", "webhook_secret": ""},
    )
    def test_initiate_without_credentials_does_not_authorize(self) -> None:
        from shopman.shop.services import payment as payment_svc

        order = _card_order("ORD-STRIPE-NOCREDS")
        payment_svc.initiate(order)

        order.refresh_from_db()
        assert order.data["payment"].get("error")
        assert not any(i.status == "authorized" for i in _intents(order))


class StripeTestModeIsDerivedFromTheKeyTests(TestCase):
    """O modo de teste sai da CHAVE. Nunca de ``DEBUG``, nunca de flag manual.

    Flag manual é exatamente o tipo de coisa que vaza para produção — e aqui ela
    decidiria se números de cartão de teste aparecem numa loja de verdade.
    """

    def _stripe(self, **kwargs) -> dict:
        base = {"secret_key": "", "publishable_key": "", "webhook_secret": ""}
        base.update(kwargs)
        return base

    def test_pk_test_is_test_mode(self) -> None:
        from shopman.shop.adapters import payment_stripe

        with override_settings(SHOPMAN_STRIPE=self._stripe(publishable_key="pk_test_abc")):
            assert payment_stripe.test_mode() is True

    def test_pk_live_is_not_test_mode(self) -> None:
        from shopman.shop.adapters import payment_stripe

        with override_settings(SHOPMAN_STRIPE=self._stripe(publishable_key="pk_live_abc")):
            assert payment_stripe.test_mode() is False

    def test_mixed_keys_are_treated_as_live(self) -> None:
        """Meia configuração é erro, e na dúvida a resposta segura é produção."""
        from shopman.shop.adapters import payment_stripe

        with override_settings(
            SHOPMAN_STRIPE=self._stripe(publishable_key="pk_test_abc", secret_key="sk_live_abc"),
        ):
            assert payment_stripe.test_mode() is False

    def test_absent_keys_are_not_test_mode(self) -> None:
        from shopman.shop.adapters import payment_stripe

        with override_settings(SHOPMAN_STRIPE=self._stripe()):
            assert payment_stripe.test_mode() is False

    @override_settings(DEBUG=True)
    def test_debug_alone_does_not_turn_on_test_mode(self) -> None:
        from shopman.shop.adapters import payment_stripe

        with override_settings(SHOPMAN_STRIPE=self._stripe(publishable_key="pk_live_abc")):
            assert payment_stripe.test_mode() is False


class TestCardsOnlyExistInTestModeTests(TestCase):
    """Os números de teste são conteúdo de alpha — não podem existir em produção.

    Não basta esconder na tela: se a projection carregar a lista, ela viaja no
    JSON e fica no HTML. Por isso a lista nasce VAZIA quando a chave é ``live``.
    """

    def _stripe(self, publishable: str) -> dict:
        return {"secret_key": "", "publishable_key": publishable, "webhook_secret": ""}

    @override_settings(SHOPMAN_PAYMENT_ADAPTERS=STRIPE_ADAPTERS)
    def test_test_key_lists_the_cards(self) -> None:
        from shopman.storefront.presentation.checkout import _stripe_test_cards

        with override_settings(SHOPMAN_STRIPE=self._stripe("pk_test_abc")):
            cards = _stripe_test_cards()

        numbers = [c.number for c in cards]
        assert "4242 4242 4242 4242" in numbers
        assert any("recus" in c.label.lower() for c in cards)
        assert any("autentica" in c.label.lower() for c in cards)

    @override_settings(SHOPMAN_PAYMENT_ADAPTERS=STRIPE_ADAPTERS)
    def test_live_key_lists_nothing(self) -> None:
        from shopman.storefront.presentation.checkout import _stripe_test_cards

        with override_settings(SHOPMAN_STRIPE=self._stripe("pk_live_abc")):
            assert _stripe_test_cards() == ()

    @override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_ADAPTERS)
    def test_non_stripe_card_gateway_lists_nothing(self) -> None:
        from shopman.storefront.presentation.checkout import _stripe_test_cards

        with override_settings(SHOPMAN_STRIPE=self._stripe("pk_test_abc")):
            assert _stripe_test_cards() == ()

    @override_settings(DEBUG=True, SHOPMAN_PAYMENT_ADAPTERS=STRIPE_ADAPTERS)
    def test_debug_does_not_conjure_the_cards_on_a_live_key(self) -> None:
        from shopman.storefront.presentation.checkout import _stripe_test_cards

        with override_settings(SHOPMAN_STRIPE=self._stripe("pk_live_abc")):
            assert _stripe_test_cards() == ()


class PaymentAdapterNeverSubstitutesAnotherMethodTests(TestCase):
    """Método não configurado é ausência — nunca "o outro adapter do dicionário"."""

    @override_settings(SHOPMAN_PAYMENT_ADAPTERS={"pix": "shopman.shop.adapters.payment_mock"})
    def test_missing_card_key_does_not_fall_back_to_the_pix_adapter(self) -> None:
        from shopman.shop.adapters import get_adapter

        assert get_adapter("payment", method="card") is None

    @override_settings(SHOPMAN_PAYMENT_ADAPTERS={"pix": "shopman.shop.adapters.payment_mock"})
    def test_order_with_unconfigured_method_fails_closed(self) -> None:
        from shopman.shop.services import payment as payment_svc

        order = _card_order("ORD-METHOD-MISSING")
        payment_svc.initiate(order)

        order.refresh_from_db()
        assert order.data["payment"].get("error")
        assert _intents(order) == []
