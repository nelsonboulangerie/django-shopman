"""Incidentes por tipo: dono, episódios, verde desde, e a porta só de leitura da ponte."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from shopman.backstage.incidents.summary import count_episodes, summarize
from shopman.backstage.models import IncidentReaderCredential, OperatorAlert

pytestmark = pytest.mark.django_db


def _alert(alert_type, *, hours_ago, resolved_hours_ago=None, severity="critical", order_ref="", message="Cliente Maria"):
    now = timezone.now()
    alert = OperatorAlert.objects.create(type=alert_type, severity=severity, message=message, order_ref=order_ref)
    resolved = now - timedelta(hours=resolved_hours_ago) if resolved_hours_ago is not None else None
    OperatorAlert.objects.filter(pk=alert.pk).update(created_at=now - timedelta(hours=hours_ago), resolved_at=resolved)
    return alert


def test_episodes_merge_overlapping_intervals():
    now = timezone.now()
    h = lambda n: now - timedelta(hours=n)  # noqa: E731
    assert count_episodes([(h(10), h(8)), (h(9), h(7)), (h(5), h(4)), (h(2), None)], now=now) == 3
    assert count_episodes([], now=now) == 0


def test_eight_alerts_in_one_burst_are_one_episode_not_recurring():
    for i in range(8):
        _alert("lifecycle_phase_stuck", hours_ago=48, order_ref=f"IFOOD-{i}")
    (group,) = summarize()
    assert group.open_count == 8
    assert group.episodes == 1
    assert group.recurring is False
    assert group.owner == "Engenharia"
    assert len(group.order_refs) == 8


def test_three_returns_in_seven_days_mark_recurring():
    _alert("webhook_failed", hours_ago=120, resolved_hours_ago=119)
    _alert("webhook_failed", hours_ago=60, resolved_hours_ago=59)
    _alert("webhook_failed", hours_ago=3)
    (group,) = summarize()
    assert group.episodes == 3
    assert group.recurring is True


def test_green_group_reports_since_when_and_old_resolved_alerts_drop_out():
    _alert("stock_low", hours_ago=30, resolved_hours_ago=26, severity="warning")
    _alert("stock_low", hours_ago=24 * 10, resolved_hours_ago=24 * 9)
    (group,) = summarize()
    assert group.open_count == 0
    assert group.green_since is not None
    assert timezone.now() - group.green_since > timedelta(hours=25)
    assert group.owner == "Produção"


@pytest.mark.parametrize(
    "alert_type",
    ["ifood_event_unhandled", "orphan_holds_released",
     "stock_alert_dispatch_unknown", "stock_alert_delivery_stuck"],
)
def test_operations_alerts_without_a_counter_gesture_go_to_engineering(alert_type):
    """Triagem de 21/11: público "operations", mas a causa está no código ou na integração."""
    from shopman.backstage.incidents.owners import owner_for

    assert owner_for(alert_type, audience="operations") == "Engenharia"
    assert owner_for("notification_failed", audience="operations") == "Operação"
    assert owner_for("stock_hold_gap", audience="operations") == "Operação", "venda acima do estoque: contar"


def test_open_alert_from_before_the_window_still_counts():
    _alert("integration_failed", hours_ago=24 * 30)
    (group,) = summarize()
    assert group.open_count == 1
    assert group.episodes == 1


def test_payload_never_carries_the_alert_message():
    _alert("payment_failed", hours_ago=1, message="Cliente Maria Souza, 11 99999-0000")
    payload = summarize()[0].to_dict()
    assert "Maria" not in str(payload)


def _url():
    return reverse("api-backstage-incidents")


def test_endpoint_refuses_anonymous_and_staff_without_superuser(client):
    assert client.get(_url()).status_code in (401, 403)
    staff = User.objects.create_user("gerente", password="x", is_staff=True)
    client.force_login(staff)
    assert client.get(_url()).status_code == 403


def test_endpoint_accepts_superuser(client):
    client.force_login(User.objects.create_superuser("dono", password="x"))
    _alert("webhook_failed", hours_ago=1)
    body = client.get(_url()).json()
    assert body["schema_version"] == 1
    assert body["groups"][0]["fingerprint"] == "shop:webhook_failed"


def test_bridge_credential_reads_and_revocation_closes(client):
    _alert("webhook_failed", hours_ago=1)
    credential, bearer = IncidentReaderCredential.issue(label="ponte", expires_at=timezone.now() + timedelta(days=1))
    ok = client.get(_url(), HTTP_AUTHORIZATION=f"Bearer {bearer}")
    assert ok.status_code == 200
    credential.refresh_from_db()
    assert credential.last_seen_at is not None

    wrong = bearer[:-2] + ("aa" if not bearer.endswith("aa") else "bb")
    assert client.get(_url(), HTTP_AUTHORIZATION=f"Bearer {wrong}").status_code in (401, 403)

    IncidentReaderCredential.objects.filter(pk=credential.pk).update(is_active=False)
    assert client.get(_url(), HTTP_AUTHORIZATION=f"Bearer {bearer}").status_code in (401, 403)


def test_expired_credential_is_refused(client):
    _credential, bearer = IncidentReaderCredential.issue(label="ponte", expires_at=timezone.now() - timedelta(minutes=1))
    assert client.get(_url(), HTTP_AUTHORIZATION=f"Bearer {bearer}").status_code in (401, 403)


def test_bridge_credential_opens_no_other_backstage_route(client):
    _credential, bearer = IncidentReaderCredential.issue(label="ponte", expires_at=timezone.now() + timedelta(days=1))
    other = reverse("api-backstage-channel-health")
    assert client.get(other, HTTP_AUTHORIZATION=f"Bearer {bearer}").status_code in (401, 403)
