from unittest.mock import Mock, patch

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from shopman.backstage.middleware_admin_login import AdminLoginRateLimitMiddleware

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def limits(settings):
    settings.SHOPMAN_ADMIN_LOGIN_IP_SOURCE = "direct"
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


@pytest.mark.parametrize("source", ["", "xff", "auto"])
def test_unknown_ip_source_refuses_before_authentication(client, settings, source):
    settings.SHOPMAN_ADMIN_LOGIN_IP_SOURCE = source
    with patch("django.contrib.auth.forms.authenticate") as authenticate:
        response = client.post("/admin/login/", {"username": "owner"})
    assert response.status_code == 503
    authenticate.assert_not_called()


@pytest.mark.parametrize("address", ["", "not-an-ip", "192.0.2.1, 192.0.2.2", "192.0.2.1:443", "fe80::1%eth0"])
def test_do_source_requires_one_valid_address(settings, address):
    settings.SHOPMAN_ADMIN_LOGIN_IP_SOURCE = "do"
    request = RequestFactory().post("/admin/login/", HTTP_DO_CONNECTING_IP=address,
                                    HTTP_X_FORWARDED_FOR="192.0.2.9", REMOTE_ADDR="192.0.2.8")
    response = AdminLoginRateLimitMiddleware(Mock()).process_view(request, None, (), {})
    assert response.status_code == 503


def test_direct_mode_ignores_all_claimed_forwarding_headers():
    middleware = AdminLoginRateLimitMiddleware(Mock())
    for attempt in range(3):
        request = RequestFactory().post("/admin/login/", {"username": "owner"},
            HTTP_DO_CONNECTING_IP=f"192.0.2.{attempt}", HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt}",
            HTTP_CF_CONNECTING_IP=f"203.0.113.{attempt}", HTTP_X_REAL_IP=f"192.0.2.{attempt}")
        response = middleware.process_view(request, None, (), {})
        assert (response.status_code if response is not None else None) == (429 if attempt == 2 else None)


def test_do_keeps_client_bucket_across_ingress_rotation_and_spoofed_prefixes(settings):
    settings.SHOPMAN_ADMIN_LOGIN_IP_SOURCE = "do"
    middleware = AdminLoginRateLimitMiddleware(Mock())
    for attempt in range(3):
        request = RequestFactory().post("/admin/login/", {"username": "owner"},
            HTTP_DO_CONNECTING_IP="192.0.2.10", REMOTE_ADDR=f"10.0.0.{attempt + 1}",
            HTTP_X_FORWARDED_FOR=f"198.51.100.{attempt}, 10.0.0.1", HTTP_CF_CONNECTING_IP=f"203.0.113.{attempt}")
        response = middleware.process_view(request, None, (), {})
        assert (response.status_code if response is not None else None) == (429 if attempt == 2 else None)
    other = RequestFactory().post("/admin/login/", {"username": "owner"},
        HTTP_DO_CONNECTING_IP="192.0.2.11", REMOTE_ADDR="10.0.0.1")
    assert middleware.process_view(other, None, (), {}) is None


def test_equivalent_ipv6_and_ipv4_mapped_addresses_share_buckets(settings):
    from shopman.backstage.services.admin_login_ip import canonical_ip
    assert canonical_ip("2001:db8::1") == canonical_ip("2001:0db8:0000:0000:0000:0000:0000:0001")
    assert canonical_ip("::ffff:192.0.2.1") == canonical_ip("192.0.2.1")


def test_deploy_check_requires_explicit_supported_source(settings):
    from shopman.backstage.services.admin_login_ip import check_admin_login_ip_source
    for source in ["", "xff", "auto"]:
        settings.SHOPMAN_ADMIN_LOGIN_IP_SOURCE = source
        assert [error.id for error in check_admin_login_ip_source(None)] == ["backstage.E001"]
    for source in ["direct", "do"]:
        settings.SHOPMAN_ADMIN_LOGIN_IP_SOURCE = source
        assert check_admin_login_ip_source(None) == []
