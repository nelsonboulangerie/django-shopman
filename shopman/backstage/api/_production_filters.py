"""Strict query contracts for production read APIs.

Production screens are operational surfaces: silently replacing an invalid date,
normalising an inverted interval, or ignoring a misspelled filter can make a
perfectly valid response describe the wrong shift. These serializers therefore
reject unknown and malformed input before a projection is built.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from shopman.backstage.api._production_mutations import (
    ProductionMutationValidationError,
)

VALID_REPORT_KINDS = ("history", "operator_productivity", "recipe_waste", "quality")
VALID_WORK_ORDER_STATUSES = ("planned", "started", "finished", "void")

# A quarter is the largest synchronous report window. Longer exports must move
# to the asynchronous export workflow introduced by WP-P1.5.
MAX_REPORT_RANGE_DAYS = 93


class StrictQuerySerializer(serializers.Serializer):
    """Serializer that treats every undeclared query parameter as a typo."""

    def to_internal_value(self, data):
        unknown = sorted(set(data.keys()) - set(self.fields))
        if unknown:
            raise serializers.ValidationError({field: ["Filtro desconhecido."] for field in unknown})
        return super().to_internal_value(data)


class ProductionDateQuerySerializer(StrictQuerySerializer):
    date = serializers.DateField(required=False, allow_null=False)


class ProductionBoardQuerySerializer(ProductionDateQuerySerializer):
    position = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)


class ProductionKDSQuerySerializer(ProductionBoardQuerySerializer):
    pass


class ProductionMiseEnPlaceQuerySerializer(ProductionDateQuerySerializer):
    expand = serializers.BooleanField(required=False, default=False)


class ProductionWeighingQuerySerializer(ProductionDateQuerySerializer):
    position = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    base_recipe = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)


class ProductionManagementQuerySerializer(ProductionDateQuerySerializer):
    position = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)


class ProductionBlindMapQuerySerializer(ProductionWeighingQuerySerializer):
    pass


def _default_date_from():
    return timezone.localdate() - timedelta(days=6)


class ProductionReportsQuerySerializer(StrictQuerySerializer):
    date_from = serializers.DateField(required=False, default=_default_date_from)
    date_to = serializers.DateField(required=False, default=timezone.localdate)
    report_kind = serializers.ChoiceField(choices=VALID_REPORT_KINDS, required=False)
    # ``kind`` remains an explicit compatibility alias. It is not an open-ended
    # fallback: invalid values and conflicting aliases are rejected.
    kind = serializers.ChoiceField(choices=VALID_REPORT_KINDS, required=False)
    recipe_ref = serializers.CharField(required=False, allow_blank=True, default="", trim_whitespace=True)
    position_ref = serializers.CharField(required=False, allow_blank=True, default="", trim_whitespace=True)
    operator_ref = serializers.CharField(required=False, allow_blank=True, default="", trim_whitespace=True)
    status = serializers.ChoiceField(
        choices=VALID_WORK_ORDER_STATUSES,
        required=False,
        allow_blank=True,
        default="",
    )
    # DRF consumes this for renderer negotiation, but it remains part of the
    # public query contract and must be declared for strict checking.
    format = serializers.ChoiceField(choices=("json", "csv"), required=False)

    def validate(self, attrs):
        report_kind = attrs.get("report_kind")
        alias_kind = attrs.pop("kind", None)
        if report_kind and alias_kind and report_kind != alias_kind:
            raise serializers.ValidationError(
                {"report_kind": ["report_kind e kind precisam indicar o mesmo relatório."]}
            )

        attrs["report_kind"] = report_kind or alias_kind or "history"
        attrs.pop("format", None)

        date_from = attrs["date_from"]
        date_to = attrs["date_to"]
        if date_from > date_to:
            raise serializers.ValidationError({"date_to": ["A data final não pode ser anterior à data inicial."]})
        if (date_to - date_from).days + 1 > MAX_REPORT_RANGE_DAYS:
            raise serializers.ValidationError(
                {"date_to": [f"O intervalo síncrono máximo é de {MAX_REPORT_RANGE_DAYS} dias."]}
            )
        return attrs


def validated_query(request, serializer_class: type[StrictQuerySerializer]) -> dict:
    serializer = serializer_class(data=request.query_params)
    try:
        serializer.is_valid(raise_exception=True)
    except serializers.ValidationError as exc:
        raise ProductionMutationValidationError(exc.detail) from exc
    return dict(serializer.validated_data)


def report_filters(request) -> dict:
    """Return the normalized filter dict consumed by projections/export."""

    filters = validated_query(request, ProductionReportsQuerySerializer)
    filters["date_from"] = filters["date_from"].isoformat()
    filters["date_to"] = filters["date_to"].isoformat()
    return filters
