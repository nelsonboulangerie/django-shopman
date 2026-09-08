"""MKT-003 — the legacy cut creates evidence without inventing consent proof."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

GUESTMAN_LEAF = ("guestman", "0004_alter_customer_ref")
BEFORE = [("customer_consent", "0001_initial"), GUESTMAN_LEAF]
AFTER = [("customer_consent", "0002_consent_evidence_events"), GUESTMAN_LEAF]


def _apps_at(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets).apps


def test_legacy_optin_is_imported_as_unverified_history() -> None:
    old_apps = _apps_at(BEFORE)
    Customer = old_apps.get_model("guestman", "Customer")
    Consent = old_apps.get_model("customer_consent", "CommunicationConsent")
    customer = Customer.objects.create(
        ref="CLI-MIGRATION",
        first_name="Legado",
        phone="+5543999001099",
    )
    old = Consent.objects.create(
        customer=customer,
        channel="whatsapp",
        status="opted_in",
        legal_basis="consent",
        source="legacy-form",
    )

    new_apps = _apps_at(AFTER)
    NewConsent = new_apps.get_model("customer_consent", "CommunicationConsent")
    Event = new_apps.get_model("customer_consent", "CommunicationConsentEvent")
    current = NewConsent.objects.get(pk=old.pk)
    event = Event.objects.get(customer_id=customer.pk)

    assert current.proof_status == "legacy_unverified"
    assert current.policy_version == ""
    assert current.disclosure_hash == ""
    assert current.last_event_ref == event.ref
    assert event.event_type == "legacy_import"
    assert event.disclosure_text == ""
    assert event.disclosure_version == ""
    assert event.resulting_status == "opted_in"
    assert len(event.evidence_hash) == 64
