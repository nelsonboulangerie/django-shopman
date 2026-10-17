"""SHOPMAN_E027: dinheiro ou nota de verdade só com as portas de teste fechadas.

O E022 e o E026 barram a virada pela metade num sentido (produção com chave de
teste). Estes testes prendem o outro: chave live, Efí fora do sandbox com Pix
na Efí, ou Focus em produção, com qualquer porta de teste aberta, em qualquer
ambiente. E prendem que o alpha de hoje (tudo de teste), o ensaio do Pix
(Efí em sandbox) e o fixture de deploy da CI continuam passando.
"""

from __future__ import annotations

import pytest
from django.core.checks import registry

from shopman.shop.checks import check_live_provider_without_test_doors
from shopman.shop.models import Shop

pytestmark = pytest.mark.django_db

_EFI = "shopman.shop.adapters.payment_efi"
_STRIPE = "shopman.shop.adapters.payment_stripe"
_MOCK = "shopman.shop.adapters.payment_mock"
_FOCUS = "shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend"

_DOOR_FLAGS = (
    "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS",
    "SHOPMAN_EXPOSE_MOCK_CAPTURE",
    "SHOPMAN_MOCK_PIX_AUTO_CONFIRM",
    "SHOPMAN_STAGING_AUTOPILOT",
)


@pytest.fixture
def closed(settings):
    """Produção com tudo de teste e todas as portas fechadas: ponto de partida."""
    settings.DEBUG = False
    settings.SHOPMAN_ENVIRONMENT = "production"
    for name in _DOOR_FLAGS:
        setattr(settings, name, False)
    settings.SHOPMAN_PAYMENT_ADAPTERS = {"pix": _EFI, "card": _STRIPE, "link": _STRIPE}
    settings.SHOPMAN_FISCAL_ADAPTER = _FOCUS
    settings.SHOPMAN_STRIPE = {"secret_key": "sk_test_sintetica", "publishable_key": "pk_test_sintetica"}
    settings.SHOPMAN_EFI = {"sandbox": True}
    settings.SHOPMAN_FOCUS_NFE = {"environment": "homologacao", "base_url": ""}
    return settings


def _make_live(settings, which: str) -> str:
    """Liga um fato live e devolve o trecho que a mensagem precisa citar."""
    if which == "stripe_secret":
        settings.SHOPMAN_STRIPE = {**settings.SHOPMAN_STRIPE, "secret_key": "sk_live_sintetica"}
        return "STRIPE_SECRET_KEY live"
    if which == "stripe_publishable":
        settings.SHOPMAN_STRIPE = {**settings.SHOPMAN_STRIPE, "publishable_key": "pk_live_sintetica"}
        return "STRIPE_PUBLISHABLE_KEY live"
    if which == "efi":
        settings.SHOPMAN_EFI = {"sandbox": False}
        return "EFI_SANDBOX=false"
    if which == "focus":
        settings.SHOPMAN_FOCUS_NFE = {"environment": "producao", "base_url": ""}
        return "Focus NFe em produção"
    raise AssertionError(which)


def _open_door(settings, which: str) -> str:
    """Abre uma porta de teste e devolve o trecho que a dica precisa citar."""
    if which == "DEBUG":
        settings.DEBUG = True
        return "DJANGO_DEBUG=true"
    if which == "staging":
        settings.SHOPMAN_ENVIRONMENT = "staging"
        return "SHOPMAN_ENVIRONMENT=staging"
    if which == "pix_mock":
        settings.SHOPMAN_PAYMENT_ADAPTERS = {**settings.SHOPMAN_PAYMENT_ADAPTERS, "pix": _MOCK}
        return "SHOPMAN_PIX_ADAPTER=payment_mock"
    setattr(settings, which, True)
    return f"{which}=true"


_LIVE = ("stripe_secret", "stripe_publishable", "efi", "focus")
_DOORS = ("DEBUG", "staging", "pix_mock", *_DOOR_FLAGS)


def test_is_registered_as_deploy_check():
    assert check_live_provider_without_test_doors in registry.registry.get_checks(include_deployment_checks=True)
    assert check_live_provider_without_test_doors not in registry.registry.get_checks(include_deployment_checks=False)


@pytest.mark.parametrize("live", _LIVE)
def test_live_with_every_door_closed_passes(closed, live):
    _make_live(closed, live)
    assert check_live_provider_without_test_doors(None) == []


@pytest.mark.parametrize("door", _DOORS)
@pytest.mark.parametrize("live", _LIVE)
def test_live_with_any_open_door_fails(closed, live, door):
    if live == "efi" and door == "pix_mock":
        # Pix no simulador tira a Efí do caminho do dinheiro; coberto abaixo
        # com o cartão live, que continua sendo dinheiro.
        pytest.skip("Pix simulado desliga a Efí: não há Pix de verdade a proteger")
    fact = _make_live(closed, live)
    door_text = _open_door(closed, door)

    errors = check_live_provider_without_test_doors(None)

    assert [error.id for error in errors] == ["SHOPMAN_E027"]
    assert fact in errors[0].msg
    assert door_text in errors[0].hint
    assert "—" not in errors[0].msg + errors[0].hint


