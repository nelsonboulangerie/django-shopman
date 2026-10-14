"""Shopman middleware — App Platform host probe, access log, API version header, operator cookie domain.

As superfícies de cliente/operador são apps Nuxt; a captura de ?channel=, o
onboarding e o welcome-gate vivem nos apps de superfície (storefront/backstage) —
não aqui. Este módulo guarda só os middlewares realmente wired em settings.
"""

from __future__ import annotations

import logging
import time
from ipaddress import ip_address, ip_network

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed

API_V1_PREFIX = "/api/v1/"
API_VERSION = "1"
HEALTH_PROBE_PATHS = {
    "/health/live/",
    "/health/ready/",
    "/health/database/",
    "/health/",
    "/ready/",
}
APP_PLATFORM_PROBE_NETWORK = ip_network("100.64.0.0/10")


class AppPlatformHealthCheckHostMiddleware:
    """Let DigitalOcean internal probes reach health views without wildcard hosts.

    App Platform probes the container through a private CGNAT address and sends
    that IP as the Host header. Rewriting only health/readiness probe hosts keeps
    Django's normal ALLOWED_HOSTS protection intact for every business route.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info in HEALTH_PROBE_PATHS and _is_app_platform_probe_host(
            request.META.get("HTTP_HOST", "")
        ):
            request.META["HTTP_HOST"] = _canonical_allowed_host()
        return self.get_response(request)


access_logger = logging.getLogger("shopman.access")

_ACCESS_LOG_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


class AccessLogMiddleware:
    """Uma linha por request, sem dado nenhum de quem pediu: método, ROTA, status, duração.

    O access log do daphne fica em ``/dev/null`` (ver ``.do/app.alpha-subdomains.yaml``)
    porque grava o request-target CRU, com query string, e o webhook da Efí
    autentica por ``?token=``. Ele também grava o IP do cliente, e o formato
    não tem opção. Sem nenhum access log, os 503 do Admin de 13/10/2026 (17:35-17:45
    UTC) não deixaram rastro do que a instância atendia antes de cair.

    Esta linha registra o PADRÃO da URL resolvida (``resolver_match.route``, ex.:
    ``api/v1/backstage/orders/<str:ref>/``), nunca o caminho pedido: ref, token de
    link mágico e código de recibo ficam de fora por construção, não por filtro.
    Request que não resolveu rota (404, host recusado) sai com ``route=-``. Sem IP,
    sem usuário, sem query string, sem corpo.

    Sonda da plataforma que responde 2xx não é registrada (seria uma linha a cada
    poucos segundos por sonda); sonda que FALHA é, porque é exatamente o sinal.
    Resposta em stream (SSE) mede o tempo até os cabeçalhos, não a vida do stream.

    Opt-in por ``SHOPMAN_ACCESS_LOG``: desligado, o Django tira o middleware da
    cadeia na subida (``MiddlewareNotUsed``) e não custa nada por request.
    """

    def __init__(self, get_response):
        if not getattr(settings, "SHOPMAN_ACCESS_LOG", False):
            raise MiddlewareNotUsed
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        status = int(getattr(response, "status_code", 0) or 0)
        if request.path_info in HEALTH_PROBE_PATHS and status < 400:
            return response
        match = getattr(request, "resolver_match", None)
        pattern = getattr(match, "route", None) if match is not None else None
        route = f"/{pattern}" if pattern else "-"
        method = request.method if request.method in _ACCESS_LOG_METHODS else "OTHER"
        duration_ms = int((time.monotonic() - started) * 1000)
        streaming = bool(getattr(response, "streaming", False))
        access_logger.log(
            logging.WARNING if status >= 500 else logging.INFO,
            "access %s %s %s %dms%s",
            method,
            route,
            status,
            duration_ms,
            " stream" if streaming else "",
            extra={
                "http_method": method,
                "http_route": route,
                "http_status": status,
                "duration_ms": duration_ms,
                "streaming": streaming,
            },
        )
        return response


def _is_app_platform_probe_host(raw_host: str) -> bool:
    host = _strip_port(raw_host)
    try:
        return ip_address(host) in APP_PLATFORM_PROBE_NETWORK
    except ValueError:
        return False


def _strip_port(raw_host: str) -> str:
    host = raw_host.strip()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0]


def _canonical_allowed_host() -> str:
    for host in settings.ALLOWED_HOSTS:
        if host and host != "*" and not host.startswith("."):
            return host
    return "localhost"


class BackupSheetDomainMiddleware:
    """`backup.boulangerie.com.br` → a planilha viva do cofre, num redirect.

    O domínio é só um ATALHO memorável; quem manda no acesso é o Google — a
    planilha continua privada às contas com quem foi compartilhada, e o
    redirect não concede nada. Config-driven e falha fechado: sem
    ``SHOPMAN_BACKUP_SHEET_URL`` o host responde 404, nunca um destino
    inventado. 302 (não 301) de propósito: se a planilha um dia for recriada,
    nenhum navegador fica preso num permanente cacheado.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = getattr(settings, "SHOPMAN_BACKUP_SHEET_HOST", "")
        if host and _strip_port(request.META.get("HTTP_HOST", "")).lower() == host.lower():
            url = getattr(settings, "SHOPMAN_BACKUP_SHEET_URL", "")
            if not url:
                from django.http import HttpResponseNotFound

                return HttpResponseNotFound("Planilha do cofre não configurada.")
            from django.http import HttpResponseRedirect

            return HttpResponseRedirect(url)
        return self.get_response(request)


