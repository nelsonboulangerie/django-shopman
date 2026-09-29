"""Pagamento simulado nunca é receita — a régua única da proveniência.

O alpha roda o Pix no ``payment_mock`` com o botão "Simular pagamento" exposto
(``SHOPMAN_EXPOSE_MOCK_CAPTURE``). O clique percorre o caminho inteiro de um Pix
pago (``mock_confirm`` → Payman capturado → ``on_paid``), e é assim que deve ser:
o roteiro de teste precisa exercitar o que vem depois do pagamento.

O defeito era o intent simulado nascer SEM a marca de proveniência. Os leitores
financeiros (fechamento, livro do turno, B.I., conciliação) já sabiam excluir
uma confirmação ``provider_simulated`` — a Efí homologação carimba —, mas o
simulador local não carimbava, e o Pix que ninguém pagou entrava como receita.

Estes testes percorrem o caminho real (``initiate`` → ``mock_confirm``), sem
dublê no meio, e perguntam a cada leitor o que ele contou.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.models import Channel
from shopman.shop.services import payment as payment_service

pytestmark = pytest.mark.django_db

_ALPHA = {
    "pix": "shopman.shop.adapters.payment_mock",
    "card": "shopman.shop.adapters.payment_stripe",
    "cash": None,
    "external": None,
}

ALPHA_SETTINGS = {
    "DEBUG": False,
    "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS": True,
    "SHOPMAN_EXPOSE_MOCK_CAPTURE": True,
    "SHOPMAN_PAYMENT_ADAPTERS": _ALPHA,
}


def _web_pix_order(ref: str = "ORD-SIM-1", total_q: int = 4200) -> Order:
    Channel.objects.get_or_create(ref="web", defaults={"name": "Web"})
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        status=Order.Status.ACCEPTED,
        total_q=total_q,
        data={"fulfillment_type": "pickup", "payment": {"method": "pix"}},
    )


def _simulate_paid(order: Order) -> Order:
    """O clique em "Simular pagamento", pelo mesmo caminho do botão."""
    payment_service.initiate(order)
    order.refresh_from_db()
    with patch("shopman.shop.lifecycle.dispatch"):
        assert payment_service.mock_confirm(order) is True
    order.refresh_from_db()
    return order


@override_settings(**ALPHA_SETTINGS)
def test_simulated_pix_is_stamped_at_the_origin_and_captured_for_testing():
    from shopman.payman import PaymentService
    from shopman.payman.models import PaymentIntent

    order = _simulate_paid(_web_pix_order())

    intent_ref = order.data["payment"]["intent_ref"]
    intent = PaymentIntent.objects.get(ref=intent_ref)
    # O teste continua funcionando: o pagamento simulado é capturado de verdade
    # no livro do Payman, e o lifecycle anda como num Pix pago.
    assert intent.gateway == "mock"
    assert PaymentService.captured_total(intent_ref) == 4200
    assert payment_service.get_payment_status(order) == "captured"
    # …mas carimbado na origem, no intent e no pedido.
    assert intent.gateway_data["confirmation_mode"] == "provider_simulated"
    assert intent.gateway_data["provider_environment"] == "local_mock"
    assert order.data["payment"]["confirmation_mode"] == "provider_simulated"
    assert order.data["payment"]["is_test_confirmation"] is True


@override_settings(**ALPHA_SETTINGS)
def test_simulated_pix_is_not_revenue_in_day_closing():
    from shopman.backstage.services.closing import _payment_method_totals

    _simulate_paid(_web_pix_order())

    assert _payment_method_totals(timezone.localdate()).get("pix", 0) == 0


@override_settings(**ALPHA_SETTINGS)
def test_simulated_pix_is_not_revenue_in_bi():
    from shopman.backstage.bi.sources import orderman as bi_orderman
    from shopman.backstage.projections.bi_explore import build_bi_explore

    order = _simulate_paid(_web_pix_order())

    assert build_bi_explore(metric="payment_received", by="payment_method").rows == ()
    now = timezone.now()
    sales, _cancelled = bi_orderman.read_sales((now - timedelta(days=1), now + timedelta(days=1)))
    assert f"{bi_orderman.SOURCE}:{order.ref}" not in {sale.ref for sale in sales}


@override_settings(**ALPHA_SETTINGS)
def test_simulated_pix_is_not_revenue_in_financial_reconciliation():
    from shopman.backstage.services.financial_reconciliation import build_financial_reconciliation

    _simulate_paid(_web_pix_order())

    report = build_financial_reconciliation(reconciliation_date=timezone.localdate())
    assert report.captured_q == 0
    assert report.net_q == 0


@override_settings(**ALPHA_SETTINGS)
def test_gestor_says_simulated_not_paid():
    from shopman.backstage.projections.order_queue import build_operator_order

    order = _simulate_paid(_web_pix_order())

    projection = build_operator_order(order)
    assert projection.payment_status == "captured"
    assert projection.payment_status_label == "Pagamento simulado, sem dinheiro"


@override_settings(**ALPHA_SETTINGS)
def test_simulated_payment_link_is_stamped_too():
    """O link do balcão no simulador também não é dinheiro."""
    from shopman.payman.models import PaymentIntent

    from shopman.shop.adapters import payment_mock

    intent = payment_mock.create_intent(order_ref="ORD-SIM-LINK", amount_q=1500, method="link")

    stored = PaymentIntent.objects.get(ref=intent.intent_ref)
    assert stored.gateway_data["confirmation_mode"] == "provider_simulated"
    assert stored.gateway_data["checkout_url"].startswith("https://pagamento.exemplo/simulado/")


# ── Stripe em modo de teste: o irmão idêntico da Efí homologação ─────────────


def test_stripe_test_key_stamps_the_charge_as_simulated():
    from shopman.shop.adapters import payment_stripe

    assert payment_stripe.provenance_metadata(test=True) == {
        "provider_environment": "test",
        "confirmation_mode": "provider_simulated",
    }
    assert payment_stripe.provenance_metadata(test=False) == {
        "provider_environment": "live",
        "confirmation_mode": "provider_live",
    }


# ── NFC-e: nota de PRODUÇÃO nunca sai para pagamento simulado ────────────────


class _FocusBackend:
    identifier = "focus"

    def __init__(self, homologation: bool):
        self.is_homologation = homologation


def _simulated_order_data(method: str = "pix") -> dict:
    return {
        "payment": {
            "method": method,
            "amount_q": 4200,
            "confirmation_mode": "provider_simulated",
            "provider_environment": "local_mock",
        }
    }


_ELETRONIC = "shopman.shop.fiscal_resolvers.eletronic_payment"


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=_ELETRONIC)
def test_production_nfce_is_refused_for_simulated_payment():
    from shopman.shop.services import fiscal

    order = Order(ref="ORD-SIM-NFCE", channel_ref="web", total_q=4200, data=_simulated_order_data())
    with patch.object(fiscal.fiscal_pool, "get_backend", return_value=_FocusBackend(homologation=False)):
        assert fiscal.emission_resolver(order) is False
        assert fiscal.emission_expected(order) is False
        assert "simulado" in fiscal.issue_override_refusal(order).lower()


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=_ELETRONIC)
def test_manager_override_cannot_force_production_nfce_for_simulated_payment():
    from shopman.shop.services import fiscal

    data = _simulated_order_data()
    data["fiscal"] = {fiscal.ISSUE_OVERRIDE_KEY: {"approved_by": "gerente"}}
    order = Order(ref="ORD-SIM-NFCE-O", channel_ref="web", total_q=4200, data=data)
    with patch.object(fiscal.fiscal_pool, "get_backend", return_value=_FocusBackend(homologation=False)):
        assert fiscal.emission_resolver(order) is False


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=_ELETRONIC)
def test_homologation_nfce_still_exercises_the_simulated_sale():
    """No alpha a Focus está em homologação: a nota não tem valor fiscal e o
    roteiro de teste continua exercitando a emissão do Pix simulado."""
    from shopman.shop.services import fiscal

    order = Order(ref="ORD-SIM-NFCE-H", channel_ref="web", total_q=4200, data=_simulated_order_data())
    with patch.object(fiscal.fiscal_pool, "get_backend", return_value=_FocusBackend(homologation=True)):
        assert fiscal.emission_resolver(order) is True


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=_ELETRONIC)
def test_backend_without_environment_is_treated_as_real():
    """Backend que não declara o ambiente é tratado como produção: falha fechado."""
    from shopman.shop.services import fiscal

    class _Unknown:
        identifier = "other"

    order = Order(ref="ORD-SIM-NFCE-U", channel_ref="web", total_q=4200, data=_simulated_order_data())
    with patch.object(fiscal.fiscal_pool, "get_backend", return_value=_Unknown()):
        assert fiscal.emission_resolver(order) is False


@override_settings(SHOPMAN_FISCAL_EMISSION_RESOLVER=_ELETRONIC)
def test_real_payment_still_emits_in_production():
    from shopman.shop.services import fiscal

    order = Order(
        ref="ORD-LIVE-NFCE",
        channel_ref="web",
        total_q=4200,
        data={"payment": {"method": "pix", "amount_q": 4200, "confirmation_mode": "provider_live"}},
    )
    with patch.object(fiscal.fiscal_pool, "get_backend", return_value=_FocusBackend(homologation=False)):
        assert fiscal.emission_resolver(order) is True


def test_focus_backend_declares_its_environment():
    from shopman.shop.adapters.fiscal_focusnfe import FocusNFeBackend

    with override_settings(SHOPMAN_FOCUS_NFE={"environment": "homologacao"}):
        assert FocusNFeBackend().is_homologation is True
    with override_settings(SHOPMAN_FOCUS_NFE={"environment": "producao"}):
        assert FocusNFeBackend().is_homologation is False
    with override_settings(
        SHOPMAN_FOCUS_NFE={"environment": "homologacao", "base_url": "https://api.focusnfe.com.br"}
    ):
        assert FocusNFeBackend().is_homologation is False


@override_settings(**ALPHA_SETTINGS)
def test_gestor_card_does_not_paint_simulated_payment_green():
    from shopman.backstage.projections.order_queue import _payment_tone

    order = _simulate_paid(_web_pix_order())

    assert _payment_tone(order, "pix", "captured", order.data["payment"]) == "warning"
