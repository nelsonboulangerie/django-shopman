"""O Stripe falso do harness responde as chamadas que o adapter faz depois do pagamento (F-7).

O ``payment_stripe`` de produção roda inteiro contra o fake (só o ``api_base`` muda), então
o contrato que importa é o do SDK oficial: as MESMAS chamadas do adapter (captura com
``expand``, anulação, expiração da sessão, estorno com chave de idempotência), feitas pelo
SDK, contra o servidor de verdade num thread. Sem isto, as jornadas de cartão (J6, #2986;
J8, #2987) morriam na primeira chamada depois do pagamento com "ROTA NÃO IMPLEMENTADA".
"""

from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

import pytest
import stripe

from shopman.shop.tests.e2e.fake_stripe import FakeStripe, _handler


@pytest.fixture
def fake():
    fake = FakeStripe(public_base="http://127.0.0.1", webhook_url="http://127.0.0.1:9/none", webhook_secret="whsec_x")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(fake))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    previous = (stripe.api_base, stripe.api_key, stripe.max_network_retries)
    stripe.api_base = f"http://127.0.0.1:{server.server_address[1]}"
    stripe.api_key = "sk_test_e2e_fake_local_only"
    stripe.max_network_retries = 0
    try:
        yield fake
    finally:
        stripe.api_base, stripe.api_key, stripe.max_network_retries = previous
        server.shutdown()
        server.server_close()


def _paid_session(fake: FakeStripe, *, amount: int = 2500, capture_method: str = "manual"):
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "brl", "unit_amount": amount, "product_data": {"name": "Pedido"}}, "quantity": 1}],
        payment_intent_data={"capture_method": capture_method, "metadata": {"order_ref": "ORD-1"}},
        success_url="http://loja/ok",
        cancel_url="http://loja/cancel",
    )
    fake.pay(session.id)
    return stripe.checkout.Session.retrieve(session.id)


def test_leitura_expandida_traz_a_cobranca_com_credito(fake):
    session = _paid_session(fake)
    intent = stripe.PaymentIntent.retrieve(session.payment_intent, expand=["latest_charge"])

    assert intent.status == "requires_capture"
    assert intent.latest_charge.id.startswith("ch_")
    assert intent.latest_charge.payment_method_details.card.funding == "credit"


def test_captura_inteira_e_parcial_da_autorizacao(fake):
    session = _paid_session(fake, amount=2500)
    captured = stripe.PaymentIntent.capture(session.payment_intent, expand=["latest_charge"], amount_to_capture=2000)

    assert captured.status == "succeeded"
    assert captured.amount_received == 2000
    assert captured.latest_charge.amount_captured == 2000

    # Capturar de novo é recusado, como no Stripe: o adapter relê antes de capturar.
    with pytest.raises(stripe.InvalidRequestError):
        stripe.PaymentIntent.capture(session.payment_intent)


def test_anular_a_autorizacao_e_recusar_anular_o_capturado(fake):
    authorized = _paid_session(fake)
    canceled = stripe.PaymentIntent.cancel(authorized.payment_intent)
    assert canceled.status == "canceled"

    paid = _paid_session(fake, capture_method="automatic")
    with pytest.raises(stripe.InvalidRequestError):
        stripe.PaymentIntent.cancel(paid.payment_intent)


def test_expirar_a_sessao_aberta_e_so_ela(fake):
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price_data": {"currency": "brl", "unit_amount": 1000, "product_data": {"name": "P"}}, "quantity": 1}],
        payment_intent_data={"capture_method": "manual"},
        success_url="http://loja/ok",
        cancel_url="http://loja/cancel",
    )
    expired = stripe.checkout.Session.expire(session.id)
    assert expired.status == "expired"

    with pytest.raises(stripe.InvalidRequestError):
        stripe.checkout.Session.expire(session.id)


def test_estorno_idempotente_parcial_e_sem_passar_do_capturado(fake):
    session = _paid_session(fake, amount=3000, capture_method="automatic")

    first = stripe.Refund.create(payment_intent=session.payment_intent, amount=1000, idempotency_key="estorno-1")
    again = stripe.Refund.create(payment_intent=session.payment_intent, amount=1000, idempotency_key="estorno-1")
    assert first.id == again.id
    assert first.amount == 1000
    assert first.status == "succeeded"

    rest = stripe.Refund.create(payment_intent=session.payment_intent)
    assert rest.amount == 2000

    intent = stripe.PaymentIntent.retrieve(session.payment_intent, expand=["latest_charge"])
    assert intent.latest_charge.amount_refunded == 3000
    assert intent.latest_charge.refunded is True

    with pytest.raises(stripe.InvalidRequestError):
        stripe.Refund.create(payment_intent=session.payment_intent, amount=1)


def test_estorno_de_autorizacao_nao_capturada_e_recusado(fake):
    session = _paid_session(fake, capture_method="manual")

    with pytest.raises(stripe.InvalidRequestError):
        stripe.Refund.create(payment_intent=session.payment_intent)
