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

#: Os apps de operador que leem o sino (ids de ``surfaces/registry.json``).
_SURFACES = frozenset({"orders", "production", "pos", "kds", "marketing", "bi", "purchase", "hub"})


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
        "respond_by_iso": serializers.CharField(),
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
        # ``?scope=orders``: o sino do Gestor de pedidos vê só o que é de pedido.
        scope = str(request.query_params.get("scope") or "").strip()
        if scope not in alert_service.ALERT_SCOPES:
            scope = ""
        # ``?surface=production``: de qual app o sino é lido. Não filtra nada; decide se
        # o botão do aviso é um caminho deste app ou o endereço do app que resolve.
        surface = str(request.query_params.get("surface") or "").strip() or scope
        if surface not in _SURFACES:
            surface = ""
        alerts = alert_service.list_active_alerts(user=request.user, limit=limit, scope=scope)
        counts = alert_service.active_counts(user=request.user, scope=scope)
        projection = build_operator_alerts_projection(alerts=alerts, counts=counts, surface=surface, user=request.user)
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


# ── "Vou verificar" da Concierge (WP-05) ──────────────────────────────

_VERIFY_ALERT_TYPE = "concierge_verify"

#: (status, frase do cartão) de cada desfecho de ``shopman.shop.concierge_verification``.
_VERIFY_OUTCOMES = {
    "not_found": (404, "Esta pergunta não está mais na conversa."),
    "not_open": (409, "Esta pergunta já foi respondida ou assumida."),
    "with_team": (409, "A conversa já está com a equipe. Continue por lá."),
    "empty_answer": (422, "Escreva a resposta para o cliente."),
    "answer_too_long": (422, "A resposta passou de {detail} caracteres. Encurte, ou assuma a conversa."),
    "house_rule_held": (422, "A resposta não pode sair como está (regra da casa {detail}). Reescreva, ou assuma a conversa."),
    "not_sent": (409, "A resposta não saiu pelo WhatsApp ({detail}). O texto continua aqui: tente de novo, ou assuma a conversa."),
    "window_closed": (409, "A janela de 24 horas do WhatsApp fechou: a resposta não sai mais por aqui. Assuma a conversa."),
    "unavailable": (503, "A Concierge não está ligada nesta instalação."),
}

_VERIFY_ANSWER_REQUEST = inline_serializer(
    name="ConciergeVerificationAnswerRequest",
    fields={"text": serializers.CharField(allow_blank=True, max_length=2000)},
)
_VERIFY_RESPONSE = inline_serializer(
    name="ConciergeVerificationResponse",
    fields={"ok": serializers.BooleanField(), "pk": serializers.IntegerField(), "sent_text": serializers.CharField()},
)


def _verify_alert(request, pk: int):
    """O cartão de verificação aberto que este operador pode ver; ``None`` senão."""
    from shopman.backstage.models import OperatorAlert

    return (
        OperatorAlert.objects.filter(
            pk=pk,
            type=_VERIFY_ALERT_TYPE,
            resolved_at__isnull=True,
            audience__in=alert_service.visible_alert_audiences(request.user),
        )
        .only("pk")
        .first()
    )


def _verify_response(pk: int, result) -> Response:
    if result.ok and not result.code:
        return Response({"ok": True, "pk": pk, "sent_text": result.sent_text})
    code = result.code
    if result.ok:
        # Assumiu, mas o aviso ao cliente não saiu: a conversa já é da equipe.
        return Response({"ok": True, "pk": pk, "sent_text": "", "warning": code, "detail": result.detail})
    key = "window_closed" if code == "not_sent" and result.detail == "window_closed" else code
    status, detail = _VERIFY_OUTCOMES.get(key, (409, "Não deu para concluir. Atualize os avisos."))
    body = {"detail": detail.replace("{detail}", result.detail or code), "error": {"code": key}}
    if status == 422:
        body["field"] = "text"
    if result.sent_text:
        body["error"]["text"] = result.sent_text
    return Response(body, status=status)


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Answer the customer's question the Concierge asked the team",
        request=_VERIFY_ANSWER_REQUEST,
        responses={200: _VERIFY_RESPONSE},
    ),
)
class ConciergeVerificationAnswerView(APIView):
    permission_classes = [CanViewOperatorAlerts]

    def post(self, request, pk: int):
        from shopman.shop import concierge_verification

        if _verify_alert(request, pk) is None:
            return Response({"detail": "Aviso não encontrado.", "error": {"code": "not_found"}}, status=404)
        text = str((request.data or {}).get("text") or "")
        result = concierge_verification.answer(pk, text, actor=alert_service._actor_ref(request.user) or "operador")
        return _verify_response(pk, result)


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Take over the conversation the Concierge is verifying",
        request=None,
        responses={200: _VERIFY_RESPONSE},
    ),
)
class ConciergeVerificationTakeOverView(APIView):
    permission_classes = [CanViewOperatorAlerts]

    def post(self, request, pk: int):
        from shopman.shop import concierge_verification

        if _verify_alert(request, pk) is None:
            return Response({"detail": "Aviso não encontrado.", "error": {"code": "not_found"}}, status=404)
        result = concierge_verification.take_over(pk, actor=alert_service._actor_ref(request.user) or "operador")
        return _verify_response(pk, result)
