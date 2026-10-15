from __future__ import annotations

from datetime import date, timedelta

from django.test import override_settings

from shopman.watchman.contracts import CheckContext, Status
from shopman.watchman.expiry import ExpiryLifecycleCheck, assess_deadline, reached_milestone


def _context() -> CheckContext:
    return CheckContext(profile="infrastructure", deadline=999999999.0)


def test_deadline_is_actionable_before_it_breaks():
    today = date(2026, 10, 15)
    assert assess_deadline(today + timedelta(days=61), today=today).status is Status.PASS
    assert assess_deadline(today + timedelta(days=60), today=today).status is Status.WARN
    assert assess_deadline(today + timedelta(days=14), today=today).status is Status.FAIL
    assert assess_deadline(today - timedelta(days=1), today=today).milestone == "expired"


def test_host_can_keep_its_own_escalation_milestones():
    today = date(2026, 10, 15)
    policy = ((3, "critical"), (7, "warning"), (30, "warning"))
    assert reached_milestone(today + timedelta(days=8), today=today, milestones=policy) == ("30", "warning")
    assert reached_milestone(today + timedelta(days=2), today=today, milestones=policy) == ("3", "critical")
    assert reached_milestone(today, today=today, milestones=policy, expired=True) == ("expired", "critical")


@override_settings(
    WATCHMAN={
        "EXPIRING_RESOURCES": [
            {
                "id": "provider_token",
                "label": "Provider token",
                "deadline_env": "PROVIDER_TOKEN_EXPIRES_AT",
                "owner": "operations@example.com",
                "impact": "Checkout stops.",
                "action": "Create a replacement and overlap both tokens.",
                "runbook": "docs/runbooks/provider-token.md",
                "verification": "Run the provider smoke check.",
            }
        ]
    }
)
def test_check_never_needs_the_secret_value(monkeypatch):
    monkeypatch.setenv("PROVIDER_TOKEN_EXPIRES_AT", "2099-12-31")
    result = ExpiryLifecycleCheck().run(_context())
    assert result.status is Status.PASS
    [resource] = result.evidence["resources"]
    assert resource["owner"] == "operations@example.com"
    assert "secret" not in resource
    assert "token" not in resource


@override_settings(
    WATCHMAN={
        "EXPIRING_RESOURCES": [
            {"id": "missing_metadata", "deadline_env": "MISSING_EXPIRES_AT"}
        ]
    }
)
def test_missing_expiry_metadata_is_unknown_not_false_green(monkeypatch):
    monkeypatch.delenv("MISSING_EXPIRES_AT", raising=False)
    result = ExpiryLifecycleCheck().run(_context())
    assert result.status is Status.UNKNOWN
    assert result.evidence["resources"][0]["required_env"] == "MISSING_EXPIRES_AT"


@override_settings(
    WATCHMAN={
        "EXPIRING_RESOURCES": [
            {"id": "broken", "deadline_env": "BROKEN_EXPIRES_AT"}
        ]
    }
)
def test_malformed_metadata_fails_closed_without_exposing_env(monkeypatch):
    monkeypatch.setenv("BROKEN_EXPIRES_AT", "not-a-date")
    result = ExpiryLifecycleCheck().run(_context())
    assert result.status is Status.FAIL
    assert "not-a-date" not in str(result.to_dict())