def test_half_turn_staging_with_live_stripe_lists_every_open_door(closed):
    """O estado que subia calado: chaves live com o resto do alpha intacto."""
    closed.SHOPMAN_ENVIRONMENT = "staging"
    closed.SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS = True
    closed.SHOPMAN_EXPOSE_MOCK_CAPTURE = True
    closed.SHOPMAN_PAYMENT_ADAPTERS = {"pix": _MOCK, "card": _STRIPE, "link": _STRIPE}
    closed.SHOPMAN_STRIPE = {"secret_key": "sk_live_segredo", "publishable_key": "pk_live_publica"}

    errors = check_live_provider_without_test_doors(None)

    assert len(errors) == 1
    hint = errors[0].hint
    for door in (
        "SHOPMAN_ENVIRONMENT=staging",
        "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true",
        "SHOPMAN_EXPOSE_MOCK_CAPTURE=true",
        "SHOPMAN_PIX_ADAPTER=payment_mock",
    ):
        assert door in hint
    # O check nomeia a chave, nunca o valor.
    assert "sk_live_segredo" not in str(errors)


def test_alpha_today_passes(closed):
    """Staging com tudo de teste e as portas abertas: o alpha de 10/10."""
    closed.SHOPMAN_ENVIRONMENT = "staging"
    closed.SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS = True
    closed.SHOPMAN_EXPOSE_MOCK_CAPTURE = True
    closed.SHOPMAN_PAYMENT_ADAPTERS = {"pix": _MOCK, "card": _STRIPE, "link": _STRIPE}
    assert check_live_provider_without_test_doors(None) == []


def test_pix_rehearsal_in_efi_sandbox_passes(closed):
    """D-031: Pix real na Efí, mas em sandbox, com o ambiente ainda staging."""
    closed.SHOPMAN_ENVIRONMENT = "staging"
    closed.SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS = True
    closed.SHOPMAN_PAYMENT_ADAPTERS = {"pix": _EFI, "card": _STRIPE, "link": _STRIPE}
    closed.SHOPMAN_EFI = {"sandbox": True}
    assert check_live_provider_without_test_doors(None) == []


def test_ci_deploy_fixture_without_efi_or_focus_in_the_path_passes(closed):
    """O fixture do runtime-gate: EFI_SANDBOX=false e Focus em produção escritos,
    mas Pix e cartão no simulador e sem emissor fiscal. Nada cobra nem emite."""
    closed.SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS = True
    closed.SHOPMAN_PAYMENT_ADAPTERS = {"pix": _MOCK, "card": _MOCK, "link": _MOCK}
    closed.SHOPMAN_FISCAL_ADAPTER = None
    closed.SHOPMAN_EFI = {"sandbox": False}
    closed.SHOPMAN_FOCUS_NFE = {"environment": "producao", "base_url": ""}
    assert check_live_provider_without_test_doors(None) == []


def test_focus_base_url_wins_over_the_environment_label(closed):
    """Como no adapter: base_url de produção é nota de verdade, mesmo com o rótulo de teste."""
    closed.SHOPMAN_FOCUS_NFE = {"environment": "homologacao", "base_url": "https://api.focusnfe.com.br"}
    closed.SHOPMAN_ENVIRONMENT = "staging"
    errors = check_live_provider_without_test_doors(None)
    assert [error.id for error in errors] == ["SHOPMAN_E027"]


def test_admin_override_to_efi_counts_as_real_pix(closed):
    """Shop.integrations aponta o Pix para a Efí por cima de um settings simulado."""
    Shop.objects.create(name="Nelson", integrations={"payment": {"pix": _EFI}})
    closed.SHOPMAN_ENVIRONMENT = "staging"
    closed.SHOPMAN_PAYMENT_ADAPTERS = {"pix": _MOCK, "card": _STRIPE, "link": _STRIPE}
    closed.SHOPMAN_EFI = {"sandbox": False}
    errors = check_live_provider_without_test_doors(None)
    assert [error.id for error in errors] == ["SHOPMAN_E027"]
    assert "EFI_SANDBOX=false" in errors[0].msg


def test_admin_override_to_mock_is_an_open_door(closed):
    Shop.objects.create(name="Nelson", integrations={"payment": {"pix": _MOCK}})
    _make_live(closed, "stripe_secret")
    errors = check_live_provider_without_test_doors(None)
    assert [error.id for error in errors] == ["SHOPMAN_E027"]
    assert "Shop.integrations[payment][pix]=payment_mock" in errors[0].hint
