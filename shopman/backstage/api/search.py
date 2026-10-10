"""Busca da suíte — ``GET /api/v1/backstage/search/?q=<termo>``.

O campo do cabeçalho de todos os apps de operador e a barra grande da Central consomem
este endpoint para o alcance "App" e "Toda a suíte" (``projections/suite_search.py``).
Qualquer operador da casa acessa; o que volta já vem recortado pelo que ELE pode abrir.
Termo curto devolve a busca vazia (não é erro: o operador ainda está digitando); termo
longo demais é recusado no dialeto da casa, com ``field = "q"``.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import IsBackstageOperator
from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.suite_search import (
    MAX_QUERY_LENGTH,
    build_suite_search,
    normalize_query,
)


class SuiteSearchView(APIView):
    permission_classes = [IsBackstageOperator]

    @extend_schema(
        tags=["backstage"],
        summary="Suite search (orders, customers, products, materials, recipes, campaigns, screens)",
        parameters=[OpenApiParameter("q", str, description="Termo buscado (2 a 80 caracteres).")],
        responses={200: OpenApiResponse(description="Resultados agrupados por tipo, com o link do app de destino.")},
    )
    def get(self, request):
        query = normalize_query(request.query_params.get("q", ""))
        if len(query) > MAX_QUERY_LENGTH:
            raise ValidationError({"q": [f"Busque com até {MAX_QUERY_LENGTH} caracteres."]})
        return Response({"search": projection_data(build_suite_search(request.user, query))})
