"""Headless operator alerts API contract (api/v1/backstage/alerts/*).

The dedicated operator apps consume this instead of the legacy HTMX alert
fragments.  The outer gate is shared with the sidebar badge; rows, counts and
acknowledgement are additionally scoped by alert audience and actor capability.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe

from shopman.backstage.models import OperatorAlert
from shopman.backstage.services import alerts as alert_service
from shopman.shop.models import Shop


def _ack_body(projection: dict, alert_pk: int, *, key: str = "ack-attempt") -> dict:
    action = next(
        item
        for alert in projection["alerts"]
        if alert["pk"] == alert_pk
        for item in alert["actions"]
        if item["ref"] == f"acknowledge:{alert_pk}"
    )
    return {
        "expected_rev": action["expected_rev"],
        "idempotency_key": key,
        "projection_generated_at": projection["generated_at"],
        "source_revision": projection["source_revision"],
        "fresh_until": projection["fresh_until"],
        "contract_version": projection["contract_version"],
        "action_ref": action["ref"],
        "action_proof": action["proof"],
    }


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
    assert {
        "pk",
        "type",
        "type_label",
        "severity",
        "severity_label",
        "message",
        "created_at_display",
        "actions",
    } <= set(first)
    assert first["actions"][0]["kind"] == "acknowledge_alert"
    assert first["actions"][0]["enabled"] is True
    assert first["audience"] == "orders"
    assert first["actions"][0] == {
        "ref": f"acknowledge:{alert.pk}",
        "kind": "acknowledge_alert",
        "label": "Visto",
        "priority": 20,
        "enabled": True,
        "reason": "",
        "method": "POST",
        "href": f"/api/v1/backstage/alerts/{alert.pk}/ack/",
        "payload_schema": "AlertAckMutationRequest",
        "expected_rev": 0,
        "idempotency": {
            "required": True,
            "key_scope": f"backstage.alert-ack:{alert.pk}",
        },
        "confirmation": {
            "required": False,
            "reason_required": False,
            "title": "",
            "confirm_label": "Confirmar",
        },
        "approval_requirement": None,
        "source_alert_ref": str(alert.pk),
        "source_alert_effect": "acknowledges",
        "proof": first["actions"][0]["proof"],
    }
    assert first["actions"][0]["proof"]
    assert body["source_revision"].startswith("sha256:")
    assert body["generated_at"] < body["fresh_until"]


@pytest.mark.django_db
def test_list_keeps_acknowledged_alert_until_the_cause_is_resolved(client, operator, alert):
    alert.acknowledged = True
    alert.save(update_fields=["acknowledged"])
    client.force_login(operator)
    body = client.get(reverse("api-backstage-alerts")).json()
    assert body["counts"]["active"] == 1
    assert [row["pk"] for row in body["alerts"]] == [alert.pk]
    assert not any(action["kind"] == "acknowledge_alert" for action in body["alerts"][0]["actions"])


@pytest.mark.django_db
def test_ack_marks_alert(client, operator, alert):
    client.force_login(operator)
    projection = client.get(reverse("api-backstage-alerts")).json()
    body = _ack_body(projection, alert.pk)
    response = client.post(
        reverse("api-backstage-alert-ack", args=[alert.pk]),
        body,
        content_type="application/json",
    )
    replay = client.post(
        reverse("api-backstage-alert-ack", args=[alert.pk]),
        body,
        content_type="application/json",
    )
    assert response.status_code == replay.status_code == 200
    assert response.json() == {"ok": True, "pk": alert.pk}
    alert.refresh_from_db()
    assert alert.acknowledged is True
    assert alert.acknowledged_at is not None
    assert alert.acknowledged_by == operator.username
    current = client.get(reverse("api-backstage-alerts")).json()
    assert [row["pk"] for row in current["alerts"]] == [alert.pk]


@pytest.mark.django_db
def test_production_alert_projects_server_owned_recovery_context(client, shop):
    operator = User.objects.create_user("production-context", password="pw", is_staff=True)
    operator.user_permissions.add(_permission("backstage", "operate_production"))
    recipe = Recipe.objects.create(
        ref="alert-deep-link",
        name="Pao de alerta",
        output_sku="ALERT-DEEP-LINK",
        batch_size=1,
    )
    target_date = date.today() - timedelta(days=1)
    work_order = craft.plan(recipe, 1, date=target_date)
    alert = OperatorAlert.objects.create(
        type="production_unfinished",
        audience="production",
        severity="error",
        message="Fornada ainda aberta",
        order_ref=work_order.ref,
    )
    client.force_login(operator)

    projected = client.get(reverse("api-backstage-alerts")).json()
    row = next(item for item in projected["alerts"] if item["pk"] == alert.pk)
    context = next(action for action in row["actions"] if action["kind"] == "open_alert_context")

    assert context["method"] == "GET"
    assert context["href"] == (
        f"/expedite?q={work_order.ref}&date={target_date.isoformat()}"
    )
    assert context["source_alert_effect"] == "keeps_open"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "alert_type",
    ("production_low_yield", "production_batch_traceability"),
)
def test_production_close_alerts_route_to_expedition(client, shop, alert_type):
    operator = User.objects.create_user(
        f"production-{alert_type}",
        password="pw",
        is_staff=True,
    )
    operator.user_permissions.add(_permission("backstage", "operate_production"))
    alert = OperatorAlert.objects.create(
        type=alert_type,
        audience="production",
        severity="error",
        message="Resolver fechamento",
        order_ref="WO-42",
    )
    client.force_login(operator)

    projected = client.get(reverse("api-backstage-alerts")).json()
    row = next(item for item in projected["alerts"] if item["pk"] == alert.pk)
    context = next(action for action in row["actions"] if action["kind"] == "open_alert_context")

    assert context["href"] == "/expedite?q=WO-42"


@pytest.mark.django_db
def test_ack_without_a_projected_action_is_rejected_before_target_lookup(client, operator):
    client.force_login(operator)
    response = client.post(reverse("api-backstage-alert-ack", args=[999999]))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


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
    body = _ack_body(listed, production.pk, key="finance-forgery")
    forbidden_ack = client.post(
        reverse("api-backstage-alert-ack", args=[finance.pk]),
        body,
        content_type="application/json",
    )

    assert [row["pk"] for row in listed["alerts"]] == [production.pk]
    assert listed["counts"] == {"active": 1, "critical": 0}
    assert forbidden_ack.status_code == 400
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


@pytest.mark.django_db
def test_limited_projection_cannot_ack_an_older_unprojected_alert(
    client,
    operator,
):
    older = OperatorAlert.objects.create(
        type="stale_new_order",
        audience="orders",
        severity="warning",
        message="Antigo",
    )
    newer = OperatorAlert.objects.create(
        type="stale_new_order",
        audience="orders",
        severity="warning",
        message="Novo",
    )
    client.force_login(operator)
    projection = client.get(reverse("api-backstage-alerts"), {"limit": 1}).json()
    assert [item["pk"] for item in projection["alerts"]] == [newer.pk]
    body = _ack_body(projection, newer.pk, key="limited-proof")

    missing = client.post(reverse("api-backstage-alert-ack", args=[older.pk]))
    cross_target = client.post(
        reverse("api-backstage-alert-ack", args=[older.pk]),
        body,
        content_type="application/json",
    )

    assert missing.status_code == 400
    assert cross_target.status_code == 400
    older.refresh_from_db()
    assert older.acknowledged is False


@pytest.mark.django_db
def test_alert_action_proof_and_idempotency_key_are_single_target_single_attempt(
    client,
    operator,
):
    first = OperatorAlert.objects.create(
        type="stale_new_order",
        audience="orders",
        message="Primeiro",
    )
    second = OperatorAlert.objects.create(
        type="stale_new_order",
        audience="orders",
        message="Segundo",
    )
    client.force_login(operator)
    projection = client.get(reverse("api-backstage-alerts")).json()
    body = _ack_body(projection, first.pk, key="one-alert-action")

    accepted = client.post(
        reverse("api-backstage-alert-ack", args=[first.pk]),
        body,
        content_type="application/json",
    )
    reused_key = client.post(
        reverse("api-backstage-alert-ack", args=[first.pk]),
        {**body, "idempotency_key": "another-attempt"},
        content_type="application/json",
    )
    cross_target = client.post(
        reverse("api-backstage-alert-ack", args=[second.pk]),
        body,
        content_type="application/json",
    )

    assert accepted.status_code == 200
    assert reused_key.status_code == 409
    assert cross_target.status_code == 400
    assert OperatorAlert.objects.get(pk=first.pk).acknowledged is True
    assert OperatorAlert.objects.get(pk=second.pk).acknowledged is False


@pytest.mark.django_db
def test_ack_rejects_an_alert_changed_after_projection(client, operator, alert):
    client.force_login(operator)
    projection = client.get(reverse("api-backstage-alerts")).json()
    stale_body = _ack_body(projection, alert.pk, key="stale-alert")
    alert_service.escalate_alert(
        alert.pk,
        severity="critical",
        message="Perigo crítico atualizado",
    )

    stale = client.post(
        reverse("api-backstage-alert-ack", args=[alert.pk]),
        stale_body,
        content_type="application/json",
    )

    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "stale_projection",
        "sent_rev": 0,
        "current_rev": 1,
        "recovery": {"action": "refresh", "label": "Atualizar alertas"},
    }
    alert.refresh_from_db()
    assert alert.acknowledged is False

    current = client.get(reverse("api-backstage-alerts")).json()
    accepted = client.post(
        reverse("api-backstage-alert-ack", args=[alert.pk]),
        _ack_body(current, alert.pk, key="current-alert"),
        content_type="application/json",
    )
    assert accepted.status_code == 200
