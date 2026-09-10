"""Preparation print jobs: operator intent and relay delivery APIs."""

from __future__ import annotations

from dataclasses import replace

from django.urls import reverse
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage import station_trust
from shopman.backstage.api._production_mutations import (
    MutationAttemptSerializer,
    ProductionMutationValidationError,
    StrictMutationSerializer,
    validated_body,
)
from shopman.backstage.api.permissions import HasProductionCapability
from shopman.backstage.api.projections import projection_data
from shopman.backstage.models import PrintAgentCredential, PrintJob
from shopman.backstage.projections.production import (
    ProductionPrintDestinationProjection,
    build_production_weighing,
    resolve_production_access,
)
from shopman.backstage.services import print_jobs


class PrintJobAPIError(APIException):
    def __init__(self, error: print_jobs.PrintJobError):
        self.status_code = error.status_code
        self.detail = {"detail": error.message, "error": {"code": error.code}}


def _validated(serializer_class, data) -> dict:
    serializer = serializer_class(data=data)
    try:
        serializer.is_valid(raise_exception=True)
    except serializers.ValidationError as exc:
        raise ProductionMutationValidationError(exc.detail) from exc
    return dict(serializer.validated_data)


class ProductionWeighingPrintJobSerializer(MutationAttemptSerializer):
    selected_date = serializers.DateField()
    position = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    base_recipe = serializers.CharField(required=False, allow_blank=True, max_length=100, default="")
    mode = serializers.ChoiceField(choices=("blind", "explicit"))
    transport = serializers.ChoiceField(choices=("relay", "browser"))
    ticket_refs = serializers.ListField(
        child=serializers.CharField(max_length=80, allow_blank=False),
        allow_empty=False,
        max_length=print_jobs.MAX_LABELS_PER_JOB,
    )


class IdempotentJobActionSerializer(StrictMutationSerializer):
    idempotency_key = serializers.CharField(max_length=96, allow_blank=False, trim_whitespace=True)


class ReprintJobSerializer(IdempotentJobActionSerializer):
    transport = serializers.ChoiceField(choices=("relay", "browser"))


class ConfirmPrintJobSerializer(IdempotentJobActionSerializer):
    result = serializers.ChoiceField(choices=("confirmed", "incomplete", "not_printed", "failed"))
    detail = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class BrowserResultSerializer(IdempotentJobActionSerializer):
    result = serializers.ChoiceField(choices=("dialog_opened", "dialog_unavailable"))


class AgentTelemetrySerializer(StrictMutationSerializer):
    version = serializers.CharField(required=False, allow_blank=True, max_length=80, default="")
    build = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    queue = serializers.CharField(required=False, allow_blank=True, max_length=160, default="")
    health = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    # Accepted only for diagnostics. Authentication and routing always come
    # from the bearer credential, never from these self-reported values.
    agent_id = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    station_ref = serializers.CharField(required=False, allow_blank=True, max_length=80, default="")


class AgentAckSerializer(AgentTelemetrySerializer):
    status = serializers.ChoiceField(choices=("spooled", "failed", "uncertain"))
    spooler_job_id = serializers.CharField(required=False, allow_blank=True, max_length=160, default="")
    detail = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")
    payload_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$")
    lease_token = serializers.CharField(min_length=20, max_length=128, trim_whitespace=True)


def destination_projection(*, request) -> ProductionPrintDestinationProjection:
    destination = print_jobs.resolve_destination(station_ref=station_trust.station_ref(request))
    return ProductionPrintDestinationProjection(
        label=destination.label,
        status_label=destination.status_label,
        available=destination.available,
    )


def _weighing_for_request(request, body):
    access = resolve_production_access(
        request.user,
        trusted_station_ref=station_trust.station_ref(request),
        selected_date=body["selected_date"],
    )
    projection = build_production_weighing(
        selected_date=body["selected_date"],
        position_ref=body.get("position", ""),
        base_recipe=body.get("base_recipe", ""),
        access=access,
    )
    return replace(projection, print_destination=destination_projection(request=request))


def _raise_service(error: Exception):
    if isinstance(error, print_jobs.PrintJobError):
        raise PrintJobAPIError(error) from error
    raise error


class ProductionWeighingPrintJobCreateView(APIView):
    permission_classes = [HasProductionCapability]
    required_production_capability = "can_print_prep"

    def post(self, request):
        action_href = "/api/v1/backstage/production/weighing/print-jobs/"
        raw_date = request.data.get("selected_date") if hasattr(request.data, "get") else None
        try:
            from django.utils.dateparse import parse_date

            selected_date = parse_date(str(raw_date or ""))
        except (TypeError, ValueError):
            selected_date = None
        if selected_date is None:
            raise ProductionMutationValidationError({"selected_date": "Informe uma data válida."})
        body = validated_body(
            request,
            ProductionWeighingPrintJobSerializer,
            projection_kind="weighing",
            action_kind="print_labels",
            action_href=action_href,
            action_ref=lambda value: (
                f"print_weighing:{value['selected_date'].isoformat()}:"
                f"{value.get('position', '')}:{value.get('base_recipe', '')}"
            ),
            selected_date=selected_date,
        )
        projection = _weighing_for_request(request, body)
        current = projection_data(
            projection,
            freshness_context=("weighing", projection.selected_date, f"user:{request.user.pk}"),
        )
        if print_jobs.projection_digest(current["source_revision"]) != print_jobs.projection_digest(body["source_revision"]):
            raise PrintJobAPIError(
                print_jobs.PrintJobError(
                    "A pesagem mudou desde que a tela foi aberta. Atualize antes de imprimir.",
                    code="stale_projection",
                    status_code=409,
                )
            )
        try:
            job = print_jobs.create_job(
                projection=projection,
                mode=body["mode"],
                transport=body["transport"],
                ticket_refs=body["ticket_refs"],
                actor=request.user,
                station_ref=station_trust.station_ref(request),
                source_revision=body["source_revision"],
                idempotency_key=body["idempotency_key"],
            )
        except Exception as error:
            _raise_service(error)
        location = reverse("api-backstage-production-print-job", args=[job.ref])
        return Response(
            {"print_job": print_jobs.job_data(job, include_document=True)},
            status=201,
            headers={"Location": location},
        )


