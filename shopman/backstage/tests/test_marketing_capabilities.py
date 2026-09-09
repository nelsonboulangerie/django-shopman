"""MKT-007 — autoridade de Marketing é granular e deny-by-default."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

pytestmark = pytest.mark.django_db

User = get_user_model()

BOARD = "/api/v1/backstage/marketing/"
PREVIEW = "/api/v1/backstage/marketing/preview/"
RULES = "/api/v1/backstage/marketing/rules/"
APPROVE = "/api/v1/backstage/marketing/announcements/999999/approve/"
REJECT = "/api/v1/backstage/marketing/announcements/999999/reject/"
FIRE = "/api/v1/backstage/marketing/rules/999999/fire/"
TEST_SEND = "/api/v1/backstage/marketing/whatsapp-template/test/"
PLATFORM_CONFIG = "/api/v1/backstage/marketing/whatsapp-template/"


def _operator(username: str, *codenames: str):
    user = User.objects.create_user(username=username, password="x", is_staff=True)
    user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    return user


def test_default_is_deny_for_read_and_external_effect(client):
    client.force_login(_operator("sem-capacidade"))

    assert client.get(BOARD).status_code == 403
    assert client.post(FIRE, data={}, content_type="application/json").status_code == 403


def test_legacy_permission_only_falls_back_for_safe_operations(client, monkeypatch):
    decisions = []
    monkeypatch.setattr(
        "shopman.backstage.api.permissions.logger.info",
        lambda message, *args: decisions.append(message % args),
    )
    client.force_login(_operator("legado", "manage_campaigns"))

    assert client.get(BOARD).status_code == 200
    assert client.post(PREVIEW, data={"body": "Olá"}, content_type="application/json").status_code == 200
    assert client.post(APPROVE, data={}, content_type="application/json").status_code == 403
    assert client.post(FIRE, data={}, content_type="application/json").status_code == 403
    assert client.post(TEST_SEND, data={}, content_type="application/json").status_code == 403
    assert client.post(PLATFORM_CONFIG, data={}, content_type="application/json").status_code == 403

    assert any("decision=legacy_safe_allow" in message for message in decisions)
    assert any("decision=deny reason=legacy_permission" in message for message in decisions)


def test_editor_can_edit_and_preview_but_cannot_decide_or_publish(client):
    client.force_login(_operator(
        "editor",
        "view_marketing",
        "edit_marketing_campaigns",
        "edit_marketing_templates",
        "preview_marketing_audience",
    ))

    assert client.get(BOARD).status_code == 200
    assert client.post(PREVIEW, data={"body": "Olá"}, content_type="application/json").status_code == 200
    # A capability deixou o gate passar; agora é a validação do formulário.
    assert client.post(RULES, data={}, content_type="application/json").status_code == 400
    assert client.post(REJECT, data={}, content_type="application/json").status_code == 403
    assert client.post(APPROVE, data={}, content_type="application/json").status_code == 403


def test_approver_can_reject_but_coupled_legacy_publish_requires_publisher(client):
    client.force_login(_operator(
        "aprovador",
        "view_marketing",
        "preview_marketing_audience",
        "approve_marketing_announcements",
    ))

    # 404 prova que passou pelo gate e chegou à busca do recurso.
    assert client.post(REJECT, data={}, content_type="application/json").status_code == 409
    # O endpoint legado ainda aprova+despacha; até MKT-009 separá-lo, exige ambas.
    assert client.post(APPROVE, data={}, content_type="application/json").status_code == 403


def test_publisher_passes_approve_and_fire_gates(client):
    client.force_login(_operator(
        "publisher",
        "approve_marketing_announcements",
        "publish_marketing_announcements",
        "fire_marketing_campaigns",
    ))

    assert client.post(APPROVE, data={}, content_type="application/json").status_code == 409
    assert client.post(FIRE, data={}, content_type="application/json").status_code == 409


def test_platform_owner_can_configure_but_publisher_cannot(client, monkeypatch):
    monkeypatch.setattr("shopman.shop.services.manychat_flows.list_flows", lambda: [])
    owner = _operator("platform-owner", "configure_marketing_platforms")
    publisher = _operator("publisher-sem-config", "publish_marketing_announcements")

    client.force_login(publisher)
    assert client.post(PLATFORM_CONFIG, data={}, content_type="application/json").status_code == 403

    client.force_login(owner)
    response = client.post(PLATFORM_CONFIG, data={}, content_type="application/json")
    assert response.status_code == 409
    assert response.json()["code"] == "platform_config_cas_not_ready"


def test_setup_groups_matches_approved_role_matrix_and_keeps_dangerous_groups_empty():
    call_command("setup_groups", verbosity=0)

    expected = {
        "Marketing — Observador": {"view_marketing"},
        "Marketing — Editor": {
            "view_marketing",
            "edit_marketing_campaigns",
            "edit_marketing_templates",
            "preview_marketing_audience",
            "send_marketing_test",
        },
        "Marketing — Aprovador": {
            "view_marketing",
            "preview_marketing_audience",
            "approve_marketing_announcements",
        },
        "Marketing — Publisher": {
            "view_marketing",
            "preview_marketing_audience",
            "approve_marketing_announcements",
            "publish_marketing_announcements",
            "fire_marketing_campaigns",
            "retry_failed_marketing",
        },
        "Marketing — Platform Owner": {
            "view_marketing",
            "send_marketing_test",
            "configure_marketing_platforms",
            "reconcile_unknown_marketing",
        },
        "Marketing — Auditor/DPO": {"view_marketing", "audit_marketing"},
        "Marketing — Segurança/Ops": {"view_marketing", "freeze_marketing"},
    }

    for name, codenames in expected.items():
        group = Group.objects.get(name=name)
        actual = set(group.permissions.filter(content_type__app_label="shop").values_list("codename", flat=True))
        assert actual == codenames
        assert group.user_set.count() == 0

    gerente = Group.objects.get(name="Gerente")
    gerente_codenames = set(gerente.permissions.filter(content_type__app_label="shop").values_list("codename", flat=True))
    assert {
        "view_marketing",
        "edit_marketing_campaigns",
        "edit_marketing_templates",
        "preview_marketing_audience",
    }.issubset(gerente_codenames)
    assert "manage_campaigns" not in gerente_codenames
    assert "publish_marketing_announcements" not in gerente_codenames
    assert "fire_marketing_campaigns" not in gerente_codenames
    assert "send_marketing_test" not in gerente_codenames
    assert "configure_marketing_platforms" not in gerente_codenames
