"""Backstage Catalog Promise API — o que o cliente lê ainda corresponde à ficha?

Leitura pura (WP-FICHA-DE-PRODUTO-E-PROMESSA bloco C): devolve, por produto e
por fato derivado, o valor publicado, se ele é derivado ou manual, de qual
versão da ficha veio, se está vencido e quem o conferiu. Nada aqui escreve.

Gate: ``backstage.view_production_reports`` — é pergunta de quem responde pelo
que a casa promete.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections.product_promise import (
    build_catalog_promise,
    build_product_promise,
)


def _flag(request, name: str) -> bool:
    return str(request.query_params.get(name, "")).lower() in ("1", "true", "yes")


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Promessa do catálogo (frescor dos fatos derivados da ficha)",
        parameters=[
            OpenApiParameter("stale", bool, description="Lista só o que está vencido."),
            OpenApiParameter("unpublished", bool, description="Inclui produtos despublicados."),
        ],
        responses={200: OpenApiResponse(description="Fatos derivados por produto, com versão de origem.")},
    ),
)
class CatalogPromiseView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.view_production_reports"

    def get(self, request):
        promise = build_catalog_promise(
            only_stale=_flag(request, "stale"),
            include_unpublished=_flag(request, "unpublished"),
        )
        return Response({"promise": projection_data(promise)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Promessa de um produto (frescor dos fatos derivados da ficha)",
        responses={
            200: OpenApiResponse(description="Fatos derivados do produto, com versão de origem."),
            404: OpenApiResponse(description="SKU não existe no catálogo."),
        },
    ),
)
class ProductPromiseView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.view_production_reports"

    def get(self, request, sku: str):
        from shopman.offerman.models import Product

        product = Product.objects.filter(sku=sku).first()
        if product is None:
            return Response({"detail": f"Produto '{sku}' não existe."}, status=404)
        return Response({"promise": projection_data(build_product_promise(product))})