class APIVersionHeaderMiddleware:
    """Stamp every `/api/v1/` response with `X-API-Version: 1`.

    Informational header for debugging and telemetry, asserted client-side by
    the BFFs: each Nuxt surface reads it on the proxy response and logs a
    structured Nitro warning when the major diverges from the one it was built
    against, without ever blocking the request (operator surfaces via
    ``surfaces/operator-kit/server/utils/apiVersion.ts``; the storefront via
    ``surfaces/storefront-nuxt/server/utils/apiVersion.ts``). Applied to the
    whole versioned API (`/api/v1/`, storefront and backstage); OpenAPI
    schema/docs and core-app APIs are unaffected.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(API_V1_PREFIX):
            response["X-API-Version"] = API_VERSION
        return response


class OperatorSessionDomainMiddleware:
    """Scope the session/CSRF cookies to the operator zone's parent domain.

    The operator apps (gestor./kds./pdv./prod.) live on a registrable domain
    SEPARATE from the customer store, so one login works across all of them while
    the cookie stays physically isolated from the public store (OPERATOR-AUTH-PLAN,
    Opção A). One Django serves both audiences, so ``SESSION_COOKIE_DOMAIN`` cannot
    be set globally (it would break the customer's host-only session). Instead, this
    middleware rewrites the cookie ``Domain`` only when the request is served on the
    operator API host — keying on ``request.get_host()`` (the operator apps proxy to
    ``SHOPMAN_OPERATOR_API_HOST``; the proxy rewrites Host to that alias).

    Feature-gated: with ``SHOPMAN_OPERATOR_COOKIE_DOMAIN`` empty (default), it is a
    no-op and the current host-only behaviour is preserved for everyone.

    Placed high in ``MIDDLEWARE`` so its response phase runs AFTER Session/CSRF
    middleware have written their cookies. Settings are read per-request so
    ``override_settings`` works in tests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        cookie_domain = (getattr(settings, "SHOPMAN_OPERATOR_COOKIE_DOMAIN", "") or "").strip()
        if not cookie_domain:
            return response
        if not self._is_operator_host(request, cookie_domain):
            return response
        for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
            if name in response.cookies:
                response.cookies[name]["domain"] = cookie_domain
        return response

    @staticmethod
    def _is_operator_host(request, cookie_domain: str) -> bool:
        host = request.get_host().split(":")[0].lower()
        api_host = (getattr(settings, "SHOPMAN_OPERATOR_API_HOST", "") or "").strip().lower()
        if api_host and host == api_host:
            return True
        # ⚠️ O ADMIN NÃO É DA ZONA DE OPERADOR, apesar do sufixo. Ele mora em
        # `admin.boulangerie.com.br`, que TERMINA em `.boulangerie.com.br` e por
        # isso casava na regra de sufixo abaixo — a sessão do Admin saía com
        # `Domain=.boulangerie.com.br` e era enviada aos 9 subdomínios de
        # operador sem precisar. Isso é colateral de cronologia, não desenho: o
        # middleware nasceu em 25/06 (WP-AUTH-1), quando a zona de operador era
        # `.boulangerie.com.br` e o Admin não morava lá; o host `admin.` foi
        # criado em 15/08 e herdou o sufixo em silêncio. Sessão de Admin é
        # host-only, como a do cliente.
        admin_host = (getattr(settings, "SHOPMAN_ADMIN_HOST", "") or "").strip().lower()
        if admin_host and host == admin_host:
            return False
        bare = cookie_domain.lstrip(".").lower()
        return host == bare or host.endswith("." + bare)
