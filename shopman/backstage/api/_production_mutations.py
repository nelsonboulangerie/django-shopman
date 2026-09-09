"""Closed request contracts for production mutations.

Operational writes must never inherit Python truthiness (``bool("false")``),
ignore misspelled fields, or mutate a WorkOrder without the revision displayed
to the operator.  These serializers are the only JSON boundary for production
actions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException

from shopman.backstage.api.production_freshness import (
    projection_revision_scope,
    validate_action_proof,
    validate_projection_metadata,
)


@dataclass(frozen=True)
class ProductionMutationCurrent:
    """Minimal authoritative WorkOrder state returned after every mutation."""

    pk: int
    ref: str
    status: str
    rev: int


@dataclass(frozen=True)
class ProductionPlanMutationSuccess:
    ok: bool
    result: str
    output_sku: str
    wo_ref: str
    quantity: str
    current: ProductionMutationCurrent | None


@dataclass(frozen=True)
class ProductionWorkOrderMutationSuccess:
    ok: bool
    wo_ref: str
    quantity: str
    current: ProductionMutationCurrent | None


@dataclass(frozen=True)
class ProductionAdvanceStepMutationSuccess:
    ok: bool
    wo_id: int
    step_index: int
    current: ProductionMutationCurrent | None


@dataclass(frozen=True)
class ProductionVoidMutationSuccess:
    ok: bool
    wo_ref: str
    current: ProductionMutationCurrent | None


@dataclass(frozen=True)
class ProductionOvenArmMutationSuccess:
    ok: bool
    run_id: int
    run_status: str
    current: ProductionMutationCurrent | None


@dataclass(frozen=True)
class ProductionOvenConcludeMutationSuccess:
    ok: bool
    measured: bool
    run_id: int
    run_status: str
    current: ProductionMutationCurrent | None


@dataclass(frozen=True)
class AlertAckMutationSuccess:
    ok: bool
    pk: int


@dataclass(frozen=True)
class ProductionValidationIssue:
    field: str
    code: str
    message: str


@dataclass(frozen=True)
class ProductionValidationErrorBody:
    code: Literal["validation_error"]
    issues: tuple[ProductionValidationIssue, ...]


@dataclass(frozen=True)
class ProductionValidationErrorEnvelope:
    detail: str
    error: ProductionValidationErrorBody


@dataclass(frozen=True)
class ProductionConflictRecovery:
    action: Literal["refresh", "retry"]
    label: str


@dataclass(frozen=True)
class ProductionConflictErrorBody:
    code: Literal["conflict", "oven_run_missing", "quick_finish_incomplete"]
    sent_rev: int | None
    current_rev: int | None
    current: ProductionMutationCurrent | None
    recovery: ProductionConflictRecovery


@dataclass(frozen=True)
class ProductionConflictErrorEnvelope:
    detail: str
    error: ProductionConflictErrorBody


@dataclass(frozen=True)
class ProductionStaleProjectionErrorBody:
    code: Literal["stale_projection"]
    age_seconds: int | None
    sent_rev: int | None
    current_rev: int | None
    current: ProductionMutationCurrent | None
    recovery: ProductionConflictRecovery


@dataclass(frozen=True)
class ProductionStaleProjectionErrorEnvelope:
    detail: str
    error: ProductionStaleProjectionErrorBody


@dataclass(frozen=True)
class ProductionForbiddenRecovery:
    action: Literal["request_access"]
    label: str


@dataclass(frozen=True)
class ProductionForbiddenErrorBody:
    code: Literal["forbidden"]
    capability: str
    recovery: ProductionForbiddenRecovery


@dataclass(frozen=True)
class ProductionForbiddenErrorEnvelope:
    detail: str
    error: ProductionForbiddenErrorBody


@dataclass(frozen=True)
class ProductionNotFoundErrorBody:
    code: Literal["not_found"]
    resource: str
    identifier: str


@dataclass(frozen=True)
class ProductionNotFoundErrorEnvelope:
    detail: str
    error: ProductionNotFoundErrorBody


@dataclass(frozen=True)
class ProductionShortagePossibility:
    kind: Literal["retry", "force"]
    label: str
    enabled: bool
    proof: str


@dataclass(frozen=True)
class ProductionMaterialShortageItem:
    sku: str
    needed: str
    available: str
    shortage: str


@dataclass(frozen=True)
class ProductionMaterialShortageErrorBody:
    code: Literal["material_shortage"]
    work_order_ref: str
    idempotency_key: str
    possibilities: tuple[ProductionShortagePossibility, ...]
    missing: tuple[ProductionMaterialShortageItem, ...]


@dataclass(frozen=True)
class ProductionMaterialShortageErrorEnvelope:
    detail: str
    error: ProductionMaterialShortageErrorBody


@dataclass(frozen=True)
class ProductionOrderShortageErrorBody:
    code: Literal["order_shortage"]
    work_order_ref: str
    idempotency_key: str
    possibilities: tuple[ProductionShortagePossibility, ...]
    required: str
    requested: str
    order_refs: tuple[str, ...]


@dataclass(frozen=True)
class ProductionOrderShortageErrorEnvelope:
    detail: str
    error: ProductionOrderShortageErrorBody


def _validation_issues(detail, *, path: str = "") -> list[dict[str, str]]:
    """Flatten DRF's nested ErrorDetail tree into a stable wire contract."""
    if isinstance(detail, dict):
        issues: list[dict[str, str]] = []
        for key, value in detail.items():
            if key == "non_field_errors" and path:
                child = path
            else:
                child = f"{path}.{key}" if path else str(key)
            issues.extend(_validation_issues(value, path=child))
        return issues
    if isinstance(detail, (list, tuple)):
        issues = []
        for index, value in enumerate(detail):
            child = f"{path}.{index}" if path and isinstance(value, (dict, list, tuple)) else path
            issues.extend(_validation_issues(value, path=child))
        return issues
    return [
        {
            "field": path or "non_field_errors",
            "code": str(getattr(detail, "code", "invalid")),
            "message": str(detail),
        }
    ]


