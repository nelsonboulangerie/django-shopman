"""Backstage API — operator alerts.

GET  /api/v1/backstage/alerts/          → active alerts + counts
POST /api/v1/backstage/alerts/<pk>/ack/ → acknowledge an alert

Mirrors the legacy HTMX alert fragments (shopman/backstage/views/alerts.py) on the
REST surface that the dedicated operator apps consume. Reuses
``shopman.backstage.services.alerts``; no rule is duplicated.
"""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api._production_mutations import (
    AlertAckMutationSerializer,
    ProductionMutationValidationError,
)
from shopman.backstage.api.production_freshness import (
    projection_revision_scope,
    validate_action_proof,
)
from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.alerts import build_operator_alerts_projection
from shopman.backstage.services import alerts as alert_service
from shopman.backstage.services.exceptions import AlertConflict

from .permissions import CanViewOperatorAlerts

_DEFAULT_LIMIT = 20


_PROJECTION_KIND = "alerts"
_PROJECTION_SLICE = "active"

_ACTION_RESPONSE = inline_serializer(
    name="OperatorAlertActionProjection",
    fields={
        "ref": serializers.CharField(),
        "kind": serializers.CharField(),
        "label": serializers.CharField(),
        "priority": serializers.IntegerField(),
        "enabled": serializers.BooleanField(),
        "reason": serializers.CharField(),
        "method": serializers.CharField(),
        "href": serializers.CharField(),
        "payload_schema": serializers.CharField(),
        "expected_rev": serializers.IntegerField(),
        "idempotency": serializers.DictField(),
        "confirmation": serializers.DictField(),
        "approval_requirement": serializers.DictField(allow_null=True),
        "source_alert_ref": serializers.CharField(),
        "source_alert_effect": serializers.CharField(),
        "proof": serializers.CharField(),
    },
)
_ALERT_RESPONSE = inline_serializer(
    name="OperatorAlertProjectionResponse",
    fields={
        "pk": serializers.IntegerField(),
        "rev": serializers.IntegerField(),
        "type": serializers.CharField(),
        "type_label": serializers.CharField(),
        "severity": serializers.CharField(),
        "severity_label": serializers.CharField(),
        "audience": serializers.CharField(),
        "message": serializers.CharField(),
        "order_ref": serializers.CharField(),
        "created_at_display": serializers.CharField(),
        "actions": _ACTION_RESPONSE.__class__(many=True),
    },
)
_ALERTS_RESPONSE = inline_serializer(
    name="OperatorAlertsProjectionResponse",
    fields={
        "alerts": _ALERT_RESPONSE.__class__(many=True),
        "counts": serializers.DictField(),
        "generated_at": serializers.DateTimeField(),
        "source_revision": serializers.CharField(),
        "fresh_until": serializers.DateTimeField(),
        "contract_version": serializers.IntegerField(),
    },
)
_ACK_RESPONSE = inline_serializer(
    name="OperatorAlertAckResponse",
    fields={"ok": serializers.BooleanField(), "pk": serializers.IntegerField()},
)


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Active operator alerts + counts",
        responses={200: _ALERTS_RESPONSE},
    ),
)
class AlertListView(APIView):
    permission_classes = [CanViewOperatorAlerts]

    def get(self, request):
        raw_limit = request.query_params.get("limit")
        try:
            limit = max(1, min(int(raw_limit), 100)) if raw_limit else _DEFAULT_LIMIT
        except (TypeError, ValueError):
            limit = _DEFAULT_LIMIT
        alerts = alert_service.list_active_alerts(user=request.user, limit=limit)
        counts = alert_service.active_counts(user=request.user)
        projection = build_operator_alerts_projection(alerts=alerts, counts=counts)
        return Response(
            projection_data(
                projection,
                freshness_context=(_PROJECTION_KIND, _PROJECTION_SLICE, f"user:{request.user.pk}"),
            )
        )


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Acknowledge an operator alert",
        request=AlertAckMutationSerializer,
        responses={200: _ACK_RESPONSE},
    ),
)
class AlertAckView(APIView):
    permission_classes = [CanViewOperatorAlerts]

    def post(self, request, pk: int):
        serializer = AlertAckMutationSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as exc:
            raise ProductionMutationValidationError(exc.detail) from exc
        body = dict(serializer.validated_data)
        action_ref = f"acknowledge:{pk}"
        action_href = f"/api/v1/backstage/alerts/{pk}/ack/"
        expected_scope = (_PROJECTION_KIND, _PROJECTION_SLICE, f"user:{request.user.pk}")
        if projection_revision_scope(body["source_revision"]) != expected_scope:
            raise ProductionMutationValidationError(
                {"source_revision": "A projeção não pertence a este operador ou painel de alertas."}
            )
        if body["action_ref"] != action_ref:
            raise ProductionMutationValidationError(
                {"action_ref": "A referência não corresponde ao alerta solicitado."}
            )
        proof_errors = validate_action_proof(
            action_proof=body["action_proof"],
            action_ref=action_ref,
            action_kind="acknowledge_alert",
            href=action_href,
            expected_rev=body["expected_rev"],
            source_revision=body["source_revision"],
            projection_generated_at=body["projection_generated_at"],
            fresh_until=body["fresh_until"],
            contract_version=body["contract_version"],
            projection_kind=_PROJECTION_KIND,
            selected_date=_PROJECTION_SLICE,
            subject_ref=f"user:{request.user.pk}",
        )
        if proof_errors:
            raise ProductionMutationValidationError(proof_errors)

        committed_replay = alert_service.has_committed_alert_ack(
            pk,
            user=request.user,
            idempotency_key=body["idempotency_key"],
            action_proof=body["action_proof"],
        )
        if timezone.now() >= body["fresh_until"] and not committed_replay:
            return Response(
                {
                    "detail": "A projeção de alertas expirou. Atualize antes de agir.",
                    "error": {
                        "code": "stale_projection",
                        "recovery": {"action": "refresh", "label": "Atualizar alertas"},
                    },
                },
                status=409,
            )
        try:
            ok = alert_service.ack_alert(
                pk,
                user=request.user,
                expected_rev=body["expected_rev"],
                idempotency_key=body["idempotency_key"],
                action_proof=body["action_proof"],
            )
        except AlertConflict as exc:
            error_data = dict(exc.data)
            return Response(
                {
                    "detail": str(exc),
                    "error": {
                        "code": exc.code,
                        "sent_rev": error_data.get("expected_rev"),
                        "current_rev": error_data.get("current_rev"),
                        "recovery": {"action": "refresh", "label": "Atualizar alertas"},
                    },
                },
                status=409,
            )
        if not ok:
            return Response({"detail": "Alerta não encontrado."}, status=404)
        return Response({"ok": True, "pk": pk})
