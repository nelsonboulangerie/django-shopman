"""O estado, no Google, da retirada e da disponibilidade na loja (WP-G14b, issue #2652).

Tudo offline: respostas gravadas no formato de ``omnichannelSettings`` da
Merchant API (referência de 17/11/2026). Nenhuma chamada ao Google, nenhuma
conta real.
"""

from __future__ import annotations

import base64
import json
from datetime import timedelta
from unittest import mock

import pytest
from django.core.cache import cache
from django.utils import timezone

from shopman.shop.adapters import catalog_projection_google as google
from shopman.shop.services import google_store_review as review

pytestmark = pytest.mark.django_db

_SETTINGS = {
    "service_account_b64": base64.b64encode(json.dumps({
        "client_email": "shopman@projeto.iam.gserviceaccount.com",
        "private_key": "chave-de-teste",
        "token_uri": "https://oauth2.mock.test/token",
    }).encode()).decode(),
    "api_base": "https://merchant.mock.test",
    "timeout": 5,
}

#: Resposta gravada: a configuração do Brasil, com a retirada negada e a
#: disponibilidade na loja em análise.
_RECORDED = {
    "omnichannelSettings": [
        {
            "name": "accounts/5881119366/omnichannelSettings/BR",
            "regionCode": "BR",
            "lsfType": "GHLSF",
            "inStock": {"state": "RUNNING"},
            "pickup": {"uri": "https://www.loja.test/produto/TRADI", "state": "FAILED"},
        }
    ]
}


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}
        self.content = json.dumps(self._body).encode()
        self.text = self.content.decode()
        self.headers = {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def conta(settings):
    from shopman.shop.models import Shop

    settings.SHOPMAN_GOOGLE_MERCHANT = _SETTINGS
    Shop.objects.create(
        name="Nelson",
        defaults={"google_merchant": {"account_id": "5881119366", "data_source_id": "999"}},
    )
    google._token_cache.clear()
    cache.delete(review.CACHE_KEY)
    with mock.patch.object(google.jwt, "encode", return_value="assinado"), mock.patch.object(
        google.requests, "post", return_value=_Resp(200, {"access_token": "tok", "expires_in": 3600})
    ):
        yield
    google._token_cache.clear()
    cache.delete(review.CACHE_KEY)


def test_reads_both_states_of_the_brazil_setting(conta):
    with mock.patch("requests.get", return_value=_Resp(200, _RECORDED)) as get:
        result = review.refresh()
    assert get.call_args.args[0] == "https://merchant.mock.test/accounts/v1/accounts/5881119366/omnichannelSettings"
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer tok"}
    assert (result.ok, result.pickup, result.in_stock) == (True, review.FAILED, review.RUNNING)
    assert review.last_review() == result


def test_account_without_setting_for_the_country_has_nothing_requested(conta):
    with mock.patch("requests.get", return_value=_Resp(200, {})):
        result = review.refresh()
    assert (result.ok, result.pickup, result.in_stock) == (True, review.NOT_REQUESTED, review.NOT_REQUESTED)


def test_refused_reading_is_kept_as_a_failure_never_as_approval(conta):
    refused = _Resp(403, {"error": {"message": "The caller does not have permission", "status": "PERMISSION_DENIED"}})
    with mock.patch("requests.get", return_value=refused):
        result = review.refresh()
    assert result.ok is False
    assert result.pickup == "" and result.in_stock == ""
    assert "PERMISSION_DENIED" in result.error
    assert review.last_review().ok is False


def test_refresh_if_due_reads_at_most_once_per_hour(conta):
    now = timezone.now()
    with mock.patch("requests.get", return_value=_Resp(200, _RECORDED)) as get:
        review.refresh_if_due(now=now)
        review.refresh_if_due(now=now + timedelta(minutes=59))
        assert get.call_count == 1
        review.refresh_if_due(now=now + review.READ_EVERY)
        assert get.call_count == 2


def test_without_account_nothing_is_asked(settings):
    settings.SHOPMAN_GOOGLE_MERCHANT = {}
    cache.delete(review.CACHE_KEY)
    with mock.patch("requests.get") as get:
        assert review.refresh_if_due() is None
    get.assert_not_called()
    assert review.last_review() is None
