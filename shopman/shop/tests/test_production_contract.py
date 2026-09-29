import socket

import pytest

from scripts.check_production_contract import (
    FORBIDDEN_FLAGS,
    PRODUCTION_ADAPTERS,
    ContractError,
    block_external_network,
    validate_environment,
)


def valid_environment() -> dict[str, str]:
    return {
        "SHOPMAN_ENVIRONMENT": "production",
        "DJANGO_DEBUG": "false",
        "DJANGO_SECURE_SSL_REDIRECT": "true",
        "DJANGO_ALLOWED_HOSTS": "shop.example.com",
        "CSRF_TRUSTED_ORIGINS": "https://shop.example.com",
        "DATABASE_URL": "postgresql://user:pass@db.invalid/shopman",
        "REDIS_URL": "rediss://cache.invalid/0",
        **dict.fromkeys(FORBIDDEN_FLAGS, "false"),
        **PRODUCTION_ADAPTERS,
    }


def test_valid_production_contract_shape_passes():
    validate_environment(valid_environment())


@pytest.mark.parametrize("flag", FORBIDDEN_FLAGS)
def test_every_test_affordance_breaks_the_contract(flag):
    environ = valid_environment()
    environ[flag] = "true"
    with pytest.raises(ContractError, match=flag):
        validate_environment(environ)


@pytest.mark.parametrize("key", PRODUCTION_ADAPTERS)
def test_every_mock_or_missing_adapter_breaks_the_contract(key):
    environ = valid_environment()
    environ[key] = "shopman.shop.adapters.payment_mock"
    with pytest.raises(ContractError, match=key):
        validate_environment(environ)


def test_contract_blocks_outbound_network():
    with block_external_network(), pytest.raises(ContractError, match="external network"):
        socket.create_connection(("example.com", 443))
