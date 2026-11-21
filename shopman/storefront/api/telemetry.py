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

from shopman.shop.services.observability import operational_event

logger = logging.getLogger("shopman.storefront.client")

# Campos aceitos do relatório; qualquer outra chave é ignorada (evita virar dreno
# de dados arbitrários do cliente).
_ALLOWED_FIELDS = ("message", "kind", "source", "url", "stack", "user_agent", "app_version")
_MAX_LEN = {"message": 500, "stack": 4000, "url": 300, "user_agent": 300, "app_version": 60}
_MAX_DEFAULT = 120
_REDACT_MARGIN = 256

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
    "address.location_check.requested": {
        "target": {"saved", "search"},
        "mode": {"measure", "visible"},
    },
    "address.location_check.resolved": {
        "target": {"saved", "search"},
        "status": {"compatible", "diverged", "inconclusive", "unavailable"},
        "accuracy_bucket": {"good", "medium", "low", "unknown"},
        "policy_version": {"v1"},
    },
    "address.location_check.failed": {
        "target": {"saved", "search"},
        "reason": {"denied", "timeout", "unavailable", "unsupported", "rate_limited"},
    },
    "address.location_mismatch.shown": {
        "target": {"saved", "search"},
        "accuracy_bucket": {"good", "medium", "low", "unknown"},
        "policy_version": {"v1"},
    },
    "address.location_mismatch.action": {
        "action": {"keep", "use_current", "review_map", "dismiss"},
        "target": {"saved", "search"},
    },
    "address.location_mismatch.recovered": {
        "path": {"use_current", "review_map"},
        "zone_result": {"covered", "uncovered", "deferred"},
    },
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
        limit = _MAX_LEN.get(field, _MAX_DEFAULT)
        # Corta ANTES dos regex de redação (endpoint anônimo: o texto cru pode ter
        # megabytes e os regex são superlineares). A folga garante que um e-mail
        # ou telefone na borda do corte final ainda seja visto inteiro.
        cleaned = value[: limit + _REDACT_MARGIN].strip()
        if not cleaned:
            continue
        if field == "url":
            cleaned = _strip_query(cleaned)
        cleaned = _redact(cleaned)
        report[field] = cleaned[:limit]
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


# O app instalado da loja trocou de versão (#2379). Gêmeo do
# ``backstage.api.telemetry.ClientPwaUpdateView``: o mesmo evento
# (``pwa.update_applied``), com ``app="storefront"``, para a pergunta "a loja instalada
# saiu do bundle velho?" ter a mesma resposta que o PDV e a Cozinha já têm.
#
# Os dois gatilhos da loja: o toque em "Atualizar" (``prompt``) e a troca de tela que
# aplica a versão nova antes de montar a próxima (``navigation``, a porta 1 do
# ``PwaUpdatePrompt``). A loja nunca aplica sozinha, parada: quem decide é o toque.
_PWA_TRIGGERS = frozenset({"prompt", "navigation"})
# Versão do build: sha curto do App Platform (`SOURCE_VERSION`) ou "local" no dev.
_PWA_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$")


def sanitize_pwa_update(payload: Any) -> dict[str, str]:
    """Aceita UMA troca de versão da loja instalada, sem dimensão livre."""
    if not isinstance(payload, dict):
        return {}
    trigger = payload.get("trigger")
    if trigger not in _PWA_TRIGGERS:
        return {}
    report = {"app": "storefront", "trigger": trigger}
    for field in ("from_version", "to_version"):
        value = payload.get(field)
        # Versão ausente é fato comum (marca escrita por um bundle sem SOURCE_VERSION);
        # versão FORA do formato é entrada arbitrária e não entra no log.
        if isinstance(value, str) and _PWA_VERSION.match(value):
            report[field] = value
    return report


@method_decorator(
    ratelimit(key="ip", rate="30/m", method="POST", block=False), name="dispatch"
)
class ClientPwaUpdateView(APIView):
    """POST /api/v1/storefront/client-pwa-update/ — a loja instalada trocou de versão.

    O relato chega no boot seguinte à troca: o ``updateServiceWorker(true)`` termina
    em carga nova da página, e nada que fique na memória sobrevive para contar o que
    aconteceu. Sem autenticação e com limite por IP, como o ``ClientErrorView``: a
    cliente pode nem ter entrado, e o payload é fechado em dimensão.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["telemetry"], summary="Report a storefront PWA version swap")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(status=status.HTTP_429_TOO_MANY_REQUESTS)

        report = sanitize_pwa_update(request.data if hasattr(request, "data") else {})
        if report:
            operational_event("pwa.update_applied", **report)
        return Response({"ok": True}, status=status.HTTP_202_ACCEPTED)
