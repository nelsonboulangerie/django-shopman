"""The temporary probe is inert unless every staging guard is satisfied."""
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.test import RequestFactory

from shopman.backstage.services.admin_ip_probe import AdminIngressProbeMiddleware, observe_admin_ip_probe

TOKEN = "synthetic-staging-probe-secret-123456789"
MARKER = "0123456789abcdef"


@pytest.fixture
def probe(settings, monkeypatch):
    settings.SHOPMAN_ENVIRONMENT = "staging"
    settings.ALLOWED_HOSTS = ["testserver", "admin.boulangerie.com.br"]
    settings.SHOPMAN_ADMIN_IP_PROBE_HOSTS = ["testserver"]
    settings.SHOPMAN_ADMIN_IP_PROBE_TOKEN = TOKEN
    settings.SHOPMAN_ADMIN_IP_PROBE_UNTIL = 1500
    monkeypatch.setattr("shopman.backstage.services.admin_ip_probe.time.time", lambda: 1000)
    logger = Mock()
    monkeypatch.setattr("shopman.backstage.services.admin_ip_probe.logger", logger)
    return logger


def request():
    return RequestFactory().get("/admin/login/",
        HTTP_X_SHOPMAN_ADMIN_IP_PROBE=TOKEN, HTTP_X_SHOPMAN_ADMIN_IP_PROBE_ID=MARKER,
        REMOTE_ADDR="10.0.0.1", HTTP_DO_CONNECTING_IP="192.0.2.1",
        HTTP_X_FORWARDED_FOR="198.51.100.1, 10.0.0.1",
        HTTP_CF_CONNECTING_IP="203.0.113.1", HTTP_X_REAL_IP="203.0.113.2")


def test_observation_is_hmac_only_and_does_not_change_get_response(probe):
    req = request()
    assert AdminIngressProbeMiddleware(Mock()).process_view(req, None, (), {}) is None
    probe.info.assert_called_once()
    payload = probe.info.call_args.args[1]
    record = json.loads(payload)
    assert record["marker"] == MARKER
    assert record["do"] == hmac.new(TOKEN.encode(), b"admin-ip-probe:192.0.2.1", hashlib.sha256).hexdigest()
    assert record["remote"] == record["xff"][1]
    assert record["do"] != record["remote"]
    for raw in [TOKEN, "192.0.2.1", "198.51.100.1", "203.0.113.1", "10.0.0.1"]:
        assert raw not in payload


@pytest.mark.parametrize("environment", ["production", "local", "test", "", "unknown"])
def test_never_observes_outside_exact_staging(probe, settings, environment):
    settings.SHOPMAN_ENVIRONMENT = environment
    observe_admin_ip_probe(request())
    probe.info.assert_not_called()


@pytest.mark.parametrize("until", [0, 999, 1000, 1901, "bad", None])
def test_expiry_and_invalid_window_disable_probe(probe, settings, until):
    settings.SHOPMAN_ADMIN_IP_PROBE_UNTIL = until
    observe_admin_ip_probe(request())
    probe.info.assert_not_called()


@pytest.mark.parametrize("change", ["token", "marker", "method", "path", "authenticated"])
def test_requires_secret_marker_anonymous_get_and_exact_login_path(probe, change):
    req = request()
    if change == "token":
        req.META["HTTP_X_SHOPMAN_ADMIN_IP_PROBE"] = "wrong"
    if change == "marker":
        req.META["HTTP_X_SHOPMAN_ADMIN_IP_PROBE_ID"] = "untrusted\nlog"
    if change == "method":
        req.method = "POST"
    if change == "path":
        req.path = "/admin/"
    if change == "authenticated":
        req.user = SimpleNamespace(is_authenticated=True)
    observe_admin_ip_probe(req)
    probe.info.assert_not_called()


def test_bad_addresses_are_classified_not_logged_and_chain_is_bounded(probe):
    req = request()
    req.META["HTTP_DO_CONNECTING_IP"] = "private-header-content"
    req.META["HTTP_X_FORWARDED_FOR"] = ",".join(["192.0.2.1"] * 20)
    observe_admin_ip_probe(req)
    payload = probe.info.call_args.args[1]
    record = json.loads(payload)
    assert record["do"] == "absent_or_invalid"
    assert len(record["xff"]) == 8
    assert record["xff_truncated"] is True
    assert "private-header-content" not in payload


@pytest.mark.parametrize("hosts", [[], ["another-staging.example"]])
def test_host_must_be_explicitly_allowed(probe, settings, hosts):
    settings.SHOPMAN_ADMIN_IP_PROBE_HOSTS = hosts
    observe_admin_ip_probe(request())
    probe.info.assert_not_called()


def test_production_host_is_not_enabled_by_staging_environment_label(probe):
    req = request()
    req.META["HTTP_HOST"] = "admin.boulangerie.com.br"
    observe_admin_ip_probe(req)
    probe.info.assert_not_called()


@pytest.mark.parametrize("app_id, host", [
    ("40b86e35-bafe-4a1a-a1b0-e124d3d9fd0f", "isolated.example"),
    ("11111111-1111-4111-8111-111111111111", "admin.boulangerie.com.br"),
    ("11111111-1111-4111-8111-111111111111", "shopman-staging-cdjpy.ondigitalocean.app"),
])
def test_sender_refuses_online_app_and_hosts_without_network(app_id, host):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([sys.executable, str(root / "scripts/probe_admin_ingress.py"),
        "--app-id", app_id, "--url", f"https://{host}/admin/login/", "--staging-host", host],
        capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "forbidden" in result.stderr.lower()
