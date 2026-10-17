"""Daily operational-checklist API for the Gestor surface."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data, read_data
from shopman.backstage.models import (
    OperationChecklistRun,
    OperationChecklistTemplate,
    OperationRunStatus,
    OperationTaskRun,
)
from shopman.backstage.projections.operation_checklists import (
    build_operation_checklist_board,
)
from shopman.backstage.services.operations import (
    OperationChecklistError,
    complete_checklist_run,
    complete_task_run,
    start_checklist_run,
    supervise_task_run,
)


class ChecklistDateSerializer(serializers.Serializer):
    business_date = serializers.DateField(required=False, default=timezone.localdate)


class ChecklistStartSerializer(ChecklistDateSerializer):
    template_ref = serializers.SlugField(max_length=80)
    shift_ref = serializers.CharField(required=False, allow_blank=True, max_length=50, default="")


class ChecklistTaskCompleteSerializer(serializers.Serializer):
    evidence_text = serializers.CharField(required=False, allow_blank=True, default="")
    evidence_number = serializers.DecimalField(required=False, allow_null=True, max_digits=12, decimal_places=3)
    evidence_data = serializers.JSONField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ChecklistSuperviseSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True, default="")


def _board_response(*, business_date, user, status_code=status.HTTP_200_OK):
    board = build_operation_checklist_board(business_date=business_date, user=user)
    return Response(read_data(checklists=projection_data(board)), status=status_code)


def _domain_error(exc: OperationChecklistError) -> Response:
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _require_open(run: OperationChecklistRun) -> Response | None:
    if run.status == OperationRunStatus.OPEN:
        return None
    return Response(
        {
            "detail": "Esta rotina já foi encerrada.",
            "error": {"code": "checklist_run_closed"},
        },
        status=status.HTTP_409_CONFLICT,
    )


class OperationChecklistBoardView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.perform_operation_task"

    def get(self, request):
        query = ChecklistDateSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        return _board_response(business_date=query.validated_data["business_date"], user=request.user)


class OperationChecklistStartView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.perform_operation_task"

    def post(self, request):
        body = ChecklistStartSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        template = get_object_or_404(OperationChecklistTemplate, ref=data["template_ref"], is_active=True)
        try:
            start_checklist_run(
                template=template,
                business_date=data["business_date"],
                shift_ref=data["shift_ref"],
                user=request.user,
                context={"surface": "orders-nuxt"},
            )
        except OperationChecklistError as exc:
            return _domain_error(exc)
        return _board_response(
            business_date=data["business_date"],
            user=request.user,
            status_code=status.HTTP_201_CREATED,
        )


class OperationTaskCompleteView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.perform_operation_task"

    def post(self, request, run_id: int, task_id: int):
        body = ChecklistTaskCompleteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        task = get_object_or_404(
            OperationTaskRun.objects.select_related("checklist_run"),
            pk=task_id,
            checklist_run_id=run_id,
        )
        if closed := _require_open(task.checklist_run):
            return closed
        try:
            complete_task_run(task, user=request.user, **body.validated_data)
        except OperationChecklistError as exc:
            return _domain_error(exc)
        return _board_response(business_date=task.checklist_run.business_date, user=request.user)


class OperationTaskSuperviseView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.supervise_operation_task"

    def post(self, request, run_id: int, task_id: int):
        body = ChecklistSuperviseSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        task = get_object_or_404(
            OperationTaskRun.objects.select_related("checklist_run"),
            pk=task_id,
            checklist_run_id=run_id,
        )
        if closed := _require_open(task.checklist_run):
            return closed
        try:
            supervise_task_run(task, user=request.user, **body.validated_data)
        except OperationChecklistError as exc:
            return _domain_error(exc)
        return _board_response(business_date=task.checklist_run.business_date, user=request.user)


class OperationChecklistCompleteView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.perform_operation_task"

    def post(self, request, run_id: int):
        run = get_object_or_404(OperationChecklistRun, pk=run_id)
        if closed := _require_open(run):
            return closed
        try:
            complete_checklist_run(run, user=request.user)
        except OperationChecklistError as exc:
            return _domain_error(exc)
        return _board_response(business_date=run.business_date, user=request.user)
