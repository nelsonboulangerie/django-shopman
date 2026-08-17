"""B.I. — endpoints de leitura analítica cross-suite (ADR-021).

Perm fina ``backstage.view_bi`` (persona gestor). Só leitura: o B.I. nunca
escreve; os ledgers seguem donos do fato.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.projections.bi_cash import build_bi_cash
from shopman.backstage.projections.bi_change import build_bi_change
from shopman.backstage.projections.bi_customers import build_bi_customers
from shopman.backstage.projections.bi_explore import (
    ExploreError,
    build_bi_explore,
    validate_config,
)
from shopman.backstage.projections.bi_forecast import ForecastError, build_bi_forecast
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


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="B.I. explorer: metric × up to two dimensions (strict grammar)",
        responses={200: OpenApiResponse(description="B.I. explore report.")},
    ),
)
class BIExploreView(_BIBase):
    def get(self, request):
        try:
            report = build_bi_explore(
                metric=str(request.GET.get("metric") or "revenue").strip(),
                by=str(request.GET.get("by") or "time").strip(),
                by2=str(request.GET.get("by2") or "").strip(),
                date_from=_query_date(request, "date_from"),
                date_to=_query_date(request, "date_to"),
            )
        except ExploreError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"bi": projection_data(report)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="B.I. forecast: what to expect for a day, week or month",
        responses={200: OpenApiResponse(description="B.I. forecast report.")},
    ),
)
class BIForecastView(_BIBase):
    """O que esperar — projeção a partir dos dias parecidos.

    Sem ``target`` a pergunta é sobre amanhã, que é o horizonte que a casa usa
    todo dia para decidir a fornada.
    """

    def get(self, request):
        target = _query_date(request, "target") or timezone.localdate() + timedelta(days=1)
        try:
            report = build_bi_forecast(
                target=target,
                horizon=str(request.GET.get("horizon") or "day").strip(),
            )
        except ForecastError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"bi": projection_data(report)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="B.I. change: how much change money the day is likely to need",
        responses={200: OpenApiResponse(description="B.I. change report.")},
    ),
)
class BIChangeView(_BIBase):
    """Previsão de necessidade de troco.

    Mesmo default de ``target`` da projeção: a pergunta útil é sobre amanhã,
    porque abastecer troco é decisão de véspera.
    """

    def get(self, request):
        target = _query_date(request, "target") or timezone.localdate() + timedelta(days=1)
        try:
            report = build_bi_change(
                target=target,
                horizon=str(request.GET.get("horizon") or "day").strip(),
            )
        except ForecastError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"bi": projection_data(report)})


# ── Cenários salvos (F9) — config validada pela gramática, zero código ───────

_VIEW_WINDOW_KEYS = {"preset", "from", "to"}


def _validated_view_config(raw) -> dict:
    """Config de cenário fora da gramática não salva (ExploreError na borda)."""
    if not isinstance(raw, dict):
        raise ExploreError("Config do cenário precisa ser um objeto.")
    unknown = set(raw) - {"metric", "by", "by2", "window"}
    if unknown:
        raise ExploreError(f"Chaves desconhecidas na config: {', '.join(sorted(unknown))}.")
    validate_config(
        str(raw.get("metric") or ""), str(raw.get("by") or "time"), str(raw.get("by2") or "")
    )
    window = raw.get("window") or {}
    if not isinstance(window, dict) or set(window) - _VIEW_WINDOW_KEYS:
        raise ExploreError("Janela do cenário aceita só: preset, from, to.")
    return {
        "metric": raw["metric"],
        "by": raw.get("by") or "time",
        "by2": raw.get("by2") or "",
        "window": {key: str(window[key]) for key in window},
    }


def _view_payload(view) -> dict:
    return {
        "id": view.pk,
        "name": view.name,
        "config": view.config,
        "is_favorite": view.is_favorite,
    }


@extend_schema_view(
    get=extend_schema(tags=["backstage"], summary="List my saved B.I. scenarios",
                      responses={200: OpenApiResponse(description="Saved scenarios.")}),
    post=extend_schema(tags=["backstage"], summary="Save a B.I. scenario (grammar-validated)",
                       responses={200: OpenApiResponse(description="Scenario saved.")}),
)
class BIViewListView(_BIBase):
    def get(self, request):
        from shopman.backstage.models import BIView

        views = BIView.objects.filter(owner=request.user)
        return Response({"views": [_view_payload(v) for v in views]})

    def post(self, request):
        from shopman.backstage.models import BIView

        name = str(request.data.get("name") or "").strip()[:80]
        if not name:
            return Response({"detail": "Dê um nome ao cenário."}, status=400)
        try:
            config = _validated_view_config(request.data.get("config"))
        except ExploreError as exc:
            return Response({"detail": str(exc)}, status=400)
        view, _created = BIView.objects.update_or_create(
            owner=request.user, name=name, defaults={"config": config}
        )
        return Response({"ok": True, "view": _view_payload(view)})


@extend_schema_view(
    patch=extend_schema(tags=["backstage"], summary="Toggle favorite on a saved scenario",
                        responses={200: OpenApiResponse(description="Scenario updated.")}),
    delete=extend_schema(tags=["backstage"], summary="Delete a saved scenario",
                         responses={200: OpenApiResponse(description="Scenario deleted.")}),
)
class BIViewDetailView(_BIBase):
    def _get(self, request, pk: int):
        from shopman.backstage.models import BIView

        return BIView.objects.filter(owner=request.user, pk=pk).first()

    def patch(self, request, pk: int):
        view = self._get(request, pk)
        if view is None:
            return Response({"detail": "Cenário não encontrado."}, status=404)
        view.is_favorite = bool(request.data.get("is_favorite"))
        view.save(update_fields=["is_favorite"])
        return Response({"ok": True, "view": _view_payload(view)})

    def delete(self, request, pk: int):
        view = self._get(request, pk)
        if view is None:
            return Response({"detail": "Cenário não encontrado."}, status=404)
        view.delete()
        return Response({"ok": True})
