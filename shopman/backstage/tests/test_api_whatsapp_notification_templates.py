from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.utils import timezone

from shopman.shop.models import (
    MarketingPlatformAuditEvent,
    NotificationTemplate,
)
from shopman.shop.services import manychat_flows
from shopman.shop.services.marketing_platform_configuration import (
    TRANSACTIONAL_WHATSAPP_EVENTS,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/backstage/marketing/whatsapp-template/"
FLOW = "content20260926170000_000001"


@pytest.fixture
def gestor():
    user = get_user_model().objects.create_user(
        username="whatsapp-platform-owner",
        password="x",
        is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(codename="view_marketing"),
        Permission.objects.get(codename="configure_marketing_platforms"),
    )
    return user


@pytest.fixture
def live_catalog(monkeypatch):
    now = timezone.now()
    catalog = manychat_flows.FlowCatalog(
        flows=((FLOW, "Pedido com nova data"),),
        state="fresh",
        checked_at=now,
        facts_as_of=now,
        fresh_until=now + timedelta(minutes=5),
        catalog_hash="a" * 64,
    )
    monkeypatch.setattr(manychat_flows, "flow_catalog", lambda **kwargs: catalog)


@pytest.fixture
def confirmed_commands(monkeypatch):
    monkeypatch.setattr(
        "shopman.backstage.api.marketing._command_authorizer",
        lambda *args, **kwargs: (lambda context, receipt: None),
    )


def _template(event: str) -> NotificationTemplate:
    template, _created = NotificationTemplate.objects.get_or_create(
        event=event,
        defaults={"subject": event, "body": event},
    )
    return template


def test_get_lists_only_supported_transactional_events(
    client, gestor, live_catalog
):
    client.force_login(gestor)

    body = client.get(URL).json()
    events = {row["event"] for row in body["notification_templates"]}

    assert events == set(TRANSACTIONAL_WHATSAPP_EVENTS)
    assert "order_rescheduled" in events
    assert "access_link" not in events
    assert "announcement_published" not in events


def test_confirmed_write_is_scoped_and_audited_by_event(
    client, gestor, live_catalog, confirmed_commands
):
    target = _template("order_rescheduled")
    other = _template("order_accepted")
    client.force_login(gestor)

    response = client.post(
        URL,
        data={
            "event": "order_rescheduled",
            "flow_ns": FLOW,
            "base_version": target.version,
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="configure-rescheduled-flow-0001",
    )

    assert response.status_code == 200
    receipt = response.json()["receipt"]
    assert receipt["resource_ref"] == "platform:whatsapp:order_rescheduled"
    target.refresh_from_db()
    other.refresh_from_db()
    assert target.whatsapp_flow_ns == FLOW
    assert target.version == 2
    assert other.whatsapp_flow_ns == ""
    audit = MarketingPlatformAuditEvent.objects.get()
    assert audit.command.resource_ref.endswith(":order_rescheduled")


def test_event_is_part_of_idempotent_intent(
    client, gestor, live_catalog, confirmed_commands
):
    first = _template("order_rescheduled")
    second = _template("order_accepted")
    client.force_login(gestor)
    key = "configure-event-scoped-flow-0001"

    accepted = client.post(
        URL,
        data={
            "event": first.event,
            "flow_ns": FLOW,
            "base_version": first.version,
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    collision = client.post(
        URL,
        data={
            "event": second.event,
            "flow_ns": FLOW,
            "base_version": second.version,
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
    )

    assert accepted.status_code == 200
    assert collision.status_code == 409
    assert collision.json()["code"] == "idempotency_conflict"
    second.refresh_from_db()
    assert second.whatsapp_flow_ns == ""


def test_unknown_event_is_rejected_without_creating_a_row(
    client, gestor, live_catalog, confirmed_commands
):
    client.force_login(gestor)

    response = client.post(
        URL,
        data={
            "event": "made_up_event",
            "flow_ns": FLOW,
            "base_version": 1,
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="configure-unknown-flow-0001",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "unsupported_notification_event"
    assert not NotificationTemplate.objects.filter(event="made_up_event").exists()


def test_missing_transactional_row_fails_loudly(
    client, gestor, live_catalog
):
    NotificationTemplate.objects.filter(event="order_rescheduled").delete()
    client.force_login(gestor)

    response = client.post(
        URL,
        data={
            "event": "order_rescheduled",
            "flow_ns": FLOW,
            "base_version": 1,
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="configure-missing-template-0001",
    )

    assert response.status_code == 422
    assert response.json()["code"] == "notification_template_missing"
    assert not NotificationTemplate.objects.filter(event="order_rescheduled").exists()
