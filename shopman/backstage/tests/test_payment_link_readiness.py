"""A tecla L do balcão pergunta ao adapter do LINK, não ao Stripe do cartão.

``_link_payment_available`` chamava ``stripe_card_readiness`` cravado. Com
``SHOPMAN_LINK_ADAPTER`` apontando para outro provedor, o PDV continuaria
perguntando ao Stripe se o link podia aparecer — e o link sumia exatamente
quando o Stripe do cartão não estivesse configurado. "Trocar de provedor é
trocar uma env" só é verdade se a prontidão seguir o adapter.
"""

from __future__ import annotations

import pytest

from shopman.backstage.projections.pos import _link_payment_available
from shopman.backstage.services.integration_readiness import (
    build_provider_readiness,
    payment_link_readiness,
)

pytestmark = pytest.mark.django_db

STRIPE = "shopman.shop.adapters.payment_stripe"
MOCK = "shopman.shop.adapters.payment_mock"

STRIPE_TEST_KEYS = {
    "publishable_key": "pk_test_shopman",
    "secret_key": "sk_test_shopman",
    "webhook_secret": "whsec_shopman",
    "capture_method": "manual",
    "domain": "https://staging.example.com",
}
STRIPE_EMPTY = {
    "publishable_key": "",
    "secret_key": "",
    "webhook_secret": "",
    "capture_method": "manual",
    "domain": "",
}


def _adapters(settings, *, link: str, card: str = STRIPE) -> None:
    settings.SHOPMAN_PAYMENT_ADAPTERS = {
        "pix": MOCK,
        "card": card,
        "link": link,
        "cash": None,
        "external": None,
    }


@pytest.fixture(autouse=True)
def _fora_de_producao(settings):
    # A prontidão em `runtime` cobra chave de TESTE fora de produção — que é
    # onde a suíte roda. Dito explicitamente para o teste não depender do env.
    settings.SHOPMAN_ENVIRONMENT = "staging"
    settings.DEBUG = False
    settings.SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS = False


def test_esta_na_lista_de_prontidao(settings):
    """O link tem linha própria no painel, ao lado do cartão."""
    assert any(p.provider == "payment_link" for p in build_provider_readiness())


def test_stripe_configurado_e_pronto(settings):
    _adapters(settings, link=STRIPE)
    settings.SHOPMAN_STRIPE = STRIPE_TEST_KEYS

    readiness = payment_link_readiness(mode="staging")

    assert readiness.ready
    assert readiness.provider == "payment_link"
    assert readiness.kind == "payment_link"
    assert readiness.environment == "test"
    assert _link_payment_available() is True


def test_stripe_sem_chave_nao_e_pronto(settings):
    _adapters(settings, link=STRIPE)
    settings.SHOPMAN_STRIPE = STRIPE_EMPTY

    readiness = payment_link_readiness(mode="staging")

    assert readiness.status == "warning"
    assert "STRIPE_SECRET_KEY" in readiness.missing
    assert "STRIPE_WEBHOOK_SECRET" in readiness.missing
    assert _link_payment_available() is False


def test_nao_depende_do_adapter_do_cartao(settings):
    """O defeito: o cartão no simulador escondia o link, mesmo com o Stripe de pé."""
    _adapters(settings, link=STRIPE, card=MOCK)
    settings.SHOPMAN_STRIPE = STRIPE_TEST_KEYS

    readiness = payment_link_readiness(mode="staging")

    assert readiness.ready
    assert "SHOPMAN_CARD_ADAPTER" not in readiness.missing
    assert _link_payment_available() is True


def test_chave_live_fora_de_producao_e_erro(settings):
    _adapters(settings, link=STRIPE)
    settings.SHOPMAN_STRIPE = {
        **STRIPE_TEST_KEYS,
        "publishable_key": "pk_live_shopman",
        "secret_key": "sk_live_shopman",
    }

    readiness = payment_link_readiness(mode="staging")

    assert readiness.status == "error"
    assert "STRIPE_SECRET_KEY_test" in readiness.missing
    assert _link_payment_available() is False


def test_sem_adapter_e_aviso(settings):
    _adapters(settings, link="")
    settings.SHOPMAN_STRIPE = STRIPE_TEST_KEYS

    readiness = payment_link_readiness(mode="staging")

    assert readiness.status == "warning"
    assert readiness.missing == ("SHOPMAN_LINK_ADAPTER",)
    assert _link_payment_available() is False


def test_simulador_em_debug_e_pronto(settings):
    """Em dev o simulador É a prontidão — sem chave nenhuma do Stripe."""
    settings.DEBUG = True
    _adapters(settings, link=MOCK)
    settings.SHOPMAN_STRIPE = STRIPE_EMPTY

    readiness = payment_link_readiness(mode="runtime")

    assert readiness.ready
    assert readiness.environment == "simulador"
    assert _link_payment_available() is True


def test_simulador_fora_de_debug_segue_a_politica_do_mock(settings):
    """Mesma régua do check SHOPMAN_E003/W006: opt-in vira aviso, sem opt-in é erro."""
    _adapters(settings, link=MOCK)
    settings.SHOPMAN_STRIPE = STRIPE_EMPTY

    sem_opt_in = payment_link_readiness(mode="runtime")
    assert sem_opt_in.status == "error"
    assert "SHOPMAN_LINK_ADAPTER_mock_fora_de_DEBUG" in sem_opt_in.missing
    assert _link_payment_available() is False

    settings.SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS = True
    com_opt_in = payment_link_readiness(mode="runtime")
    assert com_opt_in.status == "warning"
    assert "SHOPMAN_LINK_ADAPTER_real" in com_opt_in.missing
    # Aviso não é "pronto": o balcão continua sem oferecer o link.
    assert _link_payment_available() is False


def test_provedor_desconhecido_falha_fechado(settings):
    """A Stone, quando vier, traz a própria prontidão. Até lá: aviso, e nada de tecla L."""
    _adapters(settings, link="shopman.shop.adapters.payment_stone")
    settings.SHOPMAN_STRIPE = STRIPE_TEST_KEYS  # o Stripe inteiro de pé não conta

    readiness = payment_link_readiness(mode="staging")

    assert readiness.status == "warning"
    assert "SHOPMAN_LINK_ADAPTER_sem_prontidao_conhecida" in readiness.missing
    assert _link_payment_available() is False
