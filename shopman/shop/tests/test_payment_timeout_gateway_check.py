"""Timeout de PIX consulta o gateway antes de cancelar (webhook perdido ≠ não pago).

Regressão do audit pré-go-live: um webhook EFI perdido deixava o pedido "não
pago" localmente; o timeout então CANCELAVA um pedido com dinheiro capturado no
gateway, sem refund. Agora o auto-cancel só acontece com resposta definitiva do
gateway de que não há pagamento; estado incerto adia a decisão.

⚠️ **Segunda regressão, auditoria adversarial de 20/08/2026.** A pergunta era
feita com ``adapter.capture()`` — verbo de ESCRITA. No adapter da Efí capture é
"confere e, se CONCLUIDA, reconcilia", então ninguém percebeu; no
``payment_mock`` ele captura INCONDICIONALMENTE. Com o mock configurado (staging),
todo PIX que vencia sem ninguém pagar era promovido a "pago" — e o gatilho era o
próprio cliente recarregando o acompanhamento, que chama
``resolve_timeouts_if_due`` a cada GET.

Estes testes passavam durante todo esse tempo porque o dublê de adapter definia
**só** ``capture``: eles afirmavam a política certa sobre um mecanismo que não é o
dos adapters reais. Por isso o dublê agora modela os dois verbos, e a regressão do
mock (``test_mock_adapter_*``) roda contra o **adapter de verdade**, sem dublê.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Channel
from shopman.shop.services import payment as payment_service
from shopman.shop.services.customer_orders import resolve_payment_timeout_if_due

pytestmark = pytest.mark.django_db


@pytest.fixture
def overdue_pix_order(db):
    from shopman.payman import PaymentService

    Channel.objects.create(ref="web", name="Web")
    PaymentService.create_intent(
        "ORD-PIX-TIMEOUT", 5000, "pix", gateway="efi", ref="INT-PIX-1"
    )
    expired = (timezone.now() - timedelta(minutes=5)).isoformat()
    return Order.objects.create(
        ref="ORD-PIX-TIMEOUT",
        channel_ref="web",
        status=Order.Status.NEW,
        total_q=5000,
        data={
            "fulfillment_type": "pickup",
            "payment": {
                "method": "pix",
                "intent_ref": "INT-PIX-1",
                "expires_at": expired,
            },
        },
    )


def _stub_adapter(gateway_state, capture_result=None):
    """Dublê com os DOIS verbos, como todo adapter de pagamento real tem.

    ``check_gateway_status`` é a leitura (o que o gateway diz) e ``capture`` é a
    escrita (reconciliar o que o gateway confirmou). Um dublê que só tem capture
    descreve um adapter que não existe — foi assim que a regressão do mock passou.
    """
    return SimpleNamespace(
        check_gateway_status=lambda intent_ref: gateway_state,
        capture=lambda intent_ref: capture_result,
    )


def test_gateway_paid_blocks_cancel_and_promotes_order(overdue_pix_order):
    paid = SimpleNamespace(success=True, transaction_id="txid-1", amount_q=5000, error_code="")
    adapter = _stub_adapter("captured", paid)
    with patch.object(payment_service, "get_adapter", return_value=adapter):
        cancelled = resolve_payment_timeout_if_due(overdue_pix_order)

    assert cancelled is False
    overdue_pix_order.refresh_from_db()
    assert overdue_pix_order.status != Order.Status.CANCELLED
    assert overdue_pix_order.data["payment"]["captured_at"]


def test_gateway_unreachable_defers_cancel(overdue_pix_order):
    adapter = _stub_adapter("error")
    with patch.object(payment_service, "get_adapter", return_value=adapter):
        cancelled = resolve_payment_timeout_if_due(overdue_pix_order)

    assert cancelled is False
    overdue_pix_order.refresh_from_db()
    assert overdue_pix_order.status == Order.Status.NEW  # decisão adiada, não cancelado


def test_gateway_confirms_unpaid_allows_cancel(overdue_pix_order):
    adapter = _stub_adapter("pending")
    with patch.object(payment_service, "get_adapter", return_value=adapter):
        cancelled = resolve_payment_timeout_if_due(overdue_pix_order)

    assert cancelled is True
    overdue_pix_order.refresh_from_db()
    assert overdue_pix_order.status == Order.Status.CANCELLED


def test_intent_that_never_existed_is_unpaid_not_uncertain(overdue_pix_order):
    """Intent inexistente é AUSÊNCIA de pagamento, não incerteza.

    São respostas diferentes com consequências opostas: incerteza adia (e a
    directive de timeout tenta de novo), ausência cancela. Confundi-las fazia o
    handler de timeout tentar para sempre um pedido que nunca teve cobrança.
    """
    adapter = _stub_adapter("not_found")
    with patch.object(payment_service, "get_adapter", return_value=adapter):
        state = payment_service.verify_gateway_before_timeout_cancel(overdue_pix_order)

    assert state == "unpaid"


def test_paid_promotion_dispatches_on_paid_once_under_double_resolve(overdue_pix_order):
    """Dois resolvers concorrentes veem 'paid' mas on_paid dispara UMA vez
    (lock + re-check de captured_at)."""
    paid = SimpleNamespace(success=True, transaction_id="txid-1", amount_q=5000, error_code="")
    adapter = _stub_adapter("captured", paid)
    calls = []
    with patch.object(payment_service, "get_adapter", return_value=adapter), \
         patch("shopman.shop.lifecycle.dispatch", side_effect=lambda o, p: calls.append(p)):
        s1 = payment_service.verify_gateway_before_timeout_cancel(overdue_pix_order)
        # Segundo resolver, mesmo pedido, já promovido.
        overdue_pix_order.refresh_from_db()
        s2 = payment_service.verify_gateway_before_timeout_cancel(overdue_pix_order)

    assert s1 == "paid" and s2 == "paid"
    assert calls.count("on_paid") == 1  # nunca duplica


def test_adapter_without_read_verb_never_invents_payment(overdue_pix_order):
    """Adapter sem ``check_gateway_status`` não autoriza captura por dedução.

    Inventar pagamento é pior do que adiar o cancelamento por mais uma rodada, e
    é isto que impede a regressão de voltar por um adapter novo que esqueça o
    verbo de leitura.
    """
    exploded = SimpleNamespace(
        capture=lambda intent_ref: pytest.fail("capture() não pode ser chamado para PERGUNTAR")
    )
    with patch.object(payment_service, "get_adapter", return_value=exploded):
        state = payment_service.verify_gateway_before_timeout_cancel(overdue_pix_order)

    assert state == "indeterminate"
    overdue_pix_order.refresh_from_db()
    assert not overdue_pix_order.data["payment"].get("captured_at")


# ── Regressão contra o ADAPTER DE VERDADE, sem dublê ──────────────────────────
#
# O defeito vivia na diferença entre o adapter real e o dublê. Testar com dublê
# aqui seria repetir o erro que deixou o furo passar.


def test_mock_adapter_unpaid_pix_is_not_promoted_to_paid(overdue_pix_order):
    """PIX vencido que NINGUÉM pagou não pode virar pago com o adapter mock.

    Era o caminho que o próprio cliente disparava recarregando o acompanhamento.
    """
    from shopman.shop.adapters import payment_mock

    with patch.object(payment_service, "get_adapter", return_value=payment_mock), \
         patch("shopman.shop.lifecycle.dispatch") as dispatched:
        state = payment_service.verify_gateway_before_timeout_cancel(overdue_pix_order)

    assert state == "unpaid"
    assert not dispatched.called
    overdue_pix_order.refresh_from_db()
    assert not overdue_pix_order.data["payment"].get("captured_at")

    from shopman.payman import PaymentService

    assert PaymentService.captured_total("INT-PIX-1") == 0


def test_mock_adapter_paid_pix_is_still_promoted(overdue_pix_order):
    """Controle positivo: capturado de propósito continua sendo promovido.

    A proteção contra webhook perdido — a razão de a função existir — não pode
    ter sido perdida junto com o conserto.

    Este caso guarda um SEGUNDO buraco, que já existia: aqui o Payman está
    reconciliado ANTES da verificação, e recapturar um intent já capturado devolve
    ``invalid_transition``. Como qualquer falha que não fosse "error" era lida
    como "não pago", o pedido — efetivamente pago — era CANCELADO. Agora a
    captura existente é reconhecida em vez de refeita.
    """
    from shopman.payman import PaymentService

    from shopman.shop.adapters import payment_mock

    PaymentService.authorize("INT-PIX-1", gateway_id="mock-txid")
    PaymentService.capture("INT-PIX-1")

    with patch.object(payment_service, "get_adapter", return_value=payment_mock), \
         patch("shopman.shop.lifecycle.dispatch") as dispatched:
        state = payment_service.verify_gateway_before_timeout_cancel(overdue_pix_order)

    assert state == "paid"
    assert dispatched.called
    overdue_pix_order.refresh_from_db()
    assert overdue_pix_order.data["payment"]["captured_at"]


# ── O botão de simular não é afordância de cliente ────────────────────────────


@override_settings(DEBUG=False, SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True, SHOPMAN_EXPOSE_MOCK_CAPTURE=False)
def test_allow_mock_adapters_does_not_expose_capture_to_customers():
    """Rodar com gateway simulado ≠ deixar o cliente quitar o próprio pedido.

    Era a mesma env respondendo as duas perguntas, e por isso a loja pública de
    staging exibia "Simular pagamento" na tela de Pix de qualquer visitante.
    """
    assert payment_service.mock_capture_allowed() is False


@override_settings(DEBUG=False, SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True, SHOPMAN_EXPOSE_MOCK_CAPTURE=True)
def test_explicit_switch_turns_the_test_affordance_back_on():
    """Quem conduz uma rodada de testes liga o interruptor próprio, conscientemente."""
    assert payment_service.mock_capture_allowed() is True


@override_settings(DEBUG=True, SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=False, SHOPMAN_EXPOSE_MOCK_CAPTURE=False)
def test_local_development_keeps_the_button():
    """Em DEBUG o botão continua onde sempre esteve — ninguém desenvolve sem ele."""
    assert payment_service.mock_capture_allowed() is True


# ── Ambiente híbrido: PIX simulado, cartão de verdade ─────────────────────────
#
# É a configuração escolhida para o alpha — o roteiro de teste precisa do PIX
# simulado, e o cartão vai para o Stripe test, que aceita qualquer valor.

_HIBRIDO = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_stripe",
    "cash": None,
    "external": None,
}


@override_settings(DEBUG=False, SHOPMAN_EXPOSE_MOCK_CAPTURE=True, SHOPMAN_PAYMENT_ADAPTERS=_HIBRIDO)
def test_simulated_capture_follows_the_adapter_not_the_method_name():
    """Simular só vale para o método cujo gateway é simulado.

    ``mock_confirm`` captura falando direto com o Payman, sem passar pelo adapter:
    "simular" um cartão que está no Stripe test gravaria captura local que o
    Stripe não tem. A regra deriva da configuração — no dia em que o PIX apontar
    para a Efí, o botão some sozinho.
    """
    assert payment_service.mock_capture_allowed("pix") is True
    assert payment_service.mock_capture_allowed("card") is False
    # Sem método, a pergunta é só do ambiente (porta rápida, antes do banco).
    assert payment_service.mock_capture_allowed() is True


@override_settings(DEBUG=False, SHOPMAN_EXPOSE_MOCK_CAPTURE=True, SHOPMAN_PAYMENT_ADAPTERS=_HIBRIDO)
def test_tracking_screen_offers_simulation_only_for_the_simulated_method(overdue_pix_order):
    """A tela do acompanhamento respeita a mesma régua."""
    from shopman.shop.projections.order_tracking import _can_mock_confirm_payment

    assert _can_mock_confirm_payment(overdue_pix_order) is True

    data = dict(overdue_pix_order.data)
    data["payment"] = {**data["payment"], "method": "card"}
    overdue_pix_order.data = data
    overdue_pix_order.save(update_fields=["data"])

    assert _can_mock_confirm_payment(overdue_pix_order) is False
