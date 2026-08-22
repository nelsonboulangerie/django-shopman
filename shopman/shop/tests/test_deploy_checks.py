from base64 import b64encode
from pathlib import Path

import pytest
from django.test import override_settings

from config import settings as project_settings
from shopman.shop import checks


@override_settings(
    DEBUG=True,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
)
def test_database_backend_warns_for_sqlite_in_debug():
    messages = checks.check_database_backend(None)

    assert [message.id for message in messages] == ["SHOPMAN_W001"]


@override_settings(
    DEBUG=False,
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
)
def test_database_backend_blocks_sqlite_outside_debug():
    messages = checks.check_database_backend(None)

    assert [message.id for message in messages] == ["SHOPMAN_E007"]


@override_settings(
    DEBUG=False,
    DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "shopman"}},
)
def test_database_backend_accepts_postgres_outside_debug():
    assert checks.check_database_backend(None) == []


def test_efi_certificate_can_be_materialized_from_base64_env(tmp_path, monkeypatch):
    monkeypatch.delenv("EFI_CERTIFICATE_PATH", raising=False)
    monkeypatch.delenv("EFI_CERTIFICATE_PEM", raising=False)
    monkeypatch.setenv("SHOPMAN_RUNTIME_SECRET_DIR", str(tmp_path))
    monkeypatch.setenv("EFI_CERTIFICATE_PEM_BASE64", b64encode(b"certificate-body").decode())

    path = Path(project_settings._efi_certificate_path())

    assert path == tmp_path / "efi_certificate.pem"
    assert path.read_text() == "certificate-body"
    assert path.stat().st_mode & 0o777 == 0o600


@override_settings(
    DEBUG=False,
    SHOPMAN_EFI_WEBHOOK={"webhook_token": ""},
    SHOPMAN_IFOOD={"webhook_token": ""},
)
def test_webhook_tokens_efi_blocks_ifood_warns():
    # EFI (pagamento real) → Error bloqueante; iFood-legado (fail-closed) → Warning.
    messages = checks.check_webhook_tokens(None)
    by_id = {m.id: type(m).__name__ for m in messages}
    assert by_id.get("SHOPMAN_E004") == "Error"      # EFI bloqueia
    assert by_id.get("SHOPMAN_W008") == "Warning"    # iFood só avisa
    from django.core.checks import Error as CheckError

    assert not any(m.id == "SHOPMAN_W008" and isinstance(m, CheckError) for m in messages)


@override_settings(
    DEBUG=False,
    SHOPMAN_EFI_WEBHOOK={"webhook_token": "efi-tok"},
    SHOPMAN_IFOOD={"webhook_token": "ifood-tok"},
)
def test_webhook_tokens_all_set_no_messages():
    assert checks.check_webhook_tokens(None) == []


@override_settings(DEBUG=False, SHOPMAN_COURIER_ADAPTER=None)
def test_courier_check_silent_when_adapter_disabled():
    assert checks.check_courier_credentials(None) == []


@override_settings(
    DEBUG=False,
    SHOPMAN_COURIER_ADAPTER="shopman.shop.adapters.courier_machine",
    SHOPMAN_MACHINE={"username": "", "password": "", "api_key": "", "webhook_token": ""},
)
def test_courier_machine_without_credentials_blocks_and_warns_webhook():
    messages = checks.check_courier_credentials(None)
    by_id = {m.id: type(m).__name__ for m in messages}
    assert by_id.get("SHOPMAN_E011") == "Error"      # sem credenciais bloqueia
    assert by_id.get("SHOPMAN_W010") == "Warning"    # sem webhook_token só avisa


@override_settings(
    DEBUG=False,
    SHOPMAN_COURIER_ADAPTER="shopman.shop.adapters.courier_machine",
    SHOPMAN_MACHINE={
        "username": "u", "password": "p", "api_key": "k", "webhook_token": "tok",
    },
)
def test_courier_machine_fully_configured_no_messages():
    assert checks.check_courier_credentials(None) == []


@override_settings(DEBUG=False, MANYCHAT_WEBHOOK_SECRET="")
def test_manychat_webhook_secret_missing_is_warning_not_error():
    from django.core.checks import Error as CheckError

    messages = checks.check_guestman_webhook_secret(None)
    assert [m.id for m in messages] == ["SHOPMAN_W009"]
    assert not any(isinstance(m, CheckError) for m in messages)  # não bloqueia


