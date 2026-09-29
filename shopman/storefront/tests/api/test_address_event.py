from __future__ import annotations

import pytest

from shopman.storefront.api.telemetry import sanitize_address_event

pytestmark = pytest.mark.django_db


def test_address_event_keeps_only_closed_aggregate_properties():
    event = sanitize_address_event(
        {
            "event": "address.map.confirmed",
            "properties": {
                "origin": "gps",
                "accuracy_bucket": "medium",
                "moved": True,
                "latitude": -23.31,
                "postal_code": "86000-000",
                "query": "Rua pessoal, 123",
            },
        }
    )
    assert event == {
        "event": "address.map.confirmed",
        "properties": {"origin": "gps", "accuracy_bucket": "medium", "moved": "true"},
    }
    assert "Rua pessoal" not in repr(event)
    assert "-23.31" not in repr(event)


@pytest.mark.parametrize(
    "payload",
    [
        {"event": "address.map.confirmed", "properties": "gps"},
        {"event": "address.customer.address", "properties": {}},
        {"event": "address.map.ready", "properties": {"origin": "home"}},
    ],
)
def test_address_event_rejects_unknown_shapes_or_values(payload):
    sanitized = sanitize_address_event(payload)
    assert sanitized == {}


def test_address_event_endpoint_is_write_only_and_drops_pii(client, caplog):
    response = client.post(
        "/api/v1/storefront/address-event/",
        data={
            "event": "address.location.resolved",
            "properties": {
                "accuracy_bucket": "good",
                "latency_bucket": "fast",
                "address": "Rua pessoal, 123",
            },
        },
        content_type="application/json",
    )
    assert response.status_code == 202
    assert "Rua pessoal" not in caplog.text


def test_location_mismatch_event_keeps_only_policy_enums():
    event = sanitize_address_event(
        {
            "event": "address.location_check.resolved",
            "properties": {
                "target": "saved",
                "status": "diverged",
                "accuracy_bucket": "good",
                "policy_version": "v1",
                "distance_m": 930,
                "saved_address_id": 42,
                "latitude": -23.31,
            },
        }
    )

    assert event == {
        "event": "address.location_check.resolved",
        "properties": {
            "target": "saved",
            "status": "diverged",
            "accuracy_bucket": "good",
            "policy_version": "v1",
        },
    }
    assert "930" not in repr(event)
    assert "42" not in repr(event)
    assert "-23.31" not in repr(event)
