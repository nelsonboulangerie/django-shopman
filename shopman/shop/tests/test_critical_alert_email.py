from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive

from shopman.shop.services import critical_alerts, observability

pytestmark = pytest.mark.django_db


@pytest.fixture
def paging(settings, monkeypatch):
    settings.SHOPMAN_OPERATOR_EMAIL = "owner@example.com"
    monkeypatch.setattr("shopman.orderman.dispatch._on_commit_callback", lambda *args: None)
    monkeypatch.setattr("shopman.shop.adapters.notification_email.is_available", lambda *args: True)


def test_critical_alert_queues_once_per_type_without_raw_sensitive_detail(paging):
    for ref in ["ORDER-1", "ORDER-2"]:
        observability.create_operator_alert(type="fiscal_emit_failed", severity="critical",
                                           message="private provider content", order_ref=ref, dedupe_key=ref)
    task = Directive.objects.get(payload__event="operator_critical")
    assert task.payload["recipient"] == "owner@example.com"
    assert "private provider content" not in str(task.payload)
    assert task.payload["backends"] == ["email"]


def test_noncritical_alert_does_not_page(paging):
    observability.create_operator_alert(type="test", severity="warning", message="test")
    assert not Directive.objects.filter(payload__event="operator_critical").exists()


def test_accepted_email_replay_does_not_resend(paging, monkeypatch):
    observability.create_operator_alert(type="test", severity="critical", message="test")
    task = Directive.objects.get(payload__event="operator_critical")
    send = Mock(return_value=SimpleNamespace(success=True, outcome_unknown=False))
    monkeypatch.setattr(critical_alerts, "notify", send)
    critical_alerts.deliver(task)
    critical_alerts.deliver(task)
    assert send.call_count == 1


def test_lost_email_response_prevents_automatic_second_send(paging, monkeypatch):
    observability.create_operator_alert(type="test", severity="critical", message="test")
    task = Directive.objects.get(payload__event="operator_critical")
    send = Mock(return_value=SimpleNamespace(success=False, outcome_unknown=True))
    monkeypatch.setattr(critical_alerts, "notify", send)
    for _ in range(2):
        with pytest.raises(DirectiveTerminalError):
            critical_alerts.deliver(task)
    assert send.call_count == 1
