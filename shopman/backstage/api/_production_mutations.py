"""Closed request contracts for production mutations.

Operational writes must never inherit Python truthiness (``bool("false")``),
ignore misspelled fields, or mutate a WorkOrder without the revision displayed
to the operator.  These serializers are the only JSON boundary for production
actions.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers
from rest_framework.exceptions import APIException


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


def validated_body(request, serializer_class: type[StrictMutationSerializer]) -> dict:
    serializer = serializer_class(data=request.data)
    try:
        serializer.is_valid(raise_exception=True)
    except serializers.ValidationError as exc:
        raise ProductionMutationValidationError(exc.detail) from exc
    return dict(serializer.validated_data)