class ProductionMutationValidationError(APIException):
    status_code = 400
    default_code = "validation_error"

    def __init__(self, detail) -> None:
        issues = _validation_issues(detail)
        super().__init__(
            {
                "detail": "Corrija os campos indicados e tente novamente.",
                "error": {
                    "code": "validation_error",
                    "issues": issues,
                },
            }
        )


class ProductionProjectionExpiredError(APIException):
    status_code = 409
    default_code = "stale_projection"

    def __init__(self, detail) -> None:
        # APIException's default normalizer stringifies every scalar. Keep the
        # typed stale envelope intact (integer age/revisions and nullable state).
        self.detail = detail


class StrictMutationSerializer(serializers.Serializer):
    """Reject undeclared input instead of silently discarding it."""

    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            raise serializers.ValidationError({"non_field_errors": ["Envie um objeto JSON."]})
        unknown = sorted(set(data.keys()) - set(self.fields))
        if unknown:
            raise serializers.ValidationError({field: ["Campo desconhecido."] for field in unknown})
        return super().to_internal_value(data)


class MutationAttemptSerializer(StrictMutationSerializer):
    idempotency_key = serializers.CharField(
        max_length=96,
        allow_blank=False,
        trim_whitespace=True,
    )
    projection_generated_at = serializers.DateTimeField()
    source_revision = serializers.CharField(
        allow_blank=False,
        max_length=256,
        trim_whitespace=True,
    )
    fresh_until = serializers.DateTimeField()
    contract_version = serializers.IntegerField(min_value=1)
    action_ref = serializers.CharField(allow_blank=False, max_length=300)
    action_proof = serializers.CharField(allow_blank=False, max_length=2048)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        freshness_fields = {
            "projection_generated_at",
            "source_revision",
            "fresh_until",
            "contract_version",
        }
        assert freshness_fields <= attrs.keys()
        errors = validate_projection_metadata(
            projection_generated_at=attrs["projection_generated_at"],
            source_revision=attrs["source_revision"],
            fresh_until=attrs["fresh_until"],
            contract_version=attrs["contract_version"],
            now=timezone.now(),
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class ExistingWorkOrderMutationSerializer(MutationAttemptSerializer):
    expected_rev = serializers.IntegerField(min_value=0)


class ProductionPlanMutationSerializer(MutationAttemptSerializer):
    override_proof = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=4096,
    )
    recipe_id = serializers.IntegerField(min_value=1)
    work_order_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    target_date = serializers.DateField()
    position_ref = serializers.CharField(allow_blank=False, max_length=100)
    operator_ref = serializers.CharField(required=False, allow_blank=True, max_length=100)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    source = serializers.ChoiceField(
        choices=("manual", "suggested"),
        required=False,
        default="manual",
    )
    force = serializers.BooleanField(required=False, default=False)
    # Null means the client observed an empty cell.  When multiple WOs exist,
    # ``work_order_id`` must identify the exact target and this is its revision.
    expected_rev = serializers.IntegerField(allow_null=True, min_value=0)


