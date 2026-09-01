"""SHOPMAN_ENVIRONMENT é decisão explícita — nunca inferida de texto livre.

Regressão do defeito catalogado em docs/plans/fallbacks-perigosos-go-live.md
(item 3): a substring "staging" em DJANGO_ALLOWED_HOSTS/SHOPMAN_DOMAIN/etc.
rebaixava produção para staging, ligando o OTP de debug e desarmando as travas
de refresh_seed_dates/qa_scenarios/seed --flush/import_backup — e o guarda
SHOPMAN_E010 lia o mesmo valor envenenado, então não disparava.

Os testes re-executam o módulo config/settings.py com a env controlada, para
afirmar o comportamento real do boot, não um helper isolado.
"""

import importlib.util
from pathlib import Path

from config import settings as project_settings

_SETTINGS_PATH = Path(project_settings.__file__)

_ANTIGOS_HINTS = (
    "SHOPMAN_DOMAIN",
    "WHATSAPP_STOREFRONT_URL",
    "DJANGO_ALLOWED_HOSTS",
    "APP_DOMAIN",
    "APP_URL",
)


def _load_settings(monkeypatch, **env):
    for name in (
        *_ANTIGOS_HINTS,
        "SHOPMAN_ENVIRONMENT",
        "SHOPMAN_EXPOSE_DEBUG_OTP",
        "DJANGO_DEBUG",
        "DJANGO_SECRET_KEY",
        "SENTRY_DSN",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    spec = importlib.util.spec_from_file_location(
        "shopman_settings_under_test", _SETTINGS_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_staging_substring_nos_hosts_nao_rebaixa_producao(monkeypatch):
    settings = _load_settings(
        monkeypatch,
        DJANGO_SECRET_KEY="segredo-de-teste",
        DJANGO_ALLOWED_HOSTS=(
            "api.boulangerie.com.br,alpha-staging.boulangerie.com.br"
        ),
        SHOPMAN_DOMAIN="staging.boulangerie.com.br",
        APP_URL="https://alpha-staging.boulangerie.com.br",
    )

    assert settings.SHOPMAN_ENVIRONMENT == "production"
    assert settings.SHOPMAN_EXPOSE_DEBUG_OTP is False


def test_ausencia_da_env_fora_de_debug_falha_fechado_para_producao(monkeypatch):
    settings = _load_settings(
        monkeypatch,
        DJANGO_SECRET_KEY="segredo-de-teste",
        DJANGO_ALLOWED_HOSTS="api.boulangerie.com.br",
    )

    assert settings.SHOPMAN_ENVIRONMENT == "production"


def test_ausencia_da_env_em_debug_vira_development(monkeypatch):
    settings = _load_settings(monkeypatch, DJANGO_DEBUG="true")

    assert settings.SHOPMAN_ENVIRONMENT == "development"


def test_staging_so_existe_quando_a_env_diz_staging(monkeypatch):
    settings = _load_settings(
        monkeypatch,
        DJANGO_SECRET_KEY="segredo-de-teste",
        DJANGO_ALLOWED_HOSTS="api.boulangerie.com.br",
        SHOPMAN_ENVIRONMENT="staging",
    )

    assert settings.SHOPMAN_ENVIRONMENT == "staging"


def test_expor_otp_nasce_desligado_sem_herdar_de_nada(monkeypatch):
    """Nem staging explícito, nem DEBUG, ligam a flag sozinhos.

    Expor OTP é decisão do spec de deploy (`SHOPMAN_EXPOSE_DEBUG_OTP=true`);
    o dev local não depende deste default porque `_debug_otp_allowed` devolve
    True em DEBUG antes de ler a flag.
    """
    em_staging = _load_settings(
        monkeypatch,
        DJANGO_SECRET_KEY="segredo-de-teste",
        DJANGO_ALLOWED_HOSTS="api.boulangerie.com.br",
        SHOPMAN_ENVIRONMENT="staging",
    )
    assert em_staging.SHOPMAN_EXPOSE_DEBUG_OTP is False

    em_debug = _load_settings(monkeypatch, DJANGO_DEBUG="true")
    assert em_debug.SHOPMAN_EXPOSE_DEBUG_OTP is False

    explicito = _load_settings(
        monkeypatch,
        DJANGO_SECRET_KEY="segredo-de-teste",
        DJANGO_ALLOWED_HOSTS="api.boulangerie.com.br",
        SHOPMAN_ENVIRONMENT="staging",
        SHOPMAN_EXPOSE_DEBUG_OTP="true",
    )
    assert explicito.SHOPMAN_EXPOSE_DEBUG_OTP is True
