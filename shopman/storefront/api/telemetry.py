"""Ingestão de erros do cliente (storefront Nuxt) → observabilidade.

Espelha a filosofia do Sentry já configurado em ``config.settings``: opt-in e à
prova de ausência. Aqui a superfície headless (BFF/cliente) reporta erros
não-tratados para um único ponto que os LOGA em nível ``error`` — quando
``SENTRY_DSN`` está setado, a LoggingIntegration do sentry-sdk transforma isso
em evento automaticamente; sem DSN, vira só log estruturado. Nada de PII: o
payload é sanitizado (e-mail/telefone redigidos, query da URL descartada,
campos truncados e allow-listed) antes de tocar o logger.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger("shopman.storefront.client")

# Campos aceitos do relatório; qualquer outra chave é ignorada (evita virar dreno
# de dados arbitrários do cliente).
_ALLOWED_FIELDS = ("message", "kind", "source", "url", "stack", "user_agent", "app_version")
_MAX_LEN = {"message": 500, "stack": 4000, "url": 300, "user_agent": 300, "app_version": 60}
_MAX_DEFAULT = 120

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Sequências longas de dígitos (telefones, com separadores) → redige.
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")

_ADDRESS_EVENT_SCHEMA: dict[str, dict[str, set[str]]] = {
    "address.location.requested": {"origin": {"checkout"}},
    "address.location.resolved": {
        "accuracy_bucket": {"good", "medium", "low", "unknown"},
        "latency_bucket": {"fast", "normal", "slow"},
    },
    "address.location.denied": {"reason": {"denied", "timeout", "unavailable", "unsupported"}},
    "address.map.ready": {
        "origin": {"gps", "place", "adjust"},
        "latency_bucket": {"fast", "normal", "slow"},
    },
    "address.map.fallback": {
        "origin": {"gps", "place", "adjust"},
        "reason": {"disabled", "provider", "reverse", "unsupported"},
    },
    "address.map.confirmed": {
        "origin": {"gps", "place", "adjust"},
        "accuracy_bucket": {"good", "medium", "low", "unknown"},
        "moved": {"true", "false"},
    },
    "address.zone.resolved": {"result": {"covered", "outside", "deferred"}},
}


def _redact(text: str) -> str:
    text = _EMAIL_RE.sub("[email]", text)
    text = _PHONE_RE.sub("[phone]", text)
    return text


def _strip_query(url: str) -> str:
    # Guarda só caminho + host: query/fragment podem carregar tokens ou dados.
    return url.split("?", 1)[0].split("#", 1)[0]


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
    """POST /api/v1/storefront/client-error/ — recebe um erro do cliente/BFF.

    Write-only, sem estado. Sem autenticação (erros podem acontecer antes da
    sessão existir) e rate-limited por IP para não virar dreno de log.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["telemetry"], summary="Report a client-side error")
    def post(self, request):
        if getattr(request, "limited", False):
            # Silencioso: telemetria nunca deve gerar ruído de erro no cliente.
            return Response(status=status.HTTP_429_TOO_MANY_REQUESTS)

        report = sanitize_client_report(request.data if hasattr(request, "data") else {})
        message = report.get("message")
        if message:
            logger.error(
                "storefront_client_error: %s",
                message,
                extra={"client_report": report},
            )
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)


def sanitize_address_event(payload: Any) -> dict[str, Any]:
    """Accept only aggregate enums; address-like values have nowhere to land."""
    if not isinstance(payload, dict):
        return {}
    event = payload.get("event")
    schema = _ADDRESS_EVENT_SCHEMA.get(event)
    properties = payload.get("properties")
    if schema is None or not isinstance(properties, dict):
        return {}
    clean: dict[str, str] = {}
    for field, allowed in schema.items():
        raw = properties.get(field)
        value = str(raw).lower() if isinstance(raw, bool) else raw
        if isinstance(value, str) and value in allowed:
            clean[field] = value
    if set(clean) != set(schema):
        return {}
    return {"event": event, "properties": clean}


@method_decorator(
    ratelimit(key="ip", rate="60/m", method="POST", block=False), name="dispatch"
)
class AddressEventView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["telemetry"], summary="Report an aggregate address-flow event")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(status=status.HTTP_429_TOO_MANY_REQUESTS)
        event = sanitize_address_event(request.data if hasattr(request, "data") else {})
        if not event:
            return Response({"detail": "Evento inválido."}, status=status.HTTP_400_BAD_REQUEST)
        logger.info("storefront_address_event", extra={"address_event": event})
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)