class OperatorPrintJobMixin:
    permission_classes = [HasProductionCapability]
    required_production_capability = "can_print_prep"

    def job(self, request, ref):
        job = PrintJob.objects.select_related("target_terminal").filter(ref=ref).first()
        if job is None:
            raise PrintJobAPIError(print_jobs.PrintJobError("Impressão não encontrada.", code="job_not_found", status_code=404))
        access = getattr(request, "production_access", None)
        trusted_ref = station_trust.station_ref(request)
        allowed = bool(
            getattr(access, "can_manage_all", False)
            or job.requested_by_id == request.user.pk
            or (
                trusted_ref
                and trusted_ref
                in {
                    job.requested_station_ref,
                    job.target_terminal.ref if job.target_terminal_id else "",
                }
            )
        )
        if not allowed:
            raise PrintJobAPIError(
                print_jobs.PrintJobError(
                    "Esta impressão pertence a outro operador ou estação.",
                    code="job_forbidden",
                    status_code=403,
                )
            )
        return job


class ProductionPrintJobStatusView(OperatorPrintJobMixin, APIView):
    def get(self, request, job_ref):
        job = print_jobs.reconcile_job_state(self.job(request, job_ref))
        return Response({"print_job": print_jobs.job_data(job, include_document=True)})


class ProductionPrintJobRetryView(OperatorPrintJobMixin, APIView):
    def post(self, request, job_ref):
        body = _validated(IdempotentJobActionSerializer, request.data)
        try:
            job = print_jobs.retry_job(job=self.job(request, job_ref), actor=request.user, idempotency_key=body["idempotency_key"])
        except Exception as error:
            _raise_service(error)
        return Response({"print_job": print_jobs.job_data(job, include_document=True)})


class ProductionPrintJobReprintView(OperatorPrintJobMixin, APIView):
    def post(self, request, job_ref):
        body = _validated(ReprintJobSerializer, request.data)
        try:
            job = print_jobs.reprint_job(
                job=self.job(request, job_ref),
                actor=request.user,
                station_ref=station_trust.station_ref(request),
                transport=body["transport"],
                idempotency_key=body["idempotency_key"],
            )
        except Exception as error:
            _raise_service(error)
        return Response({"print_job": print_jobs.job_data(job, include_document=True)})


class ProductionPrintJobConfirmView(OperatorPrintJobMixin, APIView):
    def post(self, request, job_ref):
        body = _validated(ConfirmPrintJobSerializer, request.data)
        try:
            job = print_jobs.confirm_job(
                job=self.job(request, job_ref),
                actor=request.user,
                result=body["result"],
                detail=body["detail"],
                idempotency_key=body["idempotency_key"],
            )
        except Exception as error:
            _raise_service(error)
        return Response({"print_job": print_jobs.job_data(job, include_document=True)})


class ProductionPrintJobBrowserResultView(OperatorPrintJobMixin, APIView):
    def post(self, request, job_ref):
        body = _validated(BrowserResultSerializer, request.data)
        try:
            job = print_jobs.record_browser_result(
                job=self.job(request, job_ref),
                actor=request.user,
                result=body["result"],
                idempotency_key=body["idempotency_key"],
            )
        except Exception as error:
            _raise_service(error)
        return Response({"print_job": print_jobs.job_data(job, include_document=True)})


class PrintAgentMixin:
    permission_classes = [AllowAny]
    authentication_classes = []

    def credential(self, request) -> PrintAgentCredential:
        header = str(request.headers.get("Authorization") or "")
        scheme, _, token = header.partition(" ")
        credential = PrintAgentCredential.authenticate(token if scheme.lower() == "bearer" else "")
        if credential is None:
            raise PrintJobAPIError(print_jobs.PrintJobError("Credencial do relay inválida.", code="invalid_agent_credential", status_code=401))
        remote_addr = request.META.get("REMOTE_ADDR")
        if remote_addr:
            credential.last_remote_addr = remote_addr
            credential.save(update_fields=("last_remote_addr",))
        return credential


class PrintAgentClaimView(PrintAgentMixin, APIView):
    def post(self, request):
        credential = self.credential(request)
        telemetry = _validated(AgentTelemetrySerializer, request.data)
        claimed = print_jobs.claim_next_job(credential=credential, telemetry=telemetry)
        if claimed is None:
            return Response(status=204)
        job, attempt, lease_token = claimed
        return Response({"job": print_jobs.claimed_job_data(job, attempt, lease_token)})


class PrintAgentAckView(PrintAgentMixin, APIView):
    def post(self, request, job_ref):
        credential = self.credential(request)
        body = _validated(AgentAckSerializer, request.data)
        try:
            job = print_jobs.acknowledge_job(
                credential=credential,
                job_ref=job_ref,
                status=body["status"],
                spooler_job_id=body["spooler_job_id"],
                detail=body["detail"],
                payload_sha256=body["payload_sha256"],
                lease_token=body["lease_token"],
                telemetry=body,
            )
        except Exception as error:
            _raise_service(error)
        return Response({"print_job": print_jobs.job_data(job)})