@override_settings(DEBUG=False, MANYCHAT_WEBHOOK_SECRET="a-secret")
def test_manychat_webhook_secret_set_no_messages():
    assert checks.check_guestman_webhook_secret(None) == []


@override_settings(
    DEBUG=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
def test_shared_cache_backend_requires_redis_outside_debug():
    errors = checks.check_shared_cache_backend(None)

    assert [error.id for error in errors] == ["SHOPMAN_E006"]


@override_settings(
    DEBUG=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache"}},
)
def test_shared_cache_backend_accepts_redis_outside_debug():
    assert checks.check_shared_cache_backend(None) == []


@override_settings(
    DEBUG=False,
    CACHES={"default": {"BACKEND": "django_redis.cache.RedisCache"}},
)
def test_shared_cache_backend_rejects_legacy_redis_package_backend():
    errors = checks.check_shared_cache_backend(None)

    assert [error.id for error in errors] == ["SHOPMAN_E006"]


@override_settings(DEBUG=False, DOORMAN={"ACCESS_LINK_API_KEY": ""})
def test_access_link_api_key_required_outside_debug():
    errors = checks.check_doorman_access_link_api_key(None)

    assert [error.id for error in errors] == ["SHOPMAN_E008"]


@override_settings(DEBUG=False, DOORMAN={"ACCESS_LINK_API_KEY": "test-secret"})
def test_access_link_api_key_accepts_configured_secret_outside_debug():
    assert checks.check_doorman_access_link_api_key(None) == []


@override_settings(
    DEBUG=False,
    SHOPMAN_POS_BASE_URL="https://pdv.boulangerie.com.br",
    SHOPMAN_KDS_BASE_URL="",
    SHOPMAN_ORDERS_BASE_URL="",
    SHOPMAN_PRODUCTION_BASE_URL="",
    SHOPMAN_MARKETING_BASE_URL="",
    SHOPMAN_BI_BASE_URL="",
    SHOPMAN_OPERATOR_API_HOST="",
    SHOPMAN_OPERATOR_COOKIE_DOMAIN="",
)
def test_operator_surface_requires_api_host_and_cookie_domain_outside_debug():
    errors = checks.check_operator_cookie_domain(None)

    assert [error.id for error in errors] == ["SHOPMAN_E014", "SHOPMAN_E014"]


@override_settings(
    DEBUG=False,
    SHOPMAN_POS_BASE_URL="https://pdv.boulangerie.com.br",
    SHOPMAN_KDS_BASE_URL="https://kds.boulangerie.com.br",
    SHOPMAN_ORDERS_BASE_URL="https://gestor.boulangerie.com.br",
    SHOPMAN_PRODUCTION_BASE_URL="https://prod.boulangerie.com.br",
    SHOPMAN_MARKETING_BASE_URL="",
    SHOPMAN_BI_BASE_URL="",
    SHOPMAN_OPERATOR_API_HOST="api.boulangerie.com.br",
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=".boulangerie.com.br",
)
def test_operator_surface_accepts_shared_subdomain_cookie_zone():
    assert checks.check_operator_cookie_domain(None) == []


@override_settings(
    DEBUG=False,
    SHOPMAN_POS_BASE_URL="https://pdv.evil.example",
    SHOPMAN_KDS_BASE_URL="",
    SHOPMAN_ORDERS_BASE_URL="",
    SHOPMAN_PRODUCTION_BASE_URL="",
    SHOPMAN_MARKETING_BASE_URL="",
    SHOPMAN_BI_BASE_URL="",
    SHOPMAN_OPERATOR_API_HOST="api.boulangerie.com.br",
    SHOPMAN_OPERATOR_COOKIE_DOMAIN=".boulangerie.com.br",
)
def test_operator_surface_rejects_hosts_outside_cookie_domain():
    errors = checks.check_operator_cookie_domain(None)

    assert [error.id for error in errors] == ["SHOPMAN_E014"]
    assert "SHOPMAN_POS_BASE_URL=pdv.evil.example" in errors[0].hint


@override_settings(DEBUG=False, SHOPMAN_ENVIRONMENT="production", SHOPMAN_EXPOSE_DEBUG_OTP=True)
def test_debug_otp_exposure_errors_outside_non_production():
    messages = checks.check_debug_otp_exposure(None)

    assert [message.id for message in messages] == ["SHOPMAN_E010"]


@override_settings(DEBUG=False, SHOPMAN_ENVIRONMENT="staging", SHOPMAN_EXPOSE_DEBUG_OTP=True)
def test_debug_otp_exposure_warns_for_staging():
    messages = checks.check_debug_otp_exposure(None)

    assert [message.id for message in messages] == ["SHOPMAN_W007"]


@override_settings(DEBUG=False, SHOPMAN_ENVIRONMENT="production", SHOPMAN_EXPOSE_DEBUG_OTP=False)
def test_debug_otp_exposure_disabled_is_clean():
    assert checks.check_debug_otp_exposure(None) == []


@override_settings(DEBUG=False, SHOPMAN_ENVIRONMENT="production", SHOPMAN_EXPOSE_MOCK_CAPTURE=True)
def test_mock_capture_exposure_errors_in_production():
    messages = checks.check_mock_capture_exposure(None)

    assert [message.id for message in messages] == ["SHOPMAN_E015"]


@override_settings(DEBUG=False, SHOPMAN_ENVIRONMENT="staging", SHOPMAN_EXPOSE_MOCK_CAPTURE=True)
def test_mock_capture_exposure_warns_for_staging():
    messages = checks.check_mock_capture_exposure(None)

    assert [message.id for message in messages] == ["SHOPMAN_W016"]


@override_settings(DEBUG=False, SHOPMAN_ENVIRONMENT="production", SHOPMAN_EXPOSE_MOCK_CAPTURE=False)
def test_mock_capture_exposure_disabled_is_clean():
    assert checks.check_mock_capture_exposure(None) == []


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
    },
    SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=False,
)
def test_payment_mock_requires_explicit_staging_allowance_outside_debug():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_E003", "SHOPMAN_E003"]


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_mock",
        "card": "shopman.shop.adapters.payment_mock",
    },
    SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True,
)
def test_payment_mock_is_warning_when_explicitly_allowed_for_staging():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_W006", "SHOPMAN_W006"]


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_efi",
        "card": "shopman.shop.adapters.payment_stripe",
    },
    SHOPMAN_EFI={},
    SHOPMAN_STRIPE={
        "secret_key": "sk_test_123",
        "webhook_secret": "whsec_test_123",
    },
)
def test_payment_efi_adapter_requires_credentials_outside_debug():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_E009"]
    assert "EFI_CLIENT_ID" in messages[0].hint
    assert "EFI_CERTIFICATE_PATH" in messages[0].hint


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_efi",
        "card": "shopman.shop.adapters.payment_stripe",
    },
    SHOPMAN_EFI={
        "client_id": "client",
        "client_secret": "secret",
        "certificate_path": "/tmp/shopman-missing-efi-cert.pem",
        "pix_key": "pix-key",
    },
    SHOPMAN_STRIPE={
        "secret_key": "sk_test_123",
        "webhook_secret": "whsec_test_123",
    },
)
def test_payment_efi_adapter_requires_certificate_file_outside_debug():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_E009"]
    assert "arquivo existente" in messages[0].hint


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_efi",
        "card": "shopman.shop.adapters.payment_stripe",
    },
    SHOPMAN_EFI={
        "client_id": "client",
        "client_secret": "secret",
        "certificate_path": __file__,
        "pix_key": "pix-key",
    },
    SHOPMAN_STRIPE={},
)
def test_payment_stripe_adapter_requires_credentials_outside_debug():
    messages = checks.check_payment_adapters(None)

    assert [message.id for message in messages] == ["SHOPMAN_E009"]
    assert "STRIPE_SECRET_KEY" in messages[0].hint
    assert "STRIPE_WEBHOOK_SECRET" in messages[0].hint


