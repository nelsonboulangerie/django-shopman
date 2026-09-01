"""Operational observability tests."""
from __future__ import annotations

import json
import logging

import pytest

from shopman.backstage.models import OperatorAlert
from shopman.shop.logging import JsonLogFormatter
from shopman.shop.services import observability


def test_json_log_formatter_includes_extra_fields() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="shopman.operational",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="payment.reconciled",
        args=(),
        exc_info=None,
    )
    record.event = "payment.reconciled"
    record.order_ref = "ORD-OBS-1"
    record.amount_q = 1200

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "shopman.operational"
    assert payload["message"] == "payment.reconciled"
    assert payload["event"] == "payment.reconciled"
    assert payload["order_ref"] == "ORD-OBS-1"
    assert payload["amount_q"] == 1200
    assert "timestamp" in payload


@pytest.mark.django_db
def test_record_webhook_failure_creates_debounced_operator_alert() -> None:
    first = observability.record_webhook_failure(
        provider="stripe",
        reason="processing_failed",
        status_code=500,
        external_ref="evt_obs_1",
    )
    second = observability.record_webhook_failure(
        provider="stripe",
        reason="processing_failed",
        status_code=500,
        external_ref="evt_obs_1",
    )

    assert first is not None
    assert second is None
    alert = OperatorAlert.objects.get(type="webhook_failed")
    assert alert.severity == "error"
    assert "Webhook stripe falhou" in alert.message
    assert OperatorAlert.objects.filter(type="webhook_failed").count() == 1


@pytest.mark.django_db
def test_record_integration_failure_creates_debounced_operator_alert() -> None:
    first = observability.record_integration_failure(
        provider="google_geocoding",
        operation="forward_geocode",
        detail="status=REQUEST_DENIED",
    )
    second = observability.record_integration_failure(
        provider="google_geocoding",
        operation="forward_geocode",
        detail="status=REQUEST_DENIED",
    )

    assert first is not None
    assert second is None
    alert = OperatorAlert.objects.get(type="integration_failed")
    assert alert.severity == "error"
    assert "Google Geocoding" in alert.message
    assert "REQUEST_DENIED" in alert.message
    assert OperatorAlert.objects.filter(type="integration_failed").count() == 1


@pytest.mark.django_db
def test_integration_failed_type_is_registered_for_operator() -> None:
    """O tipo precisa de rótulo humano nos choices — slug cru no crachá do Admin
    seria ilegível (mesmo contrato do coupon_over_redeemed)."""
    alert = observability.record_integration_failure(
        provider="google_geocoding",
        operation="reverse_geocode",
        detail="status=UNKNOWN_ERROR",
    )

    assert alert is not None
    label = alert.get_type_display()
    assert label and label != "integration_failed"


@pytest.mark.django_db
def test_record_integration_failure_notifies_order_managers() -> None:
    """Alerta NOVO avisa quem gerencia pedidos pelo canal pessoal — o precedente
    é o _notify_badge_reissue do sign_in_audit."""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission

    from shopman.shop.models import NotificationCategory, UserNotification

    User = get_user_model()
    gestor = User.objects.create_user("gina", password="x", is_staff=True, is_active=True)
    gestor.user_permissions.add(
        Permission.objects.get(content_type__app_label="shop", codename="manage_orders")
    )
    balconista = User.objects.create_user("bia", password="x", is_staff=True, is_active=True)

    first = observability.record_integration_failure(
        provider="google_geocoding",
        operation="antifraud_delivery_check",
        detail="status=REQUEST_DENIED",
        severity="critical",
    )
    # Debounced: NÃO duplica a notificação pessoal.
    second = observability.record_integration_failure(
        provider="google_geocoding",
        operation="antifraud_delivery_check",
        detail="status=REQUEST_DENIED",
        severity="critical",
    )

    assert first is not None
    assert second is None
    aviso = UserNotification.objects.get(user=gestor)
    assert aviso.category == NotificationCategory.SYSTEM
    assert "Google Geocoding" in aviso.title
    assert "antifraud_delivery_check" in aviso.message
    assert not UserNotification.objects.filter(user=balconista).exists()


@pytest.mark.django_db
def test_record_integration_failure_never_raises_when_notification_breaks(monkeypatch) -> None:
    """Observabilidade não derruba a request do cliente — nem quando a camada de
    notificação quebra inteira."""
    import shopman.shop.services.campaign as campaign

    def _boom(notification):
        raise RuntimeError("push quebrou")

    monkeypatch.setattr(campaign, "push_user_notification", _boom)

    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission

    User = get_user_model()
    gestor = User.objects.create_user("gina", password="x", is_staff=True, is_active=True)
    gestor.user_permissions.add(
        Permission.objects.get(content_type__app_label="shop", codename="manage_orders")
    )

    alert = observability.record_integration_failure(
        provider="google_geocoding",
        operation="forward_geocode",
        detail="status=OVER_QUERY_LIMIT",
    )

    assert alert is not None  # o alerta operacional sobrevive à quebra do push


@pytest.mark.django_db
def test_record_payment_reconciliation_failure_creates_critical_alert() -> None:
    alert = observability.record_payment_reconciliation_failure(
        gateway="stripe",
        intent_ref="PAY-OBS-1",
        order_ref="ORD-OBS-1",
        code="reconciliation_refund_mismatch",
        context={"local_refunded_q": 5000, "gateway_refunded_q": 3000},
    )

    assert alert is not None
    alert.refresh_from_db()
    assert alert.type == "payment_reconciliation_failed"
    assert alert.severity == "critical"
    assert alert.order_ref == "ORD-OBS-1"
    assert "PAY-OBS-1" in alert.message
