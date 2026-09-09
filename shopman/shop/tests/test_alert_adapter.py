from __future__ import annotations

import pytest

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services.exceptions import AlertError
from shopman.shop.adapters import alert as alert_adapter


@pytest.mark.django_db
def test_system_resolution_records_actor_time_and_revision():
    alert = OperatorAlert.objects.create(
        type="payment_failed",
        severity="error",
        message="Pagamento falhou",
        order_ref="ORD-RESOLVE-1",
    )

    count = alert_adapter.resolve(
        "payment_failed",
        order_ref="ORD-RESOLVE-1",
        actor="system:payment",
    )

    alert.refresh_from_db()
    assert count == 1
    assert alert.acknowledged is True
    assert alert.acknowledged_at is None
    assert alert.acknowledged_by == ""
    assert alert.resolved_at is not None
    assert alert.resolved_by == "system:payment"
    assert alert.rev == 1


@pytest.mark.django_db
def test_system_resolution_is_idempotent():
    OperatorAlert.objects.create(
        type="payment_insufficient",
        severity="warning",
        message="Pagamento parcial",
        order_ref="ORD-RESOLVE-2",
    )

    assert (
        alert_adapter.resolve(
            "payment_insufficient",
            order_ref="ORD-RESOLVE-2",
            actor="system:pix-confirmation",
        )
        == 1
    )
    assert (
        alert_adapter.resolve(
            "payment_insufficient",
            order_ref="ORD-RESOLVE-2",
            actor="system:pix-confirmation",
        )
        == 0
    )


@pytest.mark.django_db
def test_system_resolution_rejects_an_omitted_target_without_bulk_mutation():
    first = OperatorAlert.objects.create(
        type="payment_failed",
        severity="error",
        message="Falha A",
        order_ref="ORD-A",
    )
    second = OperatorAlert.objects.create(
        type="payment_failed",
        severity="error",
        message="Falha B",
        order_ref="ORD-B",
    )

    with pytest.raises(TypeError):
        alert_adapter.resolve("payment_failed", actor="system:payment")
    with pytest.raises(AlertError):
        alert_adapter.resolve("payment_failed", order_ref="", actor="system:payment")

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.acknowledged is second.acknowledged is False
