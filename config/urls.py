"""URL configuration for the Shopman project."""

import functools
import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import Http404, HttpResponse
from django.middleware.csrf import get_token
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from shopman.doorman.views.access_link import AccessLinkCreateView, AccessLinkExchangeView

from shopman.backstage.admin_console.cash_receipt import cash_receipt_verify_view
from shopman.backstage.admin_console.copy_catalog import copy_catalog_view
from shopman.backstage.admin_console.diagnostics import diagnostics_view
from shopman.backstage.admin_console.operator_badge import operator_badge_view
from shopman.backstage.admin_console.pos_counter_agent import (
    pos_counter_agent_download,
    pos_counter_agent_view,
)
from shopman.backstage.admin_console.settings_hub import settings_hub_view
from shopman.backstage.views.admin_login import admin_login
from shopman.backstage.views.two_factor import admin_2fa_enroll, admin_2fa_verify
from shopman.shop.views.admin_host import admin_host_root
from shopman.shop.views.health import DatabaseReadyView, HealthCheckView, ReadyCheckView

logger = logging.getLogger(__name__)

# No custom handler404: the legacy operator shell (gestor/base.html + gestor/404.html)
# was retired with the production app cutover (OPERATOR-APPS-PLAN Fase 4). Operator
# surfaces are dedicated Nuxt apps; Django serves the API + Admin (which has its own
# 404). Django's default handler covers the rest.


def _include_optional(route: str, module: str):
    """Include a URL module, logging a warning if it fails to import."""
    try:
        return [path(route, include(module))]
    except ImportError:
        logger.warning("Optional URL module %s not found, skipping.", module)
        return []


urlpatterns = [
    # Health / readiness probes — público, sem auth, no topo para precedência.
    path("health/live/", HealthCheckView.as_view(), name="health-live"),
    path("health/ready/", ReadyCheckView.as_view(), name="health-ready"),
    path("health/database/", DatabaseReadyView.as_view(), name="health-database"),
    # O ingress público divide os dois processos Django por path. Estes aliases
    # caem no web-storefront (`/api/v1`); as rotas acima caem no web-operator.
    # Assim o monitor externo mede cada processo, não duas URLs do mesmo processo.
    path("api/v1/health/live/", HealthCheckView.as_view(), name="storefront-health-live"),
    path("api/v1/health/ready/", ReadyCheckView.as_view(), name="storefront-health-ready"),
    # Compatibility aliases while external monitors move to the explicit paths.
    path("health/", HealthCheckView.as_view(), name="health"),
    path("ready/", ReadyCheckView.as_view(), name="ready"),
    # Pedidos migraram p/ o app Nuxt dedicado (Gestor — surfaces/orders-nuxt)
    # via api/v1/backstage/orders/*; o console Admin de pedidos foi removido
    # (OPERATOR-APPS-PLAN Fase 2). O console Admin de produção saiu no
    # WP-ADM-7d: a superfície canônica é o Produção (surfaces/production-nuxt)
    # via api/v1/backstage/production/* (paridade fechada no WP-ADM-7b).
    path(
        "admin/settings/",
        admin.site.admin_view(settings_hub_view),
        name="admin_console_settings_hub",
    ),
    # ⚠️ ANTES do padrão <slug> abaixo: "copy" cairia no conversor de escopo e
    # abriria uma tela de configuração vazia em vez do catálogo de textos.
    path(
        "admin/settings/copy/",
        admin.site.admin_view(copy_catalog_view),
        name="admin_console_copy_catalog",
    ),
    # Diagnóstico das integrações. Vive fora de settings/<slug> de propósito:
    # não é uma configuração que se ajusta, é uma pergunta que se faz.
    path(
        "admin/diagnostics/",
        admin.site.admin_view(diagnostics_view),
        name="admin_console_diagnostics",
    ),
    path(
        "admin/pos/terminal/<slug:ref>/agent/",
        admin.site.admin_view(pos_counter_agent_view),
        name="admin_console_pos_counter_agent",
    ),
    path(
        "admin/pos/terminal/<slug:ref>/agent/counter_agent.py",
        admin.site.admin_view(pos_counter_agent_download),
        name="admin_console_pos_counter_agent_download",
    ),
    path(
        "admin/cash/receipt/<str:code>/",
        admin.site.admin_view(cash_receipt_verify_view),
        name="admin_console_cash_receipt",
    ),
    path(
        "admin/cash/receipt/",
        admin.site.admin_view(cash_receipt_verify_view),
        name="admin_console_cash_receipt_lookup",
    ),
    path(
        "admin/operators/badge/",
        admin.site.admin_view(operator_badge_view),
        name="admin_console_operator_badge",
    ),
    path(
        "admin/settings/<slug:slug>/",
        admin.site.admin_view(settings_hub_view),
        name="admin_console_settings_scope",
    ),
    path("admin/2fa/verify/", admin_2fa_verify, name="admin_2fa_verify"),
    path("admin/2fa/enroll/", admin_2fa_enroll, name="admin_2fa_enroll"),
    # Antes do `admin.site.urls`: a senha do Admin passa pelo mesmo freio de
    # tentativas do login de operador (ver `backstage/views/admin_login.py`).
    path("admin/login/", admin_login),
    path("admin/", admin.site.urls),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # A raiz do host do Admin cai no Admin — `admin.…/admin` é redundante.
    # `path("")` casa SÓ a raiz exata, então não sombreia as rotas do backstage
    # logo abaixo.
    path("", admin_host_root),
    path("", include("shopman.backstage.urls")),
]


