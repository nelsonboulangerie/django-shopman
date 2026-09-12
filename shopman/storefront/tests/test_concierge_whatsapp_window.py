"""Última interação WA abre somente resposta de leitura, sem autoridade comercial."""
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from shopman.orderman.models import Order, Session

from shopman.shop.models import Conversation
from shopman.storefront.concierge import service, tools, transport
from shopman.storefront.tests import test_concierge_legacy_gateway as legacy

gateway = legacy.gateway
catalog = legacy.catalog

pytestmark = pytest.mark.django_db
NOW = datetime(2026, 9, 12, 15, tzinfo=UTC)


@pytest.fixture(autouse=True)
def window(settings, monkeypatch, gateway):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "whatsapp_interaction_timezone": "America/Sao_Paulo"}
    monkeypatch.setattr(service.timezone, "now", lambda: NOW)


def post(client, at, **extra):
    body = {"subscriber_id": "123", "text": "#c cardápio", "provider_timestamp": at, **extra}
    return client.post(reverse("concierge:manychat-conversation"), json.dumps(body), content_type="application/json", HTTP_X_API_KEY="existing-test-key")


def local(at):
    return at.astimezone(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None).isoformat(sep=" ")


def test_live_field_opens_read_reply_without_identity_or_purchase(client, catalog, gateway):
    assert post(client, "2026-09-12 11:29:01.391392").json() == {"status": "legacy_read_only", "queued": True}
    conversation = Conversation.objects.get()
    receipt = conversation.messages.get()
    assert receipt.envelope["window_evidence"]["at"] == "2026-09-12T14:29:01.391392+00:00"
    assert receipt.envelope["input_assurance"] == "legacy_unverified"
    assert receipt.external_id == receipt.envelope["event_id"] == ""
    assert conversation.last_inbound_at is None
    assert transport.response_allowed(conversation, NOW)
    service.run_turn(conversation.pk)
    assert gateway and "Pão Francês" in "\n".join(gateway)
    reloaded = Conversation.objects.get(pk=conversation.pk)
    assert not tools.set_item(tools.ToolContext(reloaded, "web"), "PAO-FRANCES", 2)["ok"]
    assert not Session.objects.exists() and not Order.objects.exists()


@pytest.mark.parametrize("value", ["", "not a date", "2026-09-12", "2026-02-31 11:29:01", "2026-09-11 11:29:01.391392", "2026-09-12 12:00:00.000001", "2026-09-11 12:00:00"])
def test_invalid_future_or_expired_field_cannot_open_window(client, gateway, value):
    assert post(client, value).json()["queued"]
    conversation = Conversation.objects.get()
    assert "window_evidence" not in conversation.messages.get().envelope
    assert not transport.response_allowed(conversation, NOW)
    service.run_turn(conversation.pk)
    assert not gateway


def test_queue_expiry_and_replay_do_not_renew_window(client, gateway, monkeypatch):
    original = NOW - timedelta(hours=23, minutes=59)
    post(client, local(original))
    conversation = Conversation.objects.get()
    assert transport.response_allowed(conversation, NOW)
    later = NOW + timedelta(minutes=1)
    monkeypatch.setattr(service.timezone, "now", lambda: later)
    post(client, local(original))
    assert not transport.response_allowed(conversation, later)
    service.run_turn(conversation.pk)
    assert not gateway
    assert conversation.messages.filter(kind="inbound").count() == 2


def test_out_of_order_does_not_shorten_existing_window(client):
    post(client, local(NOW - timedelta(minutes=10)))
    post(client, local(NOW - timedelta(hours=23)))
    assert transport.response_allowed(Conversation.objects.get(), NOW + timedelta(hours=2))


def test_revocation_after_prepare_contains_send(client, settings, gateway):
    post(client, local(NOW))
    conversation, _ = service._claim(Conversation.objects.get().pk)
    prepared = service._prepare_reply(conversation, "Cardápio")
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "whatsapp_interaction_timezone": ""}
    service._dispatch_reply(conversation, prepared)
    prepared.refresh_from_db()
    assert prepared.transport_state == "not_applied" and prepared.envelope["code"] == "window_closed"
    assert not gateway


@pytest.mark.parametrize("zone", ["", "Invalid/Zone"])
def test_no_implicit_timezone_or_historical_backfill(client, settings, zone):
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "whatsapp_interaction_timezone": zone}
    post(client, local(NOW))
    conversation = Conversation.objects.get()
    assert not transport.response_allowed(conversation, NOW)
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "whatsapp_interaction_timezone": "America/Sao_Paulo"}
    assert not transport.response_allowed(conversation, NOW)


@pytest.mark.parametrize("changed", [{"authentication": ""}, {"account_id": "other"}, {"provider": "other"}, {"transport_channel": "instagram"}])
def test_field_requires_authenticated_account_and_whatsapp(changed):
    envelope = {"authentication": "api_key", "account_id": "legacy-test-account", "provider": "manychat", "transport_channel": "whatsapp", "provider_timestamp": local(NOW), **changed}
    assert transport.whatsapp_interaction_at(envelope, NOW) is None


@pytest.mark.parametrize("stamp", ["2026-09-12T15:00:00Z", "2026-09-12T12:00:00-03:00"])
def test_explicit_offset_is_not_applied_twice(client, stamp):
    post(client, stamp)
    assert transport.response_allowed(Conversation.objects.get(), NOW)


def test_legacy_gate_revocation_revokes_window_source(client, settings):
    post(client, local(NOW))
    conversation = Conversation.objects.get()
    assert transport.response_allowed(conversation, NOW)
    settings.SHOPMAN_CONCIERGE = {**settings.SHOPMAN_CONCIERGE, "legacy_read_handoff_enabled": False}
    assert not transport.response_allowed(conversation, NOW)
