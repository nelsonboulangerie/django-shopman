"""Nome da casa para os apps de operador (GET /api/v1/backstage/operator/tenant/).

Público e sem sessão, de propósito: quem pergunta é o BFF montando o
``/manifest.webmanifest`` (o navegador busca o manifesto sem cookie) e a primeira
pintura da tela de login, antes de existir operador. Devolve só o que a loja já
publica — o nome curto da marca — e nada da operação.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.operator_tenant import build_operator_tenant


class OperatorTenantView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["backstage"],
        summary="Operator app tenant name",
        responses={200: OpenApiResponse(description="Tenant short name for operator PWA names.")},
    )
    def get(self, request):
        from shopman.shop.models import Shop

        return Response({"tenant": projection_data(build_operator_tenant(Shop.load()))})