# ── O Admin só responde no host do Admin ───────────────────────────
#
# Um Django serve todos os hosts. Sem esta trava, `/admin/` respondia também em
# `api.`, e lá a sessão do login sai com `Domain=.boulangerie.com.br` (o
# `OperatorSessionDomainMiddleware` reescreve o cookie no host da API): a sessão
# de superusuário viajava para os nove subdomínios de operador (laudo S4, 23/10).
#
# Com `SHOPMAN_ADMIN_HOST` configurado, toda rota `admin/…` fora dele é 404. A
# única exceção é `GET /admin/login/`, que o BFF dos apps de operador usa para
# inicializar o cookie de CSRF (`operator-kit/server/utils/djangoProxy.ts`): fora
# do host do Admin ele devolve só o cookie (204), sem formulário e sem aceitar
# POST. Sem a setting (dev local), nada muda.
_CSRF_BOOTSTRAP_PATH = "/admin/login/"


def _is_admin_host(request) -> bool:
    canonical = (getattr(settings, "SHOPMAN_ADMIN_HOST", "") or "").strip().lower()
    if not canonical:
        return True
    return request.get_host().split(":")[0].lower() == canonical


def _admin_host_only(view):
    @functools.wraps(view)
    def guarded(request, *args, **kwargs):
        if _is_admin_host(request):
            return view(request, *args, **kwargs)
        if request.method in ("GET", "HEAD") and request.path_info == _CSRF_BOOTSTRAP_PATH:
            get_token(request)
            return HttpResponse(status=204)
        raise Http404

    return guarded


def _confine_to_admin_host(patterns):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            _confine_to_admin_host(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            pattern.callback = _admin_host_only(pattern.callback)


_confine_to_admin_host(p for p in urlpatterns if str(p.pattern).startswith("admin/"))

# ── Core APIs ──────────────────────────────────────────────────────
#
# Os ViewSets de CRUD dos pacotes do kernel (orderman, offerman, stockman,
# craftsman, guestman) NÃO são montados no deployment. Eles herdam o
# default DRF `IsAuthenticated`, e clientes do storefront viram usuários Django
# autenticados (login OTP chama `login()`), então expô-los deixaria qualquer
# cliente logado ler/mutar dados do kernel — sessões e comandas do POS, base de
# PII, ledger de estoque, BOM (segredo de negócio). Nenhuma
# superfície os consome: os apps Nuxt entram por `api/v1/` (storefront) e
# `api/v1/backstage/` (projections gateadas por permissão). Guardrail que trava
# a re-introdução: shopman/shop/tests/test_api_perimeter.py.
#
# O `payman` não aparece na lista porque não tem mais pacote `api/`: pagamento
# não tem consumidor por HTTP direto (Admin + reconciliação do backstage dão
# conta), e código de superfície pública sem trava é brecha esperando tomada.
#
# Se um desses ganhar consumidor real, ele volta COM permissão explícita
# (IsAdminUser/DjangoModelPermissions) e o guardrail é atualizado deliberadamente.

# Do doorman, o deployment monta DUAS rotas, cada uma com consumidor nomeado:
#
# - `api/auth/access/create/`: a ponte do ManyChat. O External Request do flow
#   chama servidor a servidor com `ACCESS_LINK_API_KEY` (docs/guides/
#   whatsapp-access-link.md).
# - `auth/access/` (`doorman:access-exchange`): a entrada de reserva do
#   `AccessLinkService._build_url` quando `ACCESS_LINK_ENTRY_URL` está vazio
#   (suíte de testes, dev local sem loja). Com a loja configurada, como em todo
#   ambiente vivo, o link emitido é `{loja}/a?t=` e a troca é POST.
#
# O resto de `shopman.doorman.urls` e `shopman.doorman.api.urls` (OTP por
# `api/auth/request-code|verify-code` e `auth/code/*`, pedido de link por
# e-mail, dispositivos, logout, health) era uma segunda porta de login ao lado
# da loja, sem o rate limit por IP e o `csrf_protect` que `api/v1/auth/*` tem,
# e nenhuma superfície a chamava: a loja entra por `api/v1/auth/` (BFF Nuxt).
# Guardrail: shopman/shop/tests/test_api_perimeter.py.
urlpatterns += [
    path("api/auth/access/create/", AccessLinkCreateView.as_view(), name="auth-access-create"),
    path(
        "auth/",
        include(
            (
                [path("access/", AccessLinkExchangeView.as_view(), name="access-exchange")],
                "doorman",
            )
        ),
    ),
]

urlpatterns += _include_optional("api/webhooks/", "shopman.shop.webhooks.urls")
# Concierge de WhatsApp (superfície de cliente): /api/webhooks/manychat/conversation/
urlpatterns += _include_optional("api/webhooks/", "shopman.storefront.concierge.urls")
# ManyChat inbound webhook (subscriber sync). HMAC + replay gated; without
# MANYCHAT_WEBHOOK_SECRET it fails CLOSED outside DEBUG (rejects unsigned payloads);
# only local dev (DEBUG) skips the signature. The conversational ORDER flow
# (intent/confirm endpoints) is owned by MANYCHAT-CONVERSACIONAL-PLAN, not this route.
urlpatterns += _include_optional(
    "api/webhooks/manychat/", "shopman.guestman.contrib.manychat.urls"
)
urlpatterns += _include_optional("api/v1/", "shopman.storefront.api.urls")
urlpatterns += _include_optional("api/v1/backstage/", "shopman.backstage.api.urls")

# Menuboard — superfície display pública (quadro-negro numa TV), tempo real via SSE.
urlpatterns += _include_optional("", "shopman.shop.menuboard_urls")

# Fiscal — DANFE NFC-e (cupom de operador, imprimível). Gated por permissão de pedidos ou de caixa na view.
urlpatterns += _include_optional("", "shopman.shop.fiscal_urls")

# ── Media files (dev only) ────────────────────────────────────────

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
