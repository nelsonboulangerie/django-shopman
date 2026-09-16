"""H07: sync não perde retry e string false não concede consentimento."""

import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.test import RequestFactory
from shopman.guestman.contrib.manychat.service import ManychatService
from shopman.guestman.contrib.manychat.views import ManychatWebhookView
from shopman.guestman.models import ProcessedEvent

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def config(settings):
    settings.MANYCHAT_WEBHOOK_SECRET = "local-test-only"


def call(data):
    body = json.dumps(data).encode()
    signature = hmac.new(b"local-test-only", body, hashlib.sha256).hexdigest()
    request = RequestFactory().post(
        "/sync/", body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256="sha256=" + signature
    )
    return ManychatWebhookView.as_view()(request)


@pytest.mark.parametrize("data", [[], True, None, {"subscriber": []}])
def test_shape_guard(data):
    assert call(data).status_code == 400


def test_sync_failure_then_retry_reapplies(monkeypatch):
    sync = Mock(side_effect=[RuntimeError("injected"), (SimpleNamespace(ref="customer"), True)])
    monkeypatch.setattr(ManychatService, "sync_subscriber", sync)
    payload = {"event_id": "new-event", "subscriber": {"id": "subscriber"}}
    assert call(payload).status_code == 500
    assert not ProcessedEvent.objects.exists()
    assert call(payload).status_code == 200
    assert ProcessedEvent.objects.count() == 1
    assert call(payload).status_code == 200
    assert sync.call_count == 2


def test_subscriber_id_never_dedupes_later_state(monkeypatch):
    sync = Mock(return_value=(SimpleNamespace(ref="customer"), False))
    monkeypatch.setattr(ManychatService, "sync_subscriber", sync)
    assert call({"id": "same", "optin_whatsapp": True}).status_code == 200
    assert call({"id": "same", "optin_whatsapp": False}).status_code == 200
    assert sync.call_count == 2
    assert not ProcessedEvent.objects.exists()


@pytest.mark.parametrize(
    "value,expected",
    [("false", False), ("true", True), (False, False), (True, True), ("no", None), (1, None), ([], None)],
)
def test_consent_boolean_has_explicit_meaning(monkeypatch, value, expected):
    from shopman.guestman.contrib.consent.service import ConsentService

    grant = Mock()
    revoke = Mock()
    monkeypatch.setattr(ConsentService, "grant_consent", grant)
    monkeypatch.setattr(ConsentService, "revoke_consent", revoke)
    result = ManychatService.sync_consent(SimpleNamespace(ref="customer"), {"optin_whatsapp": value})
    assert result == ({} if expected is None else {"whatsapp": expected})
    assert grant.call_count == (1 if expected is True else 0)
    assert revoke.call_count == (1 if expected is False else 0)
