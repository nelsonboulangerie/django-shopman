"""Operator projection for the daily operational checklists."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch

from shopman.backstage.models import (
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperationTaskRun,
)


@dataclass(frozen=True)
class OperationTaskProjection:
    id: int
    ref: str
    title: str
    description: str
    area: str
    area_label: str
    status: str
    status_label: str
    required: bool
    evidence_required: str
    evidence_required_label: str
    evidence_text: str
    evidence_number: str | None
    evidence_data: dict
    notes: str
    requires_supervision: bool
    supervised: bool
    executed_by: str
    supervised_by: str


@dataclass(frozen=True)
class OperationRunProjection:
    id: int
    shift_ref: str
    status: str
    status_label: str
    started_by: str
    completed_by: str
    progress_percent: int
    tasks: tuple[OperationTaskProjection, ...]


@dataclass(frozen=True)
class OperationTemplateProjection:
    id: int
    ref: str
    title: str
    description: str
    moment: str
    moment_label: str
    runs: tuple[OperationRunProjection, ...]


@dataclass(frozen=True)
class OperationChecklistBoardProjection:
    business_date: str
    can_supervise: bool
    templates: tuple[OperationTemplateProjection, ...]


def _person(user) -> str:
    if user is None:
        return ""
    name = user.get_full_name().strip()
    return name or user.get_username()


def _number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _task_projection(task: OperationTaskRun) -> OperationTaskProjection:
    template = task.template
    return OperationTaskProjection(
        id=task.pk,
        ref=template.ref,
        title=template.title,
        description=template.description,
        area=template.area,
        area_label=template.get_area_display(),
        status=task.status,
        status_label=task.get_status_display(),
        required=task.is_required,
        evidence_required=task.evidence_required,
        evidence_required_label=task.get_evidence_required_display(),
        evidence_text=task.evidence_text,
        evidence_number=_number(task.evidence_number),
        evidence_data=task.evidence_data,
        notes=task.notes,
        requires_supervision=task.requires_supervision,
        supervised=task.is_supervised,
        executed_by=_person(task.executed_by),
        supervised_by=_person(task.supervised_by),
    )


def _run_projection(run: OperationChecklistRun) -> OperationRunProjection:
    tasks = tuple(_task_projection(task) for task in run.task_runs.all())
    done = sum(task.status == "done" for task in tasks)
    return OperationRunProjection(
        id=run.pk,
        shift_ref=run.shift_ref,
        status=run.status,
        status_label=run.get_status_display(),
        started_by=_person(run.started_by),
        completed_by=_person(run.completed_by),
        progress_percent=round((done / len(tasks)) * 100) if tasks else 0,
        tasks=tasks,
    )


def build_operation_checklist_board(*, business_date: date, user) -> OperationChecklistBoardProjection:
    task_runs = OperationTaskRun.objects.select_related("template", "executed_by", "supervised_by").order_by(
        "template__sort_order", "template__title"
    )
    runs = (
        OperationChecklistRun.objects.filter(business_date=business_date)
        .select_related("started_by", "completed_by")
        .prefetch_related(Prefetch("task_runs", queryset=task_runs))
    )
    templates = OperationChecklistTemplate.objects.filter(is_active=True).prefetch_related(
        Prefetch("runs", queryset=runs)
    )
    return OperationChecklistBoardProjection(
        business_date=business_date.isoformat(),
        can_supervise=user.has_perm("backstage.supervise_operation_task"),
        templates=tuple(
            OperationTemplateProjection(
                id=template.pk,
                ref=template.ref,
                title=template.title,
                description=template.description,
                moment=template.moment,
                moment_label=template.get_moment_display(),
                runs=tuple(_run_projection(run) for run in template.runs.all()),
            )
            for template in templates
        ),
    )
