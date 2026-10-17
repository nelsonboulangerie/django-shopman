"""WP-D5 — contract for which fields are editable vs locked (with admin-history audit).

- O turno de caixa (``cashman.Shift``) é INTEIRO read-only no Admin: a anotação
  gerencial é lançamento (``note``) no livro, não coluna editável (ADR-022).
- OperationTaskRun evidence + execution trail (who/when) is read-only (anti-fraud
  record captured by the app, never forged in the admin). A tela avulsa saiu na
  curadoria do WP-ADM-R1 (duplicata do inline), então o contrato passa a ser
  afirmado onde a edição de fato poderia acontecer: o inline da execução do
  checklist — que trava tudo, inclusive `notes`, e não deixa adicionar linha.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.test import RequestFactory
from django.urls import reverse
from shopman.cashman.models import Shift
from shopman.stockman.models import Batch

from shopman.backstage.admin.operation import OperationTaskRunInline
from shopman.backstage.models import OperationChecklistRun, POSTab


def _anonymous_request():
    request = RequestFactory().get("/admin/")
    request.user = AnonymousUser()
    return request


class _PermissionUser:
    def __init__(self, *permissions):
        self.permissions = set(permissions)

    def has_perm(self, permission):
        return permission in self.permissions


def test_cash_shift_is_locked_in_the_admin():
    """Turno fechado é imutável; correção é lançamento novo (``count_correction``/``note``)."""
    shift_admin = admin.site._registry[Shift]
    assert set(shift_admin.readonly_fields) >= {"terminal", "opened_by", "opened_at", "closed_at", "status"}


def test_operation_task_run_evidence_is_locked():
    checklist_admin = admin.site._registry[OperationChecklistRun]
    assert OperationTaskRunInline in checklist_admin.inlines, (
        "sem o inline, a execução de tarefa não aparece em lugar nenhum"
    )

    locked = set(OperationTaskRunInline.readonly_fields)
    for field in (
        "evidence_text",
        "evidence_number",
        "evidence_data",
        "executed_by",
        "executed_at",
        "supervised_by",
        "supervised_at",
    ):
        assert field in locked, f"{field} deveria ser read-only (registro anti-fraude)"


def test_operation_checklist_run_admin_is_an_audit_trail():
    checklist_admin = admin.site._registry[OperationChecklistRun]
    request = _anonymous_request()

    assert checklist_admin.actions == ()
    assert not hasattr(checklist_admin, "complete_selected")
    assert checklist_admin.has_add_permission(request) is False
    assert checklist_admin.has_change_permission(request) is False
    assert checklist_admin.has_delete_permission(request) is False
    assert set(checklist_admin.readonly_fields) >= {
        "template",
        "business_date",
        "shift_ref",
        "status",
        "started_by",
        "started_at",
        "completed_by",
        "completed_at",
        "notes",
        "context",
    }


def test_pos_tabs_are_readonly_in_admin_and_not_owned_by_cash_operator_permission():
    tab_admin = admin.site._registry[POSTab]
    request = RequestFactory().get("/admin/backstage/postab/")
    request.user = _PermissionUser("cashman.operate_pos")

    assert tab_admin.has_view_permission(request) is False
    assert tab_admin.has_add_permission(request) is False
    assert tab_admin.has_change_permission(request) is False
    assert tab_admin.has_delete_permission(request) is False
    assert set(tab_admin.readonly_fields) == {"ref", "label", "is_active", "created_at", "updated_at"}

    request.user = _PermissionUser("backstage.view_postab")
    assert tab_admin.has_view_permission(request) is True


@pytest.mark.django_db
def test_cash_operator_cannot_reach_pos_tab_admin_by_direct_url(client):
    from shopman.shop.models import Shop

    Shop.objects.create(name="Loja")
    operator = get_user_model().objects.create_user("cash-operator", password="x", is_staff=True)
    operator.user_permissions.add(Permission.objects.get(codename="operate_pos", content_type__app_label="cashman"))
    client.force_login(operator)

    assert client.get(reverse("admin:backstage_postab_changelist")).status_code == 403
    assert client.post(reverse("admin:backstage_postab_add"), {"ref": "00000001"}).status_code == 403


def test_batch_quality_fact_is_locked_in_the_admin():
    """Correção de QC não pode contornar preço, canais e notificações."""
    batch_admin = admin.site._registry[Batch]
    assert set(batch_admin.readonly_fields) >= {
        "quality_grade_ref",
        "nonconformity_percent",
        "nonconformity_reason",
    }