@override_settings(
    DEBUG=False,
    SHOPMAN_PAYMENT_ADAPTERS={
        "pix": "shopman.shop.adapters.payment_efi",
        "card": "shopman.shop.adapters.payment_stripe",
    },
    SHOPMAN_EFI={
        "client_id": "client",
        "client_secret": "secret",
        "certificate_path": __file__,
        "pix_key": "pix-key",
    },
    SHOPMAN_STRIPE={
        "secret_key": "sk_test_123",
        "webhook_secret": "whsec_test_123",
    },
)
def test_real_payment_adapters_accept_complete_gateway_settings():
    assert checks.check_payment_adapters(None) == []


def test_release_readiness_runs_django_deploy_checks():
    source = (Path(__file__).resolve().parents[3] / "scripts" / "check_release_readiness.py").read_text()
    assert 'call_command("check", deploy=True' in source


# ── fiscal: resolver de emissão (silêncio fiscal é o pior modo de falha) ──────


@pytest.fixture
def selling_channel(db):
    from shopman.shop.models import Channel

    return Channel.objects.create(
        ref="pdv", name="PDV", commerce_policy=Channel.CommercePolicy.ORDER
    )


@override_settings(DEBUG=False, SHOPMAN_FISCAL_ADAPTER=None, SHOPMAN_FISCAL_EMISSION_RESOLVER="")
def test_fiscal_resolver_check_silent_without_fiscal_adapter(selling_channel):
    assert checks.check_fiscal_emission_resolver(None) == []


