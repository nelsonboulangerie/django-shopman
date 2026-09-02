"""Validade do link de pagamento — um relógio só, escrito nos dois lados.

O link é a cobrança do pedido remoto anotado no PDV. Enquanto nenhum prazo era
gravado, o único relógio era o do Stripe (24 h por conta própria) e ninguém aqui
o lia: o pedido ficava aberto, o estoque preso, e o cliente ligava dizendo que
"o link parou de funcionar".

Aqui se prova a régua (``_payment_link``), os dois adapters que emitem link
(Stripe e mock) gravando o MESMO instante no Payman e no gateway, o
``payment.initiate`` levando o prazo ao pedido e armando o ``payment.timeout``,
e os dois predicados do lifecycle que o link vira: não é entrega de balcão, e
exige captura antes do trabalho físico — mesmo no canal de ``timing="external"``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Directive, Order
from shopman.payman.models import PaymentIntent as PaymanIntent

from shopman.shop import lifecycle
from shopman.shop.adapters import _payment_link, payment_mock, payment_stripe
from shopman.shop.config import ChannelConfig
from shopman.shop.directives import PAYMENT_TIMEOUT
from shopman.shop.models import Channel
from shopman.shop.services import payment as payment_service
from shopman.shop.services.order_helpers import customer_holds_the_goods

pytestmark = pytest.mark.django_db

STRIPE_SETTINGS = {
    "secret_key": "sk_test_fake",
    "webhook_secret": "whsec_test_fake",
    "capture_method": "automatic",
    "domain": "https://shop.example.com",
}

MOCK_LINK_ADAPTERS = {
    "pix": "shopman.shop.adapters.payment_mock",
    "link": "shopman.shop.adapters.payment_mock",
    "cash": None,
    "external": None,
}


def _stripe_double(session_id: str = "cs_test_link"):
    stripe = MagicMock()
    session = MagicMock()
    session.id = session_id
    session.url = f"https://checkout.stripe.com/c/pay/{session_id}"
    session.payment_intent = None
    stripe.checkout.Session.create.return_value = session
    return stripe


# ── A régua ───────────────────────────────────────────────────────────────────


def test_default_ttl_is_the_stripe_ceiling(settings):
    """24 h, menos o minuto de folga para o relógio do Stripe."""
    settings.SHOPMAN_PAYMENT_LINK_TTL_HOURS = 24
    assert _payment_link.link_ttl() == _payment_link.LINK_TTL_MAX
    assert _payment_link.LINK_TTL_MAX == timedelta(hours=24) - timedelta(minutes=1)


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        (48, _payment_link.LINK_TTL_MAX),  # acima do teto do Stripe: preso ao teto
        (0.1, _payment_link.LINK_TTL_MIN),  # abaixo do piso (30 min): preso ao piso
        (2, timedelta(hours=2)),  # dentro da régua: vale o que a env diz
        (0.5, timedelta(minutes=30)),  # fração é aceita
        ("abc", _payment_link.LINK_TTL_MAX),  # lixo na env não derruba a venda
    ],
)
def test_ttl_is_clamped_to_the_stripe_ruler(settings, hours, expected):
    """Uma env fora da faixa não pode derrubar o ``Session.create`` com o cliente
    na frente do balcão — o valor é preso à régua, nunca mandado cru."""
    settings.SHOPMAN_PAYMENT_LINK_TTL_HOURS = hours
    assert _payment_link.link_ttl() == expected


def test_link_expires_at_is_now_plus_ttl(settings):
    settings.SHOPMAN_PAYMENT_LINK_TTL_HOURS = 2
    now = timezone.now()
    expires_at = _payment_link.link_expires_at(now)
    assert expires_at == now + timedelta(hours=2)
    assert _payment_link.link_expires_at_epoch(expires_at) == int(expires_at.timestamp())


# ── Stripe: o mesmo instante nos dois lados ───────────────────────────────────


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS, SHOPMAN_PAYMENT_LINK_TTL_HOURS=24)
def test_stripe_link_sends_the_same_deadline_to_the_gateway_and_to_payman():
    """Sem mandar ``expires_at``, o Stripe usa 24 h por conta própria e a casa
    passa a ter dois relógios — a origem do problema. Um relógio, dois lados."""
    stripe = _stripe_double()
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        intent = payment_stripe.create_intent(
            order_ref="PDV-LINK-STRIPE",
            amount_q=6300,
            method="link",
            metadata={"method": "link"},
        )

    assert intent.expires_at is not None
    assert timezone.is_aware(intent.expires_at)
    remaining = intent.expires_at - timezone.now()
    assert timedelta(hours=23, minutes=50) < remaining <= timedelta(hours=24)

    kwargs = stripe.checkout.Session.create.call_args.kwargs
    assert kwargs["expires_at"] == int(intent.expires_at.timestamp())

    db_intent = PaymanIntent.objects.get(ref=intent.intent_ref)
    assert db_intent.method == "link"
    assert db_intent.expires_at == intent.expires_at


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_stripe_card_keeps_no_deadline():
    """O cartão da loja online não ganha prazo nesta frente: lá o cliente está
    na tela, e o abandono tem a própria rede (``reconcile_with_gateway_if_due``)."""
    stripe = _stripe_double("cs_test_card")
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        intent = payment_stripe.create_intent(
            order_ref="WEB-CARD-1",
            amount_q=1000,
            method="card",
            metadata={"method": "card"},
        )

    assert intent.expires_at is None
    assert "expires_at" not in stripe.checkout.Session.create.call_args.kwargs
    assert PaymanIntent.objects.get(ref=intent.intent_ref).expires_at is None


@override_settings(SHOPMAN_STRIPE=STRIPE_SETTINGS)
def test_stripe_reused_link_intent_still_carries_its_deadline():
    """Retry com a mesma chave devolve o intent do banco — com o prazo dele,
    não sem prazo (senão o pedido perdia o ``expires_at`` no segundo ``initiate``)."""
    stripe = _stripe_double()
    with patch.object(payment_stripe, "_get_stripe", return_value=stripe):
        first = payment_stripe.create_intent(
            order_ref="PDV-LINK-RETRY",
            amount_q=6300,
            method="link",
            metadata={"method": "link"},
            idempotency_key="link-retry-1",
        )
        second = payment_stripe.create_intent(
            order_ref="PDV-LINK-RETRY",
            amount_q=6300,
            method="link",
            metadata={"method": "link"},
            idempotency_key="link-retry-1",
        )

    stripe.checkout.Session.create.assert_called_once()
    assert second.intent_ref == first.intent_ref
    assert second.expires_at == first.expires_at


# ── Mock: o dev precisa ver o vencimento ──────────────────────────────────────


@override_settings(SHOPMAN_PAYMENT_LINK_TTL_HOURS=24)
def test_mock_link_expires_on_the_same_clock():
    intent = payment_mock.create_intent(
        order_ref="PDV-LINK-MOCK",
        amount_q=6300,
        method="link",
        metadata={"method": "link"},
    )

    assert intent.expires_at is not None
    remaining = intent.expires_at - timezone.now()
    assert timedelta(hours=23, minutes=50) < remaining <= timedelta(hours=24)
    assert PaymanIntent.objects.get(ref=intent.intent_ref).expires_at == intent.expires_at
    # E continua nascendo PENDENTE: prazo não é dinheiro.
    assert intent.status == "pending"


# ── initiate: o prazo chega ao pedido e arma o timeout ────────────────────────


@override_settings(SHOPMAN_PAYMENT_ADAPTERS=MOCK_LINK_ADAPTERS, SHOPMAN_PAYMENT_LINK_TTL_HOURS=24)
def test_initiate_writes_the_deadline_on_the_order_and_arms_the_timeout():
    """``expires_at`` deixa de ser "PIX only" em ``order.data["payment"]``: é a
    chave que a tela do PDV e o aviso ao cliente leem para dizer "vale até …",
    e é o que agenda a Directive ``payment.timeout`` — a máquina inteira do
    vencimento já existia e estava parada por falta deste campo."""
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}},
    )
    order = Order.objects.create(
        ref="PDV-LINK-INIT",
        channel_ref="pdv",
        status=Order.Status.ACCEPTED,
        total_q=6300,
        data={"origin_channel": "pos", "payment": {"method": "link", "collection": "terminal"}},
    )

    payment_service.initiate(order)

    order.refresh_from_db()
    payment = order.data["payment"]
    assert payment["checkout_url"].startswith("http")
    expires_at = datetime.fromisoformat(payment["expires_at"])
    assert timezone.is_aware(expires_at)
    assert expires_at == PaymanIntent.objects.get(ref=payment["intent_ref"]).expires_at

    directive = Directive.objects.get(topic=PAYMENT_TIMEOUT, payload__order_ref=order.ref)
    assert directive.status == Directive.Status.QUEUED
    assert directive.available_at == expires_at
    assert directive.payload["intent_ref"] == payment["intent_ref"]
    assert directive.payload["expires_at"] == payment["expires_at"]


# ── O que o link vira no lifecycle ────────────────────────────────────────────


def _pos_order(**payment):
    return SimpleNamespace(
        data={
            "origin_channel": "pos",
            "fulfillment_type": "pickup",
            "payment": {"collection": "terminal", "amount_q": 1000, **payment},
        }
    )


def test_a_link_sale_is_never_a_counter_handoff():
    """O cliente do link não está na loja: paga depois, do celular, e vem buscar.
    A sacola não está na mão dele — há trajeto pela frente por definição."""
    assert customer_holds_the_goods(_pos_order(method="cash")) is True
    assert customer_holds_the_goods(_pos_order(method="link")) is False
    assert customer_holds_the_goods(_pos_order(method="LINK")) is False
    assert lifecycle._counter_handoff(_pos_order(method="link")) is False


def test_kds_asks_the_same_question():
    """Uma resposta para os dois — senão uma regra entra no lifecycle e falta no KDS."""
    from shopman.shop.services.kds import _customer_holds_the_goods

    assert _customer_holds_the_goods(_pos_order(method="link")) is False
    assert _customer_holds_the_goods(_pos_order(method="cash")) is True


def test_link_requires_captured_payment_even_on_the_external_timing_channel():
    """``timing="external"`` descreve o balcão recebendo na hora (dinheiro,
    maquininha). O link existe justamente para o pedido que NÃO está no balcão:
    o dinheiro ainda não entrou, e a cozinha e a baixa de estoque esperam."""
    Channel.objects.create(
        ref="pdv",
        name="PDV",
        is_active=True,
        config={"payment": {"method": "cash", "timing": "external"}},
    )
    config = ChannelConfig.for_channel("pdv")
    link_order = SimpleNamespace(ref="PDV-L", channel_ref="pdv", data=_pos_order(method="link").data)
    cash_order = SimpleNamespace(ref="PDV-C", channel_ref="pdv", data=_pos_order(method="cash").data)

    assert lifecycle._requires_payment_before_physical_work(link_order, config) is True
    assert lifecycle._requires_payment_before_physical_work(cash_order, config) is False
    assert lifecycle._stock_fulfill_allowed(cash_order, config) is True
    with patch.object(payment_service, "has_sufficient_captured_payment", return_value=False):
        assert lifecycle._stock_fulfill_allowed(link_order, config) is False
