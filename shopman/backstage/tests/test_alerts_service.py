"""Alert mutation service tests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import alerts
from shopman.backstage.services.exceptions import AlertError


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
def test_ack_alert_marks_alert_and_is_idempotent():
    alert = OperatorAlert.objects.create(type="stock_low", severity="warning", message="Estoque baixo")

    assert alerts.ack_alert(alert.pk) is True
    assert alerts.ack_alert(alert.pk) is True
    alert.refresh_from_db()
    assert alert.acknowledged is True
    assert alerts.ack_alert(999999) is False


@pytest.mark.django_db
def test_list_count_and_ack_share_the_same_audience_scope():
    production = OperatorAlert.objects.create(
        type="production_late",
        audience="production",
        severity="warning",
        message="Produção atrasada",
    )
    finance = OperatorAlert.objects.create(
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
    assert alerts.ack_alert(finance.pk, user=operator) is False
    assert alerts.ack_alert(production.pk, user=operator) is True


@pytest.mark.django_db
def test_escalate_alert_updates_severity_and_message():
    alert = OperatorAlert.objects.create(type="stock_low", severity="warning", message="Estoque baixo")

    updated = alerts.escalate_alert(alert.pk, severity="critical", message="Estoque crítico")

    assert updated.severity == "critical"
    assert updated.message == "Estoque crítico"


@pytest.mark.django_db
def test_escalate_alert_validates_inputs():
    alert = OperatorAlert.objects.create(type="stock_low", severity="warning", message="Estoque baixo")

    with pytest.raises(AlertError):
        alerts.escalate_alert(alert.pk, severity="fatal")

    with pytest.raises(AlertError):
        alerts.escalate_alert(999999)
