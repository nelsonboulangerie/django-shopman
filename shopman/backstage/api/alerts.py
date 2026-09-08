"""Backstage API — operator alerts.

GET  /api/v1/backstage/alerts/          → active alerts + counts
POST /api/v1/backstage/alerts/<pk>/ack/ → acknowledge an alert

Mirrors the legacy HTMX alert fragments (shopman/backstage/views/alerts.py) on the
REST surface that the dedicated operator apps consume. Reuses
``shopman.backstage.services.alerts``; no rule is duplicated.
"""

from __future__ import annotations

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.services import alerts as alert_service

from .permissions import CanViewOperatorAlerts

_DEFAULT_LIMIT = 20


def _alert_dict(alert) -> dict:
    return {
        "pk": alert.pk,
        "type": alert.type,
        "type_label": alert.get_type_display(),
        "severity": alert.severity,
        "severity_label": alert.get_severity_display(),
        "audience": alert.audience,
        "message": alert.message,
        "order_ref": alert.order_ref,
        "created_at_display": timezone.localtime(alert.created_at).strftime("%d/%m às %H:%M"),
        "actions": [
            {
                "ref": "acknowledge",
                "kind": "mutation",
                "label": "Reconhecer",
                "priority": "secondary",
                "enabled": True,
                "reason": "",
                "method": "POST",
                "href": f"/api/v1/backstage/alerts/{alert.pk}/ack/",
                "payload_schema": {},
                "expected_rev": None,
                "idempotency": "idempotent",
                "confirmation": {},
                "approval_requirement": None,
                "source_alert_ref": str(alert.pk),
                "lifecycle_effect": "acknowledges",
            }
        ],
    }


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Active operator alerts + counts",
        responses={200: OpenApiResponse(description="Unacknowledged alerts, newest first.")},
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
        return Response({
            "alerts": [_alert_dict(a) for a in alerts],
            "counts": {"active": counts.active, "critical": counts.critical},
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Acknowledge an operator alert",
        responses={200: OpenApiResponse(description="Alert acknowledged.")},
    ),
)
class AlertAckView(APIView):
    permission_classes = [CanViewOperatorAlerts]

    def post(self, request, pk: int):
        ok = alert_service.ack_alert(pk, user=request.user)
        if not ok:
            return Response({"detail": "Alerta não encontrado."}, status=404)
        return Response({"ok": True, "pk": pk})
