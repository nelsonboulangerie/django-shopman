"""Backstage API — a loja no iFood (card do canal iFood e sinal da fila).

GET  /api/v1/backstage/ifood/store/          → projeção (quem vê a fila de pedidos)

Ligar e desligar o iFood (com período) é o toggle "Ativo" do card, comum a todos
os canais: ``POST /api/v1/backstage/feeds/switch/``.
"""

from __future__ import annotations

from dataclasses import asdict

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.projections.ifood_store import build_ifood_store_projection

from .permissions import HasBackstagePermission

_STORE_RESPONSE = inline_serializer(
    name="IFoodStoreProjectionResponse",
    fields={
        "enabled": serializers.BooleanField(),
        "governs": serializers.BooleanField(),
        "channel_off": serializers.BooleanField(),
        "shop_open": serializers.BooleanField(),
        "shop_message": serializers.CharField(),
        "ifood_available": serializers.BooleanField(allow_null=True),
        "ifood_status_label": serializers.CharField(),
        "ifood_checked_at_display": serializers.CharField(),
        "ifood_problems": serializers.ListField(child=serializers.CharField()),
        "diverges": serializers.BooleanField(),
    },
)


def _projection(request) -> dict:
    return asdict(build_ifood_store_projection(user=request.user))


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="A loja no iFood (status e conferência)", responses={200: _STORE_RESPONSE}),
)
class IFoodStoreView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_orders"

    def get(self, request):
        return Response(_projection(request))
