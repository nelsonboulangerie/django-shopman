"""R11: o IP bruto da prova de consentimento vive no máximo 90 dias.

Porta do #614, com a mudança que o 15/09 exigiu: simulação por padrão e nada
agendado. O que se prova aqui é que a redação apaga só o IP, só o vencido, e
nunca além do teto de 90 dias — e que sem ``apply`` nada muda.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.forms.models import model_to_dict
from django.test import override_settings
from django.utils import timezone
from shopman.guestman.contrib.consent.models import (
    CommunicationConsent,
    CommunicationConsentEvent,
)
from shopman.guestman.contrib.consent.service import ConsentService
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db

OLD_IP = "192.0.2.10"
RECENT_IP = "192.0.2.11"


@pytest.fixture
def customer(db):
    return Customer.objects.create(ref="R11-001", first_name="Ana", phone="5541999990011")


@pytest.fixture
def old_and_recent(customer):
    """Um opt-in de 91 dias (vencido) e outro de 89 (dentro do prazo)."""

    old = timezone.now() - timedelta(days=91)
    recent = timezone.now() - timedelta(days=89)
    ConsentService.grant_consent(customer.ref, "email", ip_address=OLD_IP, occurred_at=old)
    ConsentService.grant_consent(customer.ref, "whatsapp", ip_address=RECENT_IP, occurred_at=recent)
    CommunicationConsent.objects.filter(channel="email").update(updated_at=old)
    CommunicationConsent.objects.filter(channel="whatsapp").update(updated_at=recent)
    return old, recent


def _snapshot():
    """Tudo das duas tabelas, para comparar antes/depois campo a campo."""

    current = [
        model_to_dict(row) | {"updated_at": row.updated_at, "created_at": row.created_at}
        for row in CommunicationConsent.objects.order_by("pk")
    ]
    events = [
        model_to_dict(row) | {"ref": row.ref, "occurred_at": row.occurred_at, "created_at": row.created_at}
        for row in CommunicationConsentEvent.objects.order_by("pk")
    ]
    return current, events


def test_expired_consent_ip_is_redacted_but_evidence_is_preserved(old_and_recent):
    counts = ConsentService.redact_expired_ip(days=999, apply=True)

    assert counts == {"current": 1, "events": 1}
    assert CommunicationConsent.objects.get(channel="email").ip_address is None
    assert CommunicationConsent.objects.get(channel="whatsapp").ip_address == RECENT_IP
    old_event = CommunicationConsentEvent.objects.get(channel="email")
    recent_event = CommunicationConsentEvent.objects.get(channel="whatsapp")
    assert old_event.ip_address is None
    assert old_event.disclosure_hash
    assert old_event.evidence_hash
    assert recent_event.ip_address == RECENT_IP


def test_default_is_count_only_and_mutates_nothing(old_and_recent):
    before = _snapshot()

    counts = ConsentService.redact_expired_ip()

    assert counts == {"current": 1, "events": 1}
    assert _snapshot() == before


def test_apply_changes_only_the_expired_ip_and_nothing_else(old_and_recent):
    before_current, before_events = _snapshot()

    ConsentService.redact_expired_ip(apply=True)

    after_current, after_events = _snapshot()
    pairs = zip(before_current + before_events, after_current + after_events, strict=True)
    for before, after in pairs:
        expired = before["ip_address"] == OLD_IP
        assert after["ip_address"] == (None if expired else before["ip_address"])
        assert {k: v for k, v in after.items() if k != "ip_address"} == {
            k: v for k, v in before.items() if k != "ip_address"
        }


def test_ceiling_is_ninety_days_even_when_asked_for_more(customer):
    ninety_one = timezone.now() - timedelta(days=91)
    ConsentService.grant_consent(customer.ref, "email", ip_address=OLD_IP, occurred_at=ninety_one)

    assert ConsentService.consent_ip_retention_days(365) == 90
    assert ConsentService.consent_ip_retention_days(0) == 1
    with override_settings(SHOPMAN_CONSENT_IP_RETENTION_DAYS=365):
        assert ConsentService.consent_ip_retention_days() == 90
        assert ConsentService.redact_expired_ip(apply=True)["events"] == 1
    assert CommunicationConsentEvent.objects.get().ip_address is None


def test_shorter_configured_retention_is_honored(customer):
    ten_days = timezone.now() - timedelta(days=10)
    ConsentService.grant_consent(customer.ref, "email", ip_address=OLD_IP, occurred_at=ten_days)

    with override_settings(SHOPMAN_CONSENT_IP_RETENTION_DAYS=7):
        assert ConsentService.redact_expired_ip() == {"current": 1, "events": 1}
    assert ConsentService.redact_expired_ip() == {"current": 0, "events": 0}


def test_rebuilt_projection_does_not_keep_the_ip_past_its_collection(customer):
    """``updated_at`` avança na reconstrução; o prazo conta da coleta, não dela."""

    old = timezone.now() - timedelta(days=91)
    ConsentService.grant_consent(customer.ref, "email", ip_address=OLD_IP, occurred_at=old)
    ConsentService.rebuild_current_state(customer.ref, "email")
    current = CommunicationConsent.objects.get(channel="email")
    assert current.ip_address == OLD_IP
    assert current.updated_at > timezone.now() - timedelta(days=1)

    assert ConsentService.redact_expired_ip(apply=True) == {"current": 1, "events": 1}
    assert CommunicationConsent.objects.get(channel="email").ip_address is None


def test_public_event_queryset_still_refuses_update(old_and_recent):
    """A exceção é o método de prazo; o QuerySet público segue append-only."""

    with pytest.raises(ValidationError):
        CommunicationConsentEvent.objects.update(ip_address=None)


def test_command_is_dry_run_by_default_and_prints_no_ip(old_and_recent):
    before = _snapshot()
    out = StringIO()

    call_command("purge_consent_ip", stdout=out)

    text = out.getvalue()
    assert "Simulação: 2 IP(s) com mais de 90 dias" in text
    assert "Nada foi alterado" in text
    assert OLD_IP not in text
    assert RECENT_IP not in text
    assert _snapshot() == before


def test_command_apply_redacts_and_caps_days(old_and_recent):
    out = StringIO()

    call_command("purge_consent_ip", "--apply", "--days", "365", stdout=out)

    text = out.getvalue()
    assert "2 IP(s) com mais de 90 dias removido(s)" in text
    assert OLD_IP not in text
    assert CommunicationConsent.objects.get(channel="email").ip_address is None
    assert CommunicationConsent.objects.get(channel="whatsapp").ip_address == RECENT_IP
    assert CommunicationConsentEvent.objects.filter(ip_address__isnull=False).count() == 1
