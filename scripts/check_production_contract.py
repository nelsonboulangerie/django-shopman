#!/usr/bin/env python3
"""Hermetic production-configuration contract for pull requests.

This validates production shape with synthetic credentials.  It deliberately
blocks every outbound socket before Django's deploy checks run; live readiness
belongs to the cutover runbook, never to ordinary CI.
"""

from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from urllib.parse import urlparse

FALSE_VALUES = {"", "0", "false", "no", "off"}
FORBIDDEN_FLAGS = (
    "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS",
    "SHOPMAN_EXPOSE_MOCK_CAPTURE",
    "SHOPMAN_MOCK_PIX_AUTO_CONFIRM",
    "SHOPMAN_EXPOSE_DEBUG_OTP",
    "SHOPMAN_STAGING_AUTOPILOT",
    "SHOPMAN_ENABLE_CONSOLE_NOTIFICATION_ADAPTER",
    "SHOPMAN_ALLOW_INSECURE_TEST_UPSTREAM",
)
PRODUCTION_ADAPTERS = {
    "SHOPMAN_PIX_ADAPTER": "shopman.shop.adapters.payment_efi",
    "SHOPMAN_CARD_ADAPTER": "shopman.shop.adapters.payment_stripe",
    "SHOPMAN_LINK_ADAPTER": "shopman.shop.adapters.payment_stripe",
    "SHOPMAN_FISCAL_ADAPTER": "shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend",
}


class ContractError(RuntimeError):
    pass


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() not in FALSE_VALUES


def validate_environment(environ: dict[str, str] | os._Environ[str] = os.environ) -> None:
    failures: list[str] = []
    if environ.get("SHOPMAN_ENVIRONMENT", "").strip().lower() != "production":
        failures.append("SHOPMAN_ENVIRONMENT=production")
    if _truthy(environ.get("DJANGO_DEBUG")):
        failures.append("DJANGO_DEBUG=false")
    if not _truthy(environ.get("DJANGO_SECURE_SSL_REDIRECT")):
        failures.append("DJANGO_SECURE_SSL_REDIRECT=true")

    hosts = [item.strip() for item in environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if item.strip()]
    if not hosts or "*" in hosts:
        failures.append("DJANGO_ALLOWED_HOSTS must be explicit")
    origins = [item.strip() for item in environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if item.strip()]
    if not origins or any(not item.startswith("https://") for item in origins):
        failures.append("CSRF_TRUSTED_ORIGINS must contain only https origins")

    for key, schemes in (("DATABASE_URL", {"postgres", "postgresql"}), ("REDIS_URL", {"redis", "rediss"})):
        parsed = urlparse(environ.get(key, ""))
        if parsed.scheme not in schemes or not parsed.hostname:
            failures.append(f"{key} must be a structured production URL")

    for key in FORBIDDEN_FLAGS:
        if _truthy(environ.get(key)):
            failures.append(f"{key}=false")
    for key, expected in PRODUCTION_ADAPTERS.items():
        if environ.get(key, "").strip() != expected:
            failures.append(f"{key}={expected}")

    if failures:
        raise ContractError("invalid production contract: " + "; ".join(failures))


@contextmanager
def block_external_network():
    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def blocked(*_args, **_kwargs):
        raise ContractError("production contract attempted an external network connection")

    socket.socket.connect = blocked
    socket.create_connection = blocked
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create_connection


def main() -> int:
    validate_environment()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django
    from django.core.management import call_command

    with block_external_network():
        django.setup()
        call_command("check", deploy=True, fail_level="ERROR")
    print("production-contract: passed (synthetic configuration, outbound network blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
