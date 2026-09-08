"""Headless operator alerts API contract (api/v1/backstage/alerts/*).

The dedicated operator apps consume this instead of the legacy HTMX alert
fragments.  The outer gate is shared with the sidebar badge; rows, counts and
acknowledgement are additionally scoped by alert audience and actor capability.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from shopman.backstage.models import OperatorAlert
from shopman.shop.models import Shop


def _manage_orders_perm() -> Permission:
    return Permission.objects.get(
        content_type=ContentType.objects.get(app_label="shop", model="shop"),
        codename="manage_orders",
    )


def _permission(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(
        content_type__app_label=app_label,
        codename=codename,
    )


@pytest.fixture
def shop(db):
    return Shop.objects.create(name="Loja")


@pytest.fixture
def operator(db, shop):
    user = User.objects.create_user("alerts-op", password="pw", is_staff=True)
    user.user_permissions.add(_manage_orders_perm())
    return user


@pytest.fixture
def alert(db):
    return OperatorAlert.objects.create(
        type="stale_new_order",
        audience="orders",
        severity="warning",
        message="Pedido aguardando confirmação",
    )


@pytest.mark.django_db
def test_list_requires_operator_capability(client, db, shop, alert):
    # staff WITHOUT any operator capability → blocked
    bare = User.objects.create_user("bare-staff", password="pw", is_staff=True)
    client.force_login(bare)
    assert client.get(reverse("api-backstage-alerts")).status_code == 403


@pytest.mark.django_db
def test_list_blocks_non_staff(client, db, shop, alert):
    customer = User.objects.create_user("cust", password="pw", is_staff=False)
    client.force_login(customer)
    assert client.get(reverse("api-backstage-alerts")).status_code == 403


@pytest.mark.django_db
def test_list_returns_alerts_and_counts(client, operator, alert):
    OperatorAlert.objects.create(
        type="payment_failed",
        audience="finance",
        severity="critical",
        message="Pix falhou",
    )
    OperatorAlert.objects.create(
        type="production_late",
        audience="production",
        severity="critical",
        message="Produção atrasada",
    )
    client.force_login(operator)
    response = client.get(reverse("api-backstage-alerts"))
    assert response.status_code == 200
    body = response.json()
    assert body["counts"] == {"active": 1, "critical": 0}
    assert len(body["alerts"]) == 1
    first = body["alerts"][0]
    assert first["audience"] == "orders"
    assert first["actions"][0] == {
        "ref": "acknowledge",
        "kind": "mutation",
        "label": "Reconhecer",
        "priority": "secondary",
        "enabled": True,
        "reason": "",
        "method": "POST",
        "href": f"/api/v1/backstage/alerts/{alert.pk}/ack/",
        "payload_schema": {},
        "expected_rev": None,
        "idempotency": "idempotent",
        "confirmation": {},
        "approval_requirement": None,
        "source_alert_ref": str(alert.pk),
        "lifecycle_effect": "acknowledges",
    }


@pytest.mark.django_db
def test_list_excludes_acknowledged(client, operator, alert):
    alert.acknowledged = True
    alert.save(update_fields=["acknowledged"])
    client.force_login(operator)
    body = client.get(reverse("api-backstage-alerts")).json()
    assert body["counts"]["active"] == 0
    assert body["alerts"] == []


@pytest.mark.django_db
def test_ack_marks_alert(client, operator, alert):
    client.force_login(operator)
    response = client.post(reverse("api-backstage-alert-ack", args=[alert.pk]))
    assert response.status_code == 200
    assert response.json() == {"ok": True, "pk": alert.pk}
    alert.refresh_from_db()
    assert alert.acknowledged is True


@pytest.mark.django_db
def test_ack_unknown_is_404(client, operator):
    client.force_login(operator)
    assert client.post(reverse("api-backstage-alert-ack", args=[999999])).status_code == 404


@pytest.mark.django_db
def test_production_operator_cannot_see_or_ack_finance_alert(client, shop):
    operator = User.objects.create_user("production-alerts", password="pw", is_staff=True)
    operator.user_permissions.add(_permission("backstage", "operate_production"))
    finance = OperatorAlert.objects.create(
        type="payment_disputed",
        audience="finance",
        severity="critical",
        message="Contestação financeira",
    )
    production = OperatorAlert.objects.create(
        type="production_late",
        audience="production",
        severity="warning",
        message="Produção atrasada",
    )
    client.force_login(operator)

    listed = client.get(reverse("api-backstage-alerts")).json()
    forbidden_ack = client.post(reverse("api-backstage-alert-ack", args=[finance.pk]))

    assert [row["pk"] for row in listed["alerts"]] == [production.pk]
    assert listed["counts"] == {"active": 1, "critical": 0}
    assert forbidden_ack.status_code == 404
    finance.refresh_from_db()
    assert finance.acknowledged is False


@pytest.mark.django_db
def test_cash_auditor_can_see_finance_audience(client, shop):
    auditor = User.objects.create_user("finance-alerts", password="pw", is_staff=True)
    auditor.user_permissions.add(_permission("cashman", "audit_shift"))
    finance = OperatorAlert.objects.create(
        type="payment_failed",
        audience="finance",
        severity="critical",
        message="Falha financeira",
    )
    client.force_login(auditor)

    response = client.get(reverse("api-backstage-alerts"))

    assert response.status_code == 200
    assert [row["pk"] for row in response.json()["alerts"]] == [finance.pk]
