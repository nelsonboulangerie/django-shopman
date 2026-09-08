"""Closed request contracts for production mutations.

Operational writes must never inherit Python truthiness (``bool("false")``),
ignore misspelled fields, or mutate a WorkOrder without the revision displayed
to the operator.  These serializers are the only JSON boundary for production
actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from rest_framework import serializers
from rest_framework.exceptions import APIException


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
    current: ProductionMutationCurrent | None


@dataclass(frozen=True)
class ProductionOvenConcludeMutationSuccess:
    ok: bool
    measured: bool
    current: ProductionMutationCurrent | None


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
    action: Literal["refresh"]
    label: str


@dataclass(frozen=True)
class ProductionConflictErrorBody:
    code: Literal["conflict", "state_conflict"]
    sent_rev: int | None
    current_rev: int | None
    current: ProductionMutationCurrent | None
    recovery: ProductionConflictRecovery


@dataclass(frozen=True)
class ProductionConflictErrorEnvelope:
    detail: str
    error: ProductionConflictErrorBody


@dataclass(frozen=True)
class ProductionShortagePossibility:
    kind: Literal["retry", "force"]
    label: str
    enabled: bool


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


class StrictMutationSerializer(serializers.Serializer):
    """Reject undeclared input instead of silently discarding it."""

    def to_internal_value(self, data):
        if not hasattr(data, "keys"):
            raise serializers.ValidationError({"non_field_errors": ["Envie um objeto JSON."]})
        unknown = sorted(set(data.keys()) - set(self.fields))
        if unknown:
            raise serializers.ValidationError(
                {field: ["Campo desconhecido."] for field in unknown}
            )
        return super().to_internal_value(data)


class MutationAttemptSerializer(StrictMutationSerializer):
    idempotency_key = serializers.CharField(
        max_length=96,
        allow_blank=False,
        trim_whitespace=True,
    )


class ExistingWorkOrderMutationSerializer(MutationAttemptSerializer):
    expected_rev = serializers.IntegerField(min_value=0)


class ProductionPlanMutationSerializer(MutationAttemptSerializer):
    recipe_id = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    target_date = serializers.DateField()
    position_ref = serializers.CharField(required=False, allow_blank=True, max_length=100)
    operator_ref = serializers.CharField(required=False, allow_blank=True, max_length=100)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    source = serializers.ChoiceField(
        choices=("manual", "suggested"),
        required=False,
        default="manual",
    )
    force = serializers.BooleanField(required=False, default=False)
    # Aggregate/cell revision.  Null means the client observed that this cell
    # had no planned WorkOrder; an integer names the sole target it observed.
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


class ProductionFinishMutationSerializer(ExistingWorkOrderMutationSerializer):
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    force = serializers.BooleanField(required=False, default=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    quality = serializers.CharField(required=False, allow_blank=True, max_length=100)
    partition = ProductionPartitionGroupSerializer(many=True, required=False)


class ProductionAdvanceStepMutationSerializer(ExistingWorkOrderMutationSerializer):
    pass


class ProductionQuickFinishMutationSerializer(MutationAttemptSerializer):
    recipe_id = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    position_id = serializers.CharField(required=False, allow_blank=True, max_length=100)
    force = serializers.BooleanField(required=False, default=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
    partition = ProductionPartitionGroupSerializer(many=True, required=False)


class ProductionVoidMutationSerializer(ExistingWorkOrderMutationSerializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True, max_length=500)


class ProductionOvenArmMutationSerializer(ExistingWorkOrderMutationSerializer):
    planned_seconds = serializers.IntegerField(min_value=1, max_value=86_400)
    operator_ref = serializers.CharField(required=False, allow_blank=True, max_length=100)


class ProductionOvenConcludeMutationSerializer(ExistingWorkOrderMutationSerializer):
    pass


@dataclass(frozen=True)
class ProductionActionSpec:
    """One generated client operation backed by the serializer used by DRF."""

    function_name: str
    href: str
    request_name: str
    serializer: type[StrictMutationSerializer]
    response: type
    work_order_path: bool = False


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
        True,
    ),
    ProductionActionSpec(
        "finishProductionWorkOrder",
        "/api/v1/backstage/production/{workOrderId}/finish/",
        "ProductionFinishMutationRequest",
        ProductionFinishMutationSerializer,
        ProductionWorkOrderMutationSuccess,
        True,
    ),
    ProductionActionSpec(
        "advanceProductionWorkOrderStep",
        "/api/v1/backstage/production/{workOrderId}/advance-step/",
        "ProductionAdvanceStepMutationRequest",
        ProductionAdvanceStepMutationSerializer,
        ProductionAdvanceStepMutationSuccess,
        True,
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
        True,
    ),
    ProductionActionSpec(
        "armProductionOven",
        "/api/v1/backstage/production/{workOrderId}/oven/arm/",
        "ProductionOvenArmMutationRequest",
        ProductionOvenArmMutationSerializer,
        ProductionOvenArmMutationSuccess,
        True,
    ),
    ProductionActionSpec(
        "concludeProductionOven",
        "/api/v1/backstage/production/{workOrderId}/oven/conclude/",
        "ProductionOvenConcludeMutationRequest",
        ProductionOvenConcludeMutationSerializer,
        ProductionOvenConcludeMutationSuccess,
        True,
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
    ProductionValidationIssue,
    ProductionValidationErrorBody,
    ProductionValidationErrorEnvelope,
    ProductionConflictRecovery,
    ProductionConflictErrorBody,
    ProductionConflictErrorEnvelope,
    ProductionShortagePossibility,
    ProductionMaterialShortageItem,
    ProductionMaterialShortageErrorBody,
    ProductionMaterialShortageErrorEnvelope,
    ProductionOrderShortageErrorBody,
    ProductionOrderShortageErrorEnvelope,
)


def validated_body(request, serializer_class: type[StrictMutationSerializer]) -> dict:
    serializer = serializer_class(data=request.data)
    try:
        serializer.is_valid(raise_exception=True)
    except serializers.ValidationError as exc:
        raise ProductionMutationValidationError(exc.detail) from exc
    return dict(serializer.validated_data)
