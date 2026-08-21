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

from django.contrib import admin
from shopman.cashman.models import Shift

from shopman.backstage.admin.operation import OperationTaskRunInline
from shopman.backstage.models import OperationChecklistRun


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
