"""Alert mutation service tests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import alerts
from shopman.backstage.services.exceptions import AlertConflict, AlertError


@pytest.mark.django_db
def test_create_alert_validates_type_and_message():
    alert = alerts.create_alert(
        type="production_late",
        severity="warning",
        message="Produção atrasada",
        order_ref="WO-1",
    )

    assert alert.pk
    assert alert.order_ref == "WO-1"
    assert alert.audience == "production"

    with pytest.raises(AlertError):
        alerts.create_alert(type="unknown", message="x")

    with pytest.raises(AlertError):
        alerts.create_alert(type="production_late", message="")


@pytest.mark.django_db
def test_list_and_count_active_alerts():
    OperatorAlert.objects.create(type="stock_low", severity="warning", message="Estoque baixo")
    OperatorAlert.objects.create(type="production_late", severity="critical", message="Produção atrasada")
    OperatorAlert.objects.create(
        type="payment_failed",
        severity="error",
        message="Pago falhou",
        acknowledged=True,
    )

    active = alerts.list_active_alerts(limit=10)
    counts = alerts.active_counts()

    assert len(active) == 2
    assert counts.active == 2
    assert counts.critical == 1


@pytest.mark.django_db
def test_ack_alert_rejects_an_unprojected_internal_write():
    alert = OperatorAlert.objects.create(type="stock_low", severity="warning", message="Estoque baixo")

    with pytest.raises(TypeError):
        alerts.ack_alert(alert.pk)
    with pytest.raises(AlertConflict):
        alerts.ack_alert(
            alert.pk,
            user=None,
            expected_rev=alert.rev,
            idempotency_key="direct-write",
            action_proof="forged",
        )
    alert.refresh_from_db()
    assert alert.acknowledged is False
    assert alert.acknowledged_at is None


@pytest.mark.django_db
def test_list_and_count_share_the_same_audience_scope():
    production = OperatorAlert.objects.create(
        type="production_late",
        audience="production",
        severity="warning",
        message="Produção atrasada",
    )
    OperatorAlert.objects.create(
        type="payment_failed",
        audience="finance",
        severity="critical",
        message="Pagamento falhou",
    )
    operator = User.objects.create_user("production-alert-service", is_staff=True)
    operator.user_permissions.add(
        Permission.objects.get(
            content_type__app_label="backstage",
            codename="operate_production",
        )
    )

    assert alerts.list_active_alerts(user=operator) == [production]
    assert alerts.active_counts(user=operator) == alerts.AlertCounts(active=1, critical=0)


@pytest.mark.django_db
def test_escalate_alert_updates_severity_and_message():
    alert = OperatorAlert.objects.create(type="stock_low", severity="warning", message="Estoque baixo")

    updated = alerts.escalate_alert(alert.pk, severity="critical", message="Estoque crítico")

    assert updated.severity == "critical"
    assert updated.message == "Estoque crítico"
    assert updated.rev == 1


@pytest.mark.django_db
def test_escalate_alert_validates_inputs():
    alert = OperatorAlert.objects.create(type="stock_low", severity="warning", message="Estoque baixo")

    with pytest.raises(AlertError):
        alerts.escalate_alert(alert.pk, severity="fatal")

    with pytest.raises(AlertError):
        alerts.escalate_alert(999999)
