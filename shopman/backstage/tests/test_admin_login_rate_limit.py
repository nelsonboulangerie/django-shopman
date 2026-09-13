from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from shopman.backstage.middleware_admin_login import AdminLoginRateLimitMiddleware

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def limits(settings):
    settings.SHOPMAN_ADMIN_LOGIN_ACCOUNT_IP_LIMIT = 2
    settings.SHOPMAN_ADMIN_LOGIN_IP_LIMIT = 4
    cache.clear()
    yield
    cache.clear()


def test_admin_password_throttles_before_authentication_and_ignores_forged_forwarded_ip(client):
    with patch("django.contrib.auth.forms.authenticate", return_value=None) as authenticate:
        for i in range(2):
            assert client.post("/admin/login/", {"username": "owner", "password": "wrong"},
                               HTTP_X_FORWARDED_FOR=f"192.0.2.{i}").status_code == 200
        response = client.post("/admin/login/", {"username": "owner", "password": "wrong"},
                               HTTP_X_FORWARDED_FOR="192.0.2.200")
    assert response.status_code == 429
    assert authenticate.call_count == 2
    assert response["Retry-After"] == "300"
    assert response["Cache-Control"] == "no-store"
    assert client.get("/admin/login/").status_code == 200


def test_spraying_usernames_still_hits_address_limit():
    middleware = AdminLoginRateLimitMiddleware(Mock())
    factory = RequestFactory()
    for i in range(4):
        assert middleware.process_view(factory.post("/admin/login/", {"username": str(i)}), None, (), {}) is None
    assert middleware.process_view(factory.post("/admin/login/", {"username": "another"}), None, (), {}).status_code == 429
    assert middleware.process_view(factory.post("/admin/login/", {"username": "another"}, REMOTE_ADDR="192.0.2.2"), None, (), {}) is None


def test_cache_failure_does_not_bypass_admin_guard():
    middleware = AdminLoginRateLimitMiddleware(Mock())
    with patch("shopman.backstage.middleware_admin_login.cache.add", side_effect=RuntimeError("cache offline")):
        response = middleware.process_view(RequestFactory().post("/admin/login/", {"username": "owner"}), None, (), {})
    assert response.status_code == 503


def test_bucket_expiration_allows_next_attempt():
    middleware = AdminLoginRateLimitMiddleware(Mock())
    request = RequestFactory().post("/admin/login/", {"username": "owner"})
    for _ in range(2):
        assert middleware.process_view(request, None, (), {}) is None
    assert middleware.process_view(request, None, (), {}).status_code == 429
    cache.clear()
    assert middleware.process_view(request, None, (), {}) is None
