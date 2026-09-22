"""Backstage API — a loja no iFood (Gestor de pedidos, menu de mais opções).

GET  /api/v1/backstage/ifood/store/          → projeção (quem vê a fila de pedidos)
POST /api/v1/backstage/ifood/store/pause/    → pausa o iFood com a casa aberta (Gerente)
POST /api/v1/backstage/ifood/store/resume/   → retira a pausa do gestor (Gerente)

A pausa não chama o iFood dentro do request: grava a interrupção (quem, quando,
por quê) e enfileira a Directive que atravessa a rede com retry. A tela mostra
"Pedindo a pausa ao iFood…" até a Directive responder.
"""

from __future__ import annotations

from dataclasses import asdict

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.projections.ifood_store import PAUSE_PERMISSION, build_ifood_store_projection
from shopman.shop.services import ifood_merchant

from .permissions import HasBackstagePermission

_STORE_RESPONSE = inline_serializer(
    name="IFoodStoreProjectionResponse",
    fields={
        "enabled": serializers.BooleanField(),
        "governs": serializers.BooleanField(),
        "can_pause": serializers.BooleanField(),
        "shop_open": serializers.BooleanField(),
        "shop_message": serializers.CharField(),
        "ifood_available": serializers.BooleanField(allow_null=True),
        "ifood_status_label": serializers.CharField(),
        "ifood_checked_at_display": serializers.CharField(),
        "ifood_problems": serializers.ListField(child=serializers.CharField()),
        "diverges": serializers.BooleanField(),
        "pause": serializers.DictField(allow_null=True),
        "last_pause": serializers.DictField(allow_null=True),
        "options": serializers.ListField(child=serializers.DictField()),
    },
)


class IFoodPauseRequestSerializer(serializers.Serializer):
    duration = serializers.ChoiceField(
        choices=[*ifood_merchant.PAUSE_DURATIONS, ifood_merchant.PAUSE_UNTIL_CLOSE],
        error_messages={"invalid_choice": "Escolha por quanto tempo pausar."},
    )
    reason = serializers.CharField(
        max_length=200,
        trim_whitespace=True,
        error_messages={"blank": "Escreva o motivo da pausa.", "required": "Escreva o motivo da pausa."},
    )


def _projection(request) -> dict:
    return asdict(build_ifood_store_projection(user=request.user))


def _refused(exc: ifood_merchant.PauseRefused) -> Response:
    return Response({"detail": str(exc), "error": {"code": "ifood_pause_refused"}}, status=409)


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="A loja no iFood (status, pausa do gestor)", responses={200: _STORE_RESPONSE}),
)
class IFoodStoreView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request):
        return Response(_projection(request))


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Pausar a loja no iFood",
        request=IFoodPauseRequestSerializer,
        responses={200: _STORE_RESPONSE},
    ),
)
class IFoodStorePauseView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = PAUSE_PERMISSION

    def post(self, request):
        serializer = IFoodPauseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ifood_merchant.request_pause(
                duration=serializer.validated_data["duration"],
                reason=serializer.validated_data["reason"],
                user=request.user,
            )
        except ifood_merchant.PauseRefused as exc:
            return _refused(exc)
        return Response(_projection(request))


@extend_schema_view(
    post=extend_schema(tags=["backstage"], summary="Retomar a loja no iFood", request=None, responses={200: _STORE_RESPONSE}),
)
class IFoodStoreResumeView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = PAUSE_PERMISSION

    def post(self, request):
        try:
            ifood_merchant.request_resume(user=request.user)
        except ifood_merchant.PauseRefused as exc:
            return _refused(exc)
        return Response(_projection(request))
