"""Erro de provedor de IA vai ao Sentry uma vez por dia por causa (SHOPMAN-1C)."""

from __future__ import annotations

from django.core.cache import cache

from shopman.shop.telemetry_throttle import drop_repeated_provider_error


def _event(exc_type: str, value: str, *, mechanism: str = "anthropic") -> dict:
    return {"exception": {"values": [{"type": exc_type, "value": value, "mechanism": {"type": mechanism}}]}}


def test_the_same_provider_failure_goes_once_and_another_cause_goes_too():
    cache.clear()
    unauthorized = _event("AuthenticationError", "Error code: 401 - invalid x-api-key")
    assert drop_repeated_provider_error(unauthorized) is unauthorized
    for _ in range(5):
        assert drop_repeated_provider_error(_event("AuthenticationError", "Error code: 401 - invalid x-api-key")) is None
    overloaded = _event("APIStatusError", "Error code: 529 - overloaded")
    assert drop_repeated_provider_error(overloaded) is overloaded


def test_errors_of_the_system_itself_are_never_dropped():
    cache.clear()
    own = _event("ValueError", "boom", mechanism="django")
    for _ in range(3):
        assert drop_repeated_provider_error(own) is own
    message_only = {"message": "maintenance_worker: x"}
    assert drop_repeated_provider_error(message_only) is message_only
