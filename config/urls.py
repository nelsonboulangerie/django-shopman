"""URL configuration for the Shopman project."""

import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from shopman.backstage.admin_console.cash_receipt import cash_receipt_verify_view
from shopman.backstage.admin_console.copy_catalog import copy_catalog_view
from shopman.backstage.admin_console.operator_badge import operator_badge_view
from shopman.backstage.admin_console.pos_counter_agent import (
    pos_counter_agent_download,
    pos_counter_agent_view,
)
from shopman.backstage.admin_console.settings_hub import settings_hub_view
from shopman.backstage.views.two_factor import admin_2fa_verify
from shopman.shop.views.admin_host import admin_host_root
from shopman.shop.views.health import HealthCheckView, ReadyCheckView

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

urlpatterns += _include_optional("api/auth/", "shopman.doorman.api.urls")
urlpatterns += _include_optional("auth/", "shopman.doorman.urls")

urlpatterns += _include_optional("api/webhooks/", "shopman.shop.webhooks.urls")
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

# Fiscal — DANFE NFC-e (cupom de operador, imprimível). Gated a staff na view.
urlpatterns += _include_optional("", "shopman.shop.fiscal_urls")

# ── Media files (dev only) ────────────────────────────────────────

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