class ProductionStartMutationSerializer(ExistingWorkOrderMutationSerializer):
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    position_id = serializers.CharField(required=False, allow_blank=True, max_length=100)
    operator_ref = serializers.CharField(required=False, allow_blank=True, max_length=100)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class ProductionPartitionGroupSerializer(StrictMutationSerializer):
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    quality_grade_ref = serializers.CharField(required=False, allow_blank=True, max_length=100)
    quality_defect_ref = serializers.CharField(required=False, allow_blank=True, max_length=100)
    loss = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("loss") and not str(attrs.get("quality_defect_ref") or "").strip():
            raise serializers.ValidationError({"quality_defect_ref": "Informe o motivo da perda declarada."})
        return attrs


class ProductionFinishMutationSerializer(ExistingWorkOrderMutationSerializer):
    override_proof = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=4096,
    )
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    force = serializers.BooleanField(required=False, default=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    yield_deviation_confirmed = serializers.BooleanField(required=False, default=False)
    yield_deviation_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
    )
    quality = serializers.CharField(required=False, allow_blank=True, max_length=100)
    partition = ProductionPartitionGroupSerializer(
        many=True,
        required=False,
        allow_empty=False,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        partition = attrs.get("partition")
        quality = str(attrs.get("quality") or "").strip()
        if partition is not None and quality:
            raise serializers.ValidationError({"quality": "Informe quality ou partition, nunca os dois."})
        if partition is not None:
            partition_total = sum(
                (group["quantity"] for group in partition),
                Decimal("0"),
            )
            if partition_total != attrs["quantity"]:
                raise serializers.ValidationError(
                    {"partition": ("A soma dos grupos deve ser exatamente igual à quantidade total informada.")}
                )
        return attrs


class ProductionAdvanceStepMutationSerializer(ExistingWorkOrderMutationSerializer):
    pass


class ProductionQuickFinishMutationSerializer(MutationAttemptSerializer):
    override_proof = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=4096,
    )
    recipe_id = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    position_id = serializers.CharField(required=False, allow_blank=True, max_length=100)
    force = serializers.BooleanField(required=False, default=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    partition = ProductionPartitionGroupSerializer(
        many=True,
        required=False,
        allow_empty=False,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        partition = attrs.get("partition")
        if partition is not None:
            partition_total = sum(
                (group["quantity"] for group in partition),
                Decimal("0"),
            )
            if partition_total != attrs["quantity"]:
                raise serializers.ValidationError(
                    {"partition": ("A soma dos grupos deve ser exatamente igual à quantidade total informada.")}
                )
        return attrs


class ProductionVoidMutationSerializer(ExistingWorkOrderMutationSerializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True, max_length=500)


class ProductionOvenArmMutationSerializer(ExistingWorkOrderMutationSerializer):
    planned_seconds = serializers.IntegerField(min_value=1, max_value=86_400)
    operator_ref = serializers.CharField(required=False, allow_blank=True, max_length=100)


class ProductionOvenConcludeMutationSerializer(ExistingWorkOrderMutationSerializer):
    pass


class AlertAckMutationSerializer(ExistingWorkOrderMutationSerializer):
    """Closed request contract for one projected alert acknowledgement."""

    pass


@dataclass(frozen=True)
class ProductionActionSpec:
    """One generated client operation backed by the serializer used by DRF."""

    function_name: str
    href: str
    request_name: str
    serializer: type[StrictMutationSerializer]
    response: type
    path_parameter: str | None = None


PRODUCTION_ACTION_SPECS = (
    ProductionActionSpec(
        "planProduction",
        "/api/v1/backstage/production/plan/",
        "ProductionPlanMutationRequest",
        ProductionPlanMutationSerializer,
        ProductionPlanMutationSuccess,
    ),
    ProductionActionSpec(
        "startProductionWorkOrder",
        "/api/v1/backstage/production/{workOrderId}/start/",
        "ProductionStartMutationRequest",
        ProductionStartMutationSerializer,
        ProductionWorkOrderMutationSuccess,
        "workOrderId",
    ),
    ProductionActionSpec(
        "finishProductionWorkOrder",
        "/api/v1/backstage/production/{workOrderId}/finish/",
        "ProductionFinishMutationRequest",
        ProductionFinishMutationSerializer,
        ProductionWorkOrderMutationSuccess,
        "workOrderId",
    ),
    ProductionActionSpec(
        "advanceProductionWorkOrderStep",
        "/api/v1/backstage/production/{workOrderId}/advance-step/",
        "ProductionAdvanceStepMutationRequest",
        ProductionAdvanceStepMutationSerializer,
        ProductionAdvanceStepMutationSuccess,
        "workOrderId",
    ),
    ProductionActionSpec(
        "quickFinishProduction",
        "/api/v1/backstage/production/quick-finish/",
        "ProductionQuickFinishMutationRequest",
        ProductionQuickFinishMutationSerializer,
        ProductionWorkOrderMutationSuccess,
    ),
    ProductionActionSpec(
        "voidProductionWorkOrder",
        "/api/v1/backstage/production/{workOrderId}/void/",
        "ProductionVoidMutationRequest",
        ProductionVoidMutationSerializer,
        ProductionVoidMutationSuccess,
        "workOrderId",
    ),
    ProductionActionSpec(
        "armProductionOven",
        "/api/v1/backstage/production/{workOrderId}/oven/arm/",
        "ProductionOvenArmMutationRequest",
        ProductionOvenArmMutationSerializer,
        ProductionOvenArmMutationSuccess,
        "workOrderId",
    ),
    ProductionActionSpec(
        "concludeProductionOven",
        "/api/v1/backstage/production/{workOrderId}/oven/conclude/",
        "ProductionOvenConcludeMutationRequest",
        ProductionOvenConcludeMutationSerializer,
        ProductionOvenConcludeMutationSuccess,
        "workOrderId",
    ),
    ProductionActionSpec(
        "acknowledgeOperatorAlert",
        "/api/v1/backstage/alerts/{alertId}/ack/",
        "AlertAckMutationRequest",
        AlertAckMutationSerializer,
        AlertAckMutationSuccess,
        "alertId",
    ),
)

PRODUCTION_REQUEST_SERIALIZERS = (
    ("ProductionPartitionGroupRequest", ProductionPartitionGroupSerializer),
    *((spec.request_name, spec.serializer) for spec in PRODUCTION_ACTION_SPECS),
)

PRODUCTION_MUTATION_DATACLASSES = (
    ProductionMutationCurrent,
    ProductionPlanMutationSuccess,
    ProductionWorkOrderMutationSuccess,
    ProductionAdvanceStepMutationSuccess,
    ProductionVoidMutationSuccess,
    ProductionOvenArmMutationSuccess,
    ProductionOvenConcludeMutationSuccess,
    AlertAckMutationSuccess,
    ProductionValidationIssue,
    ProductionValidationErrorBody,
    ProductionValidationErrorEnvelope,
    ProductionConflictRecovery,
    ProductionConflictErrorBody,
    ProductionConflictErrorEnvelope,
    ProductionStaleProjectionErrorBody,
    ProductionStaleProjectionErrorEnvelope,
    ProductionForbiddenRecovery,
    ProductionForbiddenErrorBody,
    ProductionForbiddenErrorEnvelope,
    ProductionNotFoundErrorBody,
    ProductionNotFoundErrorEnvelope,
    ProductionShortagePossibility,
    ProductionMaterialShortageItem,
    ProductionMaterialShortageErrorBody,
    ProductionMaterialShortageErrorEnvelope,
    ProductionOrderShortageErrorBody,
    ProductionOrderShortageErrorEnvelope,
)


def validated_body(
    request,
    serializer_class: type[StrictMutationSerializer],
    *,
    projection_kind: str | tuple[str, ...],
    action_kind: str,
    action_href: str,
    action_ref: str | Callable[[dict], str],
    selected_date=None,
    work_order_id: int | None = None,
) -> dict:
    serializer = serializer_class(data=request.data)
    try:
        serializer.is_valid(raise_exception=True)
    except serializers.ValidationError as exc:
        raise ProductionMutationValidationError(exc.detail) from exc
    body = dict(serializer.validated_data)
    projection_kinds = (projection_kind,) if isinstance(projection_kind, str) else projection_kind
    if selected_date is None and work_order_id is None and "board" in projection_kinds:
        selected_date = body.get("target_date")
    if selected_date is None and work_order_id is None and "qc" in projection_kinds:
        selected_date = timezone.localdate()

    actual_scope = projection_revision_scope(body["source_revision"])
    expected_subject = f"user:{request.user.pk}"
    selected_date_ref = selected_date.isoformat() if selected_date else ""
    scope_matches = bool(
        actual_scope
        and actual_scope[0] in projection_kinds
        and actual_scope[1]
        and actual_scope[2] == expected_subject
        and (not selected_date_ref or actual_scope[1] == selected_date_ref)
    )
    if not scope_matches:
        raise ProductionMutationValidationError(
            {
                "source_revision": (
                    "A projeção não pertence a esta ação, data ou operador. Atualize o painel antes de agir."
                )
            }
        )
    assert actual_scope is not None
    expected_action_ref = action_ref(body) if callable(action_ref) else action_ref
    if body["action_ref"] != expected_action_ref:
        raise ProductionMutationValidationError({"action_ref": "A referência não corresponde à ação solicitada."})
    proof_errors = validate_action_proof(
        action_proof=body["action_proof"],
        action_ref=expected_action_ref,
        action_kind=action_kind,
        href=action_href,
        expected_rev=body.get("expected_rev"),
        source_revision=body["source_revision"],
        projection_generated_at=body["projection_generated_at"],
        fresh_until=body["fresh_until"],
        contract_version=body["contract_version"],
        projection_kind=actual_scope[0],
        selected_date=actual_scope[1],
        subject_ref=actual_scope[2],
    )
    if proof_errors:
        raise ProductionMutationValidationError(proof_errors)

    # Target discovery happens only after a cryptographically valid projected
    # action. Invalid direct URLs therefore cannot enumerate whether a hidden
    # WorkOrder exists or on which date it lives.
    if work_order_id is not None:
        from shopman.craftsman.models import WorkOrder

        target_date = WorkOrder.objects.filter(pk=work_order_id).values_list("target_date", flat=True).first()
        if target_date is not None and target_date.isoformat() != actual_scope[1]:
            raise ProductionMutationValidationError(
                {
                    "action_proof": (
                        "A ação não pertence a esta projeção, alvo ou data. Atualize o painel antes de agir."
                    )
                }
            )

    # Freshness prevents a new mutation from an old screen, but must not make
    # a response-loss retry impossible after the exact attempt has committed.
    # The service still validates the frozen actor and payload before replaying
    # the result; this flag only lets that durable receipt reach the service.
    from shopman.backstage.services.production import has_committed_mutation_attempt

    committed_replay = has_committed_mutation_attempt(
        action_kind=action_kind,
        work_order_id=work_order_id,
        idempotency_key=body["idempotency_key"],
        body=body,
    )
    fresh_until = body.get("fresh_until")
    if fresh_until is not None and timezone.now() >= fresh_until and not committed_replay:
        generated_at = body.get("projection_generated_at")
        age_seconds = max(0, int((timezone.now() - generated_at).total_seconds())) if generated_at is not None else None
        raise ProductionProjectionExpiredError(
            detail={
                "detail": "A projeção de produção expirou. Atualize o painel antes de agir.",
                "error": {
                    "code": "stale_projection",
                    "age_seconds": age_seconds,
                    "sent_rev": body.get("expected_rev"),
                    "current_rev": None,
                    "current": None,
                    "recovery": {
                        "action": "refresh",
                        "label": "Atualizar painel",
                    },
                },
            },
        )
    body["_committed_replay"] = committed_replay
    return body
