"""B.I. — endpoints de leitura analítica cross-suite (ADR-021).

Perm fina ``backstage.view_bi`` (persona gestor). Só leitura: o B.I. nunca
escreve; os ledgers seguem donos do fato.
"""

from __future__ import annotations

from datetime import date

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.projections.bi_cash import build_bi_cash
from shopman.backstage.projections.bi_customers import build_bi_customers
from shopman.backstage.projections.bi_production import build_bi_production
from shopman.backstage.projections.bi_sales import build_bi_sales

from .permissions import HasBackstagePermission
from .projections import projection_data


class _BIBase(APIView):
    """Shared gate for B.I. read endpoints."""

    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.view_bi"


def _query_date(request, param: str) -> date | None:
    raw = (request.GET.get(param) or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None  # janela inválida cai no default — a projection normaliza


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="B.I. production: daily series, quality mix and oven real time",
        responses={200: OpenApiResponse(description="B.I. production report.")},
    ),
)
class BIProductionView(_BIBase):
    def get(self, request):
        report = build_bi_production(
            date_from=_query_date(request, "date_from"),
            date_to=_query_date(request, "date_to"),
        )
        return Response({"bi": projection_data(report)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="B.I. sales: daily revenue, channel mix, top SKUs, hour/weekday",
        responses={200: OpenApiResponse(description="B.I. sales report.")},
    ),
)
class BISalesView(_BIBase):
    def get(self, request):
        report = build_bi_sales(
            date_from=_query_date(request, "date_from"),
            date_to=_query_date(request, "date_to"),
        )
        return Response({"bi": projection_data(report)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="B.I. cash: shift variance, movements and payment method mix",
        responses={200: OpenApiResponse(description="B.I. cash report.")},
    ),
)
class BICashView(_BIBase):
    def get(self, request):
        report = build_bi_cash(
            date_from=_query_date(request, "date_from"),
            date_to=_query_date(request, "date_to"),
        )
        return Response({"bi": projection_data(report)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="B.I. customers: RFM distribution and new customers by week",
        responses={200: OpenApiResponse(description="B.I. customers report.")},
    ),
)
class BICustomersView(_BIBase):
    def get(self, request):
        report = build_bi_customers(
            date_from=_query_date(request, "date_from"),
            date_to=_query_date(request, "date_to"),
        )
        return Response({"bi": projection_data(report)})
