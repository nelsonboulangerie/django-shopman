"""A sonda ``courier_webhooks``: a TaOn tem os avisos de status e de posição desta casa (F7b).

Só leitura (``list_webhooks``). A URL cadastrada leva o token: a evidência nunca a mostra.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse
from shopman.watchman.contracts import CheckContext, Status
from shopman.watchman.registry import build_registry

from shopman.shop.adapters import courier_mock
from shopman.shop.watchman_checks import CourierWebhooksCheck

pytestmark = pytest.mark.django_db

MOCK_ADAPTER = "shopman.shop.adapters.courier_mock"
TOKEN = "tok-segredo-123"


@pytest.fixture(autouse=True)
def _clean_state():
    courier_mock.reset()
    yield
    courier_mock.reset()


def _run():
    return CourierWebhooksCheck().run(CheckContext(profile="courier", deadline=time.monotonic() + 40))


def _ours() -> str:
    return f"https://api.exemplo.com.br{reverse('webhooks:machine-webhook')}?token={TOKEN}"


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_both_webhooks_pointing_here_pass_and_the_token_never_shows():
    courier_mock.register_webhook(_ours(), kind="status")
    courier_mock.register_webhook(_ours(), kind="posicao")
    courier_mock.register_webhook("https://outro.exemplo/x", kind="posicao")

    result = _run()

    assert result.status is Status.PASS
    assert dict(result.evidence) == {"registered": 3, "pointing_here": 2, "kinds": ["posicao", "status"]}
    assert TOKEN not in str(result.to_dict())


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_without_the_position_webhook_it_fails_and_says_which():
    courier_mock.register_webhook(_ours(), kind="status")
    courier_mock.register_webhook("https://outro.exemplo/x", kind="posicao")

    result = _run()

    assert result.status is Status.FAIL
    assert result.evidence["missing"] == ["posicao"]
    assert "machine_register_webhook" in result.remediation


@override_settings(SHOPMAN_COURIER_ADAPTER=MOCK_ADAPTER)
def test_a_listing_that_fails_is_unknown_not_pass():
    with patch.object(courier_mock, "list_webhooks", side_effect=RuntimeError("fora do ar")):
        result = _run()
    assert result.status is Status.UNKNOWN
    assert dict(result.evidence) == {"error": "RuntimeError"}


def test_without_a_delivery_service_it_is_skipped():
    with patch("shopman.shop.services.delivery_services.courier_backend", return_value=None):
        assert _run().status is Status.SKIPPED


def test_it_lives_in_its_own_profile_outside_readiness():
    registry = build_registry()
    assert [check.id for check in registry.for_profile("courier")] == ["courier_webhooks"]
    assert "courier_webhooks" not in [check.id for check in registry.for_profile("readiness")]
    assert "courier_webhooks" not in [check.id for check in registry.for_profile("diagnostic")]
