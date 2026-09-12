"""C01/H04: ACK local, envelope limitado e identidade estável."""

import json
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from shopman.storefront.concierge import service

pytestmark = pytest.mark.django_db
CONFIG = {
    "contract_version": 2,
    "enabled": True,
    "api_key": "test-only",
    "api_key_previous": "old-test-only",
    "account_id": "test-account",
    "transport_channel": "whatsapp",
    "allowed_subscribers": ["opaque:customer"],
}


@pytest.fixture(autouse=True)
def setup(settings):
    settings.SHOPMAN_CONCIERGE = CONFIG.copy()
    settings.AI_ASSIST_API_KEY = "fake"
    cache.clear()


def post(data, key="test-only", content_type="application/json"):
    return Client().post(
        reverse("concierge:manychat-conversation"), json.dumps(data), content_type=content_type, HTTP_X_API_KEY=key
    )


def event(**changes):
    return {"subscriber_id": "opaque:customer", "text": "Olá", "event_id": "event-1", **changes}


@pytest.mark.parametrize("key", ["test-only", "old-test-only"])
def test_rotation_and_no_network_in_ack(key, monkeypatch):
    from shopman.guestman.adapters.auth import CustomerResolver

    spy = Mock(side_effect=AssertionError("network in ACK"))
    monkeypatch.setattr(CustomerResolver, "manychat_last_input_text", spy)
    monkeypatch.setattr(service, "identify", spy)
    response = post(event(), key)
    assert response.status_code == 200
    assert response.json()["queued"]
    spy.assert_not_called()


@pytest.mark.parametrize(
    "data",
    [
        [],
        None,
        True,
        12,
        "text",
        event(subscriber_id=True),
        event(text=[]),
        event(event_id=[]),
        event(provider_timestamp={}),
    ],
)
def test_invalid_shape_never_persists(data):
    from shopman.shop.models import ConversationMessage

    assert post(data).status_code == 400
    assert not ConversationMessage.objects.exists()


@pytest.mark.parametrize(
    "key,value", [("account_id", "another"), ("transport_channel", "instagram"), ("provider", "other")]
)
def test_body_cannot_choose_account_or_channel(key, value):
    assert post(event(**{key: value})).status_code == 403


def test_no_secret_fails_closed_in_debug(settings):
    settings.DEBUG = True
    settings.SHOPMAN_CONCIERGE = {**CONFIG, "api_key": "", "api_key_previous": ""}
    assert post(event()).status_code == 503


def test_limits():
    assert post(event(text="a" * 16001)).status_code == 413
    assert post(event(), content_type="text/plain").status_code == 415
    nested = {}
    for _ in range(10):
        nested = {"x": nested}
    assert post(event(extra=nested)).status_code == 400


def test_long_event_identity_replay_conflict():
    from shopman.shop.models import ConversationMessage

    one = "a" * 200 + "1"
    two = "a" * 200 + "2"
    assert post(event(event_id=one)).json()["queued"]
    assert post(event(event_id=one)).json()["status"] == "duplicate"
    assert post(event(event_id=two)).json()["queued"]
    assert post(event(event_id=one, text="changed")).status_code == 409
    assert ConversationMessage.objects.count() == 2
    assert {m.envelope["event_id"] for m in ConversationMessage.objects.all()} == {one, two}


def test_missing_id_or_empty_allowlist_never_admits(settings):
    from shopman.shop.models import ConversationMessage

    assert not post(event(event_id="")).json()["queued"]
    settings.SHOPMAN_CONCIERGE = {**CONFIG, "allowed_subscribers": []}
    assert not post(event()).json()["queued"]
    assert not ConversationMessage.objects.exists()


def test_payload_conflict_includes_profile():
    assert post(event(first_name="Ana")).json()["queued"]
    assert post(event(first_name="Outra")).status_code == 409


def test_subject_rate_does_not_block_other_customer_on_provider_ip(settings, monkeypatch):
    settings.SHOPMAN_CONCIERGE = {**CONFIG, "allowed_subscribers": ["opaque:customer", "another"]}
    monkeypatch.setattr(service, "receive_inbound", lambda **kw: service.IntakeResult(None, None, True, "queued"))
    for i in range(60):
        assert post(event(event_id=str(i))).status_code == 200
    assert post(event(event_id="limited")).status_code == 429
    assert post(event(subscriber_id="another")).status_code == 200


def test_profile_change_conflict_is_auditable_without_new_work():
    from shopman.shop.models import ConversationMessage

    assert post(event(first_name="Ana")).status_code == 200
    assert post(event(first_name="Other")).status_code == 409
    assert ConversationMessage.objects.count() == 1
