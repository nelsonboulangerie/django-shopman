"""Ingestão de erros do cliente (superfícies de operador Nuxt) → observabilidade.

Espelha a filosofia do Sentry já configurado em ``config.settings``: opt-in e à prova
de ausência. As superfícies de operador headless (BFF/cliente) reportam erros
não-tratados para um único ponto que os LOGA em nível ``error`` — com ``SENTRY_DSN``
setado, a LoggingIntegration transforma isso em evento; sem DSN, vira log estruturado.
Nada de PII: o payload é sanitizado (e-mail/telefone redigidos, query da URL
descartada, campos truncados e allow-listed) antes de tocar o logger.

Gêmeo operador do endpoint do storefront: o ``operator-kit`` (Nuxt layer) posta aqui
via ``reportClientError`` → ``/api/v1/backstage/client-error/``.
"""

from __future__ import annotations

import hashlib
import logging
import math

import re
import time
import uuid
from typing import Any

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasMarketingCapability
from shopman.shop.services.marketing_observability import emit_metric
from shopman.shop.telemetry_redaction import redact_text, strip_url_query

from shopman.shop.services.observability import operational_context, operational_event

logger = logging.getLogger("shopman.backstage.client")

# Campos aceitos do relatório; qualquer outra chave é ignorada (evita virar dreno de
# dados arbitrários do cliente).
_ALLOWED_FIELDS = ("message", "kind", "source", "url", "stack", "user_agent", "app_version")
_MAX_LEN = {"message": 500, "stack": 4000, "url": 300, "user_agent": 300, "app_version": 60}
_MAX_DEFAULT = 120

def _redact(text: str) -> str:
    return redact_text(text)


def _strip_query(url: str) -> str:
    # Guarda só caminho + host: query/fragment podem carregar tokens ou dados.
    return strip_url_query(url)


def sanitize_client_report(payload: Any) -> dict[str, str]:
    """Reduz um payload arbitrário do cliente a um relatório seguro e limitado."""
    if not isinstance(payload, dict):
        return {}

    report: dict[str, str] = {}
    for field in _ALLOWED_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned:
            continue
        if field == "url":
            cleaned = _strip_query(cleaned)
        cleaned = _redact(cleaned)
        report[field] = cleaned[: _MAX_LEN.get(field, _MAX_DEFAULT)]
    return report


@method_decorator(
    ratelimit(key="ip", rate="30/m", method="POST", block=False), name="dispatch"
)
class ClientErrorView(APIView):
    """POST /api/v1/backstage/client-error/ — recebe um erro do cliente/BFF de operador.

    Write-only, sem estado. Sem autenticação (erros podem acontecer antes da sessão de
    operador existir, ou justamente quando ela expira) e rate-limited por IP para não
    virar dreno de log.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["telemetry"], summary="Report an operator client-side error")
    def post(self, request):
        if getattr(request, "limited", False):
            # Silencioso: telemetria nunca deve gerar ruído de erro no cliente.
            return Response(status=status.HTTP_429_TOO_MANY_REQUESTS)

        report = sanitize_client_report(request.data if hasattr(request, "data") else {})
        message = report.get("message")
        if message:
            logger.error(
                "backstage_client_error: %s",
                message,
                extra={"client_report": report},
            )
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)


_VITAL_NAMES = frozenset({"LCP", "INP", "CLS"})
_VITAL_RATINGS = frozenset({"good", "needs_improvement", "poor"})
_VITAL_ROUTES = frozenset({
    "board",
    "campaigns",
    "templates",
    "platforms",
    "history",
    "announcement_detail",
    "other",
})
_VITAL_THEMES = frozenset({"light", "dark"})


def sanitize_marketing_vital(payload: Any) -> dict[str, str | float]:
    """Accept one bounded Web Vital sample with no free-form dimensions."""

    if not isinstance(payload, dict):
        return {}
    name = payload.get("name")
    rating = payload.get("rating")
    route = payload.get("route")
    theme = payload.get("theme")
    value = payload.get("value")
    if (
        name not in _VITAL_NAMES
        or rating not in _VITAL_RATINGS
        or route not in _VITAL_ROUTES
        or theme not in _VITAL_THEMES
        or isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value < 0
        or value > 120_000
    ):
        return {}
    return {
        "name": name,
        "rating": rating,
        "route": route,
        "theme": theme,
        "value": round(float(value), 3),
    }


@method_decorator(
    ratelimit(key="ip", rate="60/m", method="POST", block=False), name="dispatch"
)
class MarketingVitalView(APIView):
    """Authenticated, write-only and dimension-closed Web Vitals ingestion."""

    permission_classes = [HasMarketingCapability]
    permission_map = {"POST": "shop.view_marketing"}

    @extend_schema(tags=["telemetry"], summary="Report one Marketing Web Vital")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(status=status.HTTP_429_TOO_MANY_REQUESTS)
        sample = sanitize_marketing_vital(
            request.data if hasattr(request, "data") else {}
        )
        if not sample:
            return Response(
                {"code": "invalid_metric"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        emit_metric(
            "marketing_frontend_vital",
            sample["value"],
            name=str(sample["name"]),
            rating=str(sample["rating"]),
            route=str(sample["route"]),
            theme=str(sample["theme"]),
        )
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)

class OperationalObservationMixin:
    """Metadados limitados das APIs operacionais; nunca texto/payload do pedido."""

    def dispatch(self, request, *args, **kwargs):
        start = time.perf_counter()
        with operational_context(request_id=uuid.uuid4().hex, operation=type(self).__name__, method=request.method) as context:
            self._operation_observation = context
            operational_event("operator.request.started")
            try:
                response = super().dispatch(request, *args, **kwargs)
            except Exception as exc:
                operational_event("operator.request.finished", response_status=500, outcome="transport_unknown", exception_class=type(exc).__name__, view_elapsed_ms=round((time.perf_counter() - start) * 1000, 3))
                raise
            body = getattr(response, "data", None)
            body = body if isinstance(body, dict) else {}
            outcome = body.get("outcome")
            outcome = outcome if outcome in {"applied", "not_applied", "unknown", "in_progress"} else "read" if request.method == "GET" and response.status_code < 400 else "unclassified"
            operational_event("operator.request.finished", response_status=response.status_code, outcome=outcome, replayed=body.get("replayed") is True, view_elapsed_ms=round((time.perf_counter() - start) * 1000, 3))
            response["X-Request-ID"] = context["request_id"]
            return response

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # initial já aplicou autenticação/permissão. Nunca confiar em actor do body.
        context = self._operation_observation
        context["actor_id"] = request.user.pk
        data = request.data if request.method in {"POST", "PATCH"} and callable(getattr(self, request.method.lower(), None)) else {}
        data = data if isinstance(data, dict) else {}
        resource = kwargs.get("ref") or kwargs.get("sku") or data.get("ref") or data.get("sku") or request.query_params.get("ref")
        if isinstance(resource, str):
            context["resource_ref"] = resource[:128]
        surface = data.get("surface_ref")
        if isinstance(surface, str):
            context["surface_ref"] = surface[:128]
        key = request.headers.get("Idempotency-Key") or data.get("idempotency_key") or request.query_params.get("idempotency_key")
        base = data.get("base_revision") or request.headers.get("If-Match")
        # Chaves/precondições opacas são digests: não podem virar dreno de tokens.
        for field, value in (("intention_digest", key), ("base_revision_digest", base)):
            if isinstance(value, str) and value:
                context[field] = hashlib.sha256(value.encode()).hexdigest()