@override_settings(
    DEBUG=False,
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER="",
)
def test_fiscal_adapter_with_selling_channel_requires_a_resolver(selling_channel):
    messages = checks.check_fiscal_emission_resolver(None)
    assert [m.id for m in messages] == ["SHOPMAN_E013"]
    from django.core.checks import Error as CheckError

    assert isinstance(messages[0], CheckError)


@override_settings(
    DEBUG=False,
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER="",
)
def test_fiscal_resolver_check_silent_without_active_selling_channel(db):
    from shopman.shop.models import Channel

    Channel.objects.create(
        ref="menuboard", name="Menu", commerce_policy=Channel.CommercePolicy.DISPLAY
    )
    assert checks.check_fiscal_emission_resolver(None) == []


@override_settings(
    DEBUG=False,
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER="shopman.shop.fiscal_resolvers.nao_existe",
)
def test_fiscal_resolver_that_does_not_import_blocks_deploy(selling_channel):
    # O motor engole o ImportError e cai no fallback: a emissão fica desligada
    # em silêncio. É exatamente o modo de falha que o check existe para pegar.
    messages = checks.check_fiscal_emission_resolver(None)
    assert [m.id for m in messages] == ["SHOPMAN_E013"]


@override_settings(
    DEBUG=False,
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER="shopman.shop.fiscal_resolvers.always",
)
def test_fiscal_resolver_configured_is_clean(selling_channel):
    assert checks.check_fiscal_emission_resolver(None) == []


@override_settings(
    DEBUG=False,
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend",
    SHOPMAN_FISCAL_EMISSION_RESOLVER=(
        "shopman.shop.fiscal_resolvers.on_request_or_tax_id,"
        "shopman.shop.fiscal_resolvers.card_payment"
    ),
)
def test_fiscal_resolver_accepts_the_comma_separated_or_list(selling_channel):
    assert checks.check_fiscal_emission_resolver(None) == []


# ── W003: a loja oferece NFC-e e não há adapter (check que voltou a valer) ────
#
# Até 2026-08-19 o predicado era `Channel.config["fiscal"]["enabled"]`, chave que
# nenhum código do sistema escreve — o check nunca disparou uma vez. O que a
# loja realmente usa é `Shop.defaults["pos"]["fiscal_toggle"]`.


def _shop_with_pos_defaults(pos_cfg: dict):
    from shopman.shop.models import Shop

    # ``Shop.save`` já limpa o cache do singleton.
    return Shop.objects.create(name="Nelson", defaults={"pos": pos_cfg})


@pytest.fixture
def store_offering_nfce(db):
    return _shop_with_pos_defaults({"fiscal_toggle": True})


@override_settings(SHOPMAN_FISCAL_ADAPTER=None)
def test_store_offering_nfce_without_fiscal_adapter_warns(store_offering_nfce):
    messages = checks.check_fiscal_adapter(None)
    assert [m.id for m in messages] == ["SHOPMAN_W003"]
    from django.core.checks import Warning as CheckWarning

    assert isinstance(messages[0], CheckWarning)


@override_settings(
    SHOPMAN_FISCAL_ADAPTER="shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend"
)
def test_store_offering_nfce_with_adapter_is_clean(store_offering_nfce):
    assert checks.check_fiscal_adapter(None) == []


@override_settings(SHOPMAN_FISCAL_ADAPTER=None)
def test_store_not_offering_nfce_is_clean(db):
    _shop_with_pos_defaults({})

    assert checks.check_fiscal_adapter(None) == []


@override_settings(SHOPMAN_FISCAL_ADAPTER=None)
def test_channel_config_fiscal_enabled_is_not_the_predicate_anymore(db):
    # A chave antiga não é escrita por nada no sistema; se alguém a colocar na
    # mão, ela não ressuscita o check — o predicado é o da loja.
    from shopman.shop.models import Channel

    Channel.objects.create(ref="pdv", name="PDV", config={"fiscal": {"enabled": True}})

    assert checks.check_fiscal_adapter(None) == []
