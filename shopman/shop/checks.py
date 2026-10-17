"""
Django system checks for Shopman.

Registered in ShopmanConfig.ready() via checks.register().

Errors (block runserver/migrate --deploy in production):
  SHOPMAN_E001  SECRET_KEY is the development default
  SHOPMAN_E002  ALLOWED_HOSTS is empty or contains '*'
  SHOPMAN_E003  PIX or CARD payment adapter is missing or payment_mock without explicit staging allowance
  SHOPMAN_E004  A webhook integration has no token configured
  SHOPMAN_E006  Shared Redis cache is not configured
  SHOPMAN_E007  Database backend is SQLite in production
  SHOPMAN_E008  Doorman access-link API key is not configured
  SHOPMAN_E009  Real payment adapter is missing required credentials/files
  SHOPMAN_E011  Machine courier adapter enabled without API credentials
  SHOPMAN_E012  Piloto automático de staging habilitado em produção
  SHOPMAN_E013  Adapter fiscal + canal de venda ativo sem resolver de emissão que resolva
  SHOPMAN_E014  Operator subdomain zone configured without shared cookie scope
  SHOPMAN_E015  Captura simulada exposta fora de ambiente não produtivo
  SHOPMAN_E016  Catálogo de qualidade não tem exatamente um grau padrão ativo
  SHOPMAN_E017  Catálogo de qualidade não tem grau ativo a preço cheio
  SHOPMAN_E018  Catálogo de qualidade tem política ativa incoerente
  SHOPMAN_E019  Configuração de produção da loja é inválida
  SHOPMAN_W020  WhatsApp Marketing com flow ainda fechado ou em ensaio (o envio já falha fechado em runtime)
  SHOPMAN_E021  Allowlist de mídia Marketing contém host inseguro
  SHOPMAN_E022  Provedor de produção aponta para ambiente ou credencial de teste
  SHOPMAN_E023  Google Maps exige credenciais de browser e servidor separadas em produção
  SHOPMAN_E024  Configuração VAPID parcial ou inválida
  SHOPMAN_E025  Chave HMAC dos recibos de privacidade ausente ou inválida
  SHOPMAN_E026  Ambiente de cobrança (EFI_SANDBOX) ou fiscal (FOCUS_NFE_ENVIRONMENT) não declarado em produção
  SHOPMAN_E027  Dinheiro ou nota de verdade com porta de teste aberta (em qualquer ambiente)

Warnings (non-blocking, logged at startup):
  SHOPMAN_W001  Database backend is SQLite in local/debug mode
  SHOPMAN_W002  Notification backend is console while DEBUG=False
  SHOPMAN_W003  Store offers NFC-e at the counter but no fiscal adapter is configured
  SHOPMAN_W004  Listing.ref has no matching Channel.ref
  SHOPMAN_W005  OFFERMAN pricing backend not configured
  SHOPMAN_W006  Mock payment adapter explicitly allowed outside DEBUG
  SHOPMAN_W008  iFood webhook token is not configured (integration webhook unauthenticated)
  SHOPMAN_W009  Manychat webhook secret is not configured
  SHOPMAN_W010  Machine courier enabled without webhook token (status via polling only)
  SHOPMAN_W011  Piloto automático de staging ligado (pedidos andam sozinhos)
  SHOPMAN_W012  Display channel has no valid display.prices_from pointer
  SHOPMAN_W013  Publicly tracked channel takes price from a non-public channel
  SHOPMAN_W014  Active WhatsApp campaign without an approved template (flow ns)
  SHOPMAN_W015  SKU com cadastro de venda e de compra em unidades diferentes
  SHOPMAN_W016  Captura simulada exposta em staging técnico
  SHOPMAN_W017  SHOPMAN_ENVIRONMENT com valor irreconhecível (tratado como produção)
  SHOPMAN_W018  Botão "Simular pagamento" e auto-confirm do Pix mock ligados juntos
  SHOPMAN_W019  Web Push do backstage desativado por ausência de VAPID
  SHOPMAN_W021  Modo do WhatsApp de Marketing pedido sem cache compartilhado, sem lista do ensaio ou desconhecido

Os avisos do Concierge (W022 e W023) moram em ``shopman/storefront/checks.py``,
porque o shop não importa superfície. O próximo id livre aqui é o W024.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Warning, register
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from shopman.shop.cache import is_redis_cache_backend
from shopman.shop.environment import (
    NON_PRODUCTION_ENVIRONMENTS,
    environment_name,
    is_production,
    is_recognized_environment,
)

_DEV_SECRET_KEY = "dev-secret-key-not-for-production"


@register(deploy=True)
def check_secret_key(app_configs, **kwargs):
    errors = []
    if not settings.DEBUG:
        key = getattr(settings, "SECRET_KEY", "")
        if key == _DEV_SECRET_KEY or not key:
            errors.append(
                Error(
                    "SECRET_KEY está no valor default de desenvolvimento.",
                    hint="Defina DJANGO_SECRET_KEY com um valor aleatório seguro via variável de ambiente.",
                    id="SHOPMAN_E001",
                )
            )
    return errors


@register(deploy=True)
def check_allowed_hosts(app_configs, **kwargs):
    errors = []
    if not settings.DEBUG:
        hosts = getattr(settings, "ALLOWED_HOSTS", [])
        if not hosts or "*" in hosts:
            errors.append(
                Error(
                    "ALLOWED_HOSTS está vazio ou contém '*' em produção.",
                    hint="Defina DJANGO_ALLOWED_HOSTS com os domínios reais da aplicação.",
                    id="SHOPMAN_E002",
                )
            )
    return errors


@register(deploy=True)
def check_payment_adapters(app_configs, **kwargs):
    messages = []
    if settings.DEBUG:
        return messages

    adapters = getattr(settings, "SHOPMAN_PAYMENT_ADAPTERS", {}) or {}
    allow_mock = bool(getattr(settings, "SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", False))
    for method in ("pix", "card"):
        path = adapters.get(method, "")
        if not path:
            messages.append(
                Error(
                    f"Adapter de pagamento para método '{method}' não está configurado fora de DEBUG.",
                    hint=f"Defina SHOPMAN_{method.upper()}_ADAPTER com um adapter real ou habilite mock explicitamente em staging técnico.",
                    id="SHOPMAN_E003",
                )
            )
            continue

        if "payment_mock" in path:
            if allow_mock:
                messages.append(
                    Warning(
                        f"Adapter de pagamento para método '{method}' está usando payment_mock fora de DEBUG.",
                        hint=(
                            "Isto só é aceitável em staging/teste operacional sem credenciais sandbox reais. "
                            "Antes de go-live, remova SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS e configure o gateway real."
                        ),
                        id="SHOPMAN_W006",
                    )
                )
            else:
                messages.append(
                    Error(
                        f"Adapter de pagamento para método '{method}' aponta para payment_mock fora de DEBUG.",
                        hint=(
                            f"Defina SHOPMAN_{method.upper()}_ADAPTER com um adapter real "
                            "ou habilite SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=true apenas em staging técnico."
                        ),
                        id="SHOPMAN_E003",
                    )
                )
            continue

        if "payment_efi" in path:
            messages.extend(_check_efi_payment_credentials(method=method))
        if "payment_stripe" in path:
            messages.extend(_check_stripe_payment_credentials(method=method))
    return messages


def _check_efi_payment_credentials(*, method: str):
    cfg = getattr(settings, "SHOPMAN_EFI", {}) or {}
    missing = []
    for key, label in (
        ("client_id", "EFI_CLIENT_ID"),
        ("client_secret", "EFI_CLIENT_SECRET"),
        ("certificate_path", "EFI_CERTIFICATE_PATH"),
        ("pix_key", "EFI_PIX_KEY"),
    ):
        if not cfg.get(key):
            missing.append(label)

    certificate_path = cfg.get("certificate_path")
    if certificate_path and not os.path.exists(certificate_path):
        missing.append("EFI_CERTIFICATE_PATH arquivo existente no container")

    if not missing:
        return []

    return [
        Error(
            f"Adapter EFI configurado para '{method}', mas credenciais/arquivos obrigatórios estão ausentes.",
            hint="Configure: " + ", ".join(missing) + ".",
            id="SHOPMAN_E009",
        )
    ]


def _check_stripe_payment_credentials(*, method: str):
    cfg = getattr(settings, "SHOPMAN_STRIPE", {}) or {}
    missing = []
    if not cfg.get("secret_key"):
        missing.append("STRIPE_SECRET_KEY")
    if not cfg.get("webhook_secret"):
        missing.append("STRIPE_WEBHOOK_SECRET")

    if not missing:
        return []

    return [
        Error(
            f"Adapter Stripe configurado para '{method}', mas credenciais obrigatórias estão ausentes.",
            hint="Configure: " + ", ".join(missing) + ".",
            id="SHOPMAN_E009",
        )
    ]


@register(deploy=True)
def check_webhook_tokens(app_configs, **kwargs):
    """Validate inbound-integration webhook tokens.

    Every endpoint already fails CLOSED without a token (rejects all requests —
    there is no bypass). The severity here reflects the CONSEQUENCE of a missing
    token, not a security risk:

    - EFI (``critical=True``) → **Error**: the PIX confirmation webhook is in
      active use; without the token real payments silently never confirm. Block
      the deploy.
    - iFood (``critical=False``) → **Warning**: fail-closed, mas NÃO é "opcional"
      se você recebe pedidos por webhook. ``/api/webhooks/ifood/`` ingere o pedido
      no canal iFood; sem o token, TODO callback do iFood toma 401 e nenhum pedido
      entra. É Warning (não Error) só porque um deployment que não usa iFood deve
      poder subir sem ele — mas se usa, este token é obrigatório.
    """
    messages = []
    if settings.DEBUG:
        return messages

    # (settings_attr, persona, env_var, critical)
    integrations = [
        ("SHOPMAN_EFI_WEBHOOK", "EFI", "EFI_WEBHOOK_TOKEN", True),
        ("SHOPMAN_IFOOD", "iFood", "IFOOD_WEBHOOK_TOKEN", False),
    ]
    for attr, name, env_var, critical in integrations:
        cfg = getattr(settings, attr, {}) or {}
        if cfg.get("webhook_token"):
            continue
        if critical:
            messages.append(
                Error(
                    f"{attr}['webhook_token'] não está configurado em produção.",
                    hint=(
                        f"{name} confirma pagamento real via webhook; sem o token "
                        f"a confirmação nunca chega e o pagamento trava. Defina "
                        f"{env_var} via variável de ambiente."
                    ),
                    id="SHOPMAN_E004",
                )
            )
        else:
            messages.append(
                Warning(
                    f"{attr}['webhook_token'] não configurado — o webhook {name} "
                    f"(/api/webhooks/ifood/) rejeita TODO callback com 401.",
                    hint=(
                        f"Se você recebe pedidos {name} por webhook, eles NÃO entram "
                        f"sem este token — o endpoint ingere o pedido no canal {name}, "
                        f"mas sem {env_var} (igual ao configurado no portal {name}) "
                        f"todo callback toma 401. Defina {env_var}. Deixe vazio só se "
                        f"não usa o webhook {name}."
                    ),
                    id="SHOPMAN_W008",
                )
            )
    return messages


@register()
def check_database_backend(app_configs, **kwargs):
    messages = []
    default_db = settings.DATABASES.get("default", {})
    engine = default_db.get("ENGINE", "")
    if "sqlite3" in engine:
        if settings.DEBUG:
            messages.append(
                Warning(
                    "O banco de dados padrão é SQLite.",
                    hint="SQLite não suporta operações concorrentes adequadamente. Use PostgreSQL em produção.",
                    id="SHOPMAN_W001",
                )
            )
        else:
            messages.append(
                Error(
                    "O banco de dados padrão é SQLite fora do modo DEBUG.",
                    hint="Defina DATABASE_URL com PostgreSQL antes de qualquer ambiente público.",
                    id="SHOPMAN_E007",
                )
            )
    return messages


@register()
def check_notification_backend(app_configs, **kwargs):
    warnings = []
    if not settings.DEBUG:
        adapters = getattr(settings, "SHOPMAN_NOTIFICATION_ADAPTERS", {})
        if not adapters:
            return warnings
        for method, path in adapters.items():
            if path and "notification_console" in path:
                warnings.append(
                    Warning(
                        f"Adapter de notificação para '{method}' é console fora do modo DEBUG.",
                        hint="Configure SHOPMAN_NOTIFICATION_ADAPTERS com um backend real (email, SMS, WhatsApp).",
                        id="SHOPMAN_W002",
                    )
                )
    return warnings


@register(deploy=True)
def check_guestman_webhook_secret(app_configs, **kwargs):
    """ManyChat inbound webhook secret.

    O endpoint falha FECHADO sem a secret (rejeita payloads não assinados — ver
    guestman Gates.provider_event_authenticity com allow_unsigned=DEBUG). Logo,
    faltar a secret NÃO é insegurança: só desativa o sync inbound de assinantes.
    Warning (não bloqueia o deploy) — configure só se usar o fluxo inbound.
    """
    messages = []
    if not settings.DEBUG:
        secret = getattr(settings, "MANYCHAT_WEBHOOK_SECRET", "")
        if not secret:
            messages.append(
                Warning(
                    "MANYCHAT_WEBHOOK_SECRET não configurado — webhook inbound do ManyChat inativo (rejeita tudo).",
                    hint=(
                        "Sem a secret o endpoint falha fechado (seguro). Defina "
                        "MANYCHAT_WEBHOOK_SECRET (mesmo valor no webhook do ManyChat) "
                        "apenas se usar o sync inbound de assinantes."
                    ),
                    id="SHOPMAN_W009",
                )
            )
    return messages


@register(deploy=True)
def check_courier_credentials(app_configs, **kwargs):
    """Machine courier: credenciais obrigatórias quando o adapter real está ligado.

    Fora do check_webhook_tokens porque a severidade é condicional ao adapter:
    sem SHOPMAN_COURIER_ADAPTER apontando para courier_machine, nada aqui se
    aplica (deployment sem courier sobe limpo). Com o adapter ligado:
    - sem username/password/api_key → Error (todo despacho automático falharia);
    - sem webhook_token → Warning (o polling cobre o status, com latência).
    """
    messages = []
    if settings.DEBUG:
        return messages

    adapter_path = getattr(settings, "SHOPMAN_COURIER_ADAPTER", None) or ""
    if "courier_machine" not in adapter_path:
        return messages

    cfg = getattr(settings, "SHOPMAN_MACHINE", {}) or {}
    missing = [
        env
        for key, env in (
            ("username", "MACHINE_API_USER"),
            ("password", "MACHINE_API_PASSWORD"),
            ("api_key", "MACHINE_API_KEY"),
        )
        if not cfg.get(key)
    ]
    if missing:
        messages.append(
            Error(
                f"SHOPMAN_COURIER_ADAPTER aponta para courier_machine sem credenciais: faltam {', '.join(missing)}.",
                hint=(
                    "O despacho automático de entregadores falharia em toda corrida. "
                    "Defina as variáveis de ambiente da Machine ou remova "
                    "SHOPMAN_COURIER_ADAPTER."
                ),
                id="SHOPMAN_E011",
            )
        )
    if not cfg.get("webhook_token"):
        messages.append(
            Warning(
                "SHOPMAN_MACHINE['webhook_token'] não configurado — status da corrida "
                "só por polling (latência de até courier_poll_seconds).",
                hint=(
                    "Defina MACHINE_WEBHOOK_TOKEN e cadastre o endpoint com "
                    "`manage.py machine_register_webhook` para receber status em push."
                ),
                id="SHOPMAN_W010",
            )
        )
    return messages


@register(deploy=True)
def check_doorman_access_link_api_key(app_configs, **kwargs):
    errors = []
    if settings.DEBUG:
        return errors

    doorman = getattr(settings, "DOORMAN", {}) or {}
    if not doorman.get("ACCESS_LINK_API_KEY"):
        errors.append(
            Error(
                "DOORMAN['ACCESS_LINK_API_KEY'] não está configurado em produção.",
                hint=(
                    "Defina DOORMAN_ACCESS_LINK_API_KEY. O endpoint de criação "
                    "de access links é CSRF-exempt por ser integração servidor-servidor "
                    "e deve falhar fechado fora de DEBUG."
                ),
                id="SHOPMAN_E008",
            )
        )
    return errors


@register(deploy=True)
def check_operator_cookie_domain(app_configs, **kwargs):
    """Operator apps published on subdomains need a shared operator cookie scope."""
    errors = []
    if settings.DEBUG:
        return errors

    api_host = str(getattr(settings, "SHOPMAN_OPERATOR_API_HOST", "") or "").strip().lower()
    cookie_domain = str(getattr(settings, "SHOPMAN_OPERATOR_COOKIE_DOMAIN", "") or "").strip().lower()
    registry = json.loads(
        (Path(__file__).resolve().parents[2] / "surfaces" / "registry.json").read_text(encoding="utf-8")
    )
    bare_domain = cookie_domain.lstrip(".")
    operator_base_urls: dict[str, str] = {}
    for surface_id, surface in registry["surfaces"].items():
        if surface.get("kind") != "operator" or surface.get("deployment") != "digitalocean":
            continue
        env = surface.get("base_url_env")
        value = str(getattr(settings, env, "") or "") if env else ""
        # A Central não tem base_url_env porque não lista a si mesma. Seu host
        # ainda pertence à sessão comum e é derivado da topologia declarada.
        if not value and surface.get("subdomain") and bare_domain:
            value = f"https://{surface['subdomain']}.{bare_domain}"
        operator_base_urls[surface_id] = value
    configured_urls = {key: value for key, value in operator_base_urls.items() if value}

    if not configured_urls and not api_host and not cookie_domain:
        return errors

    if configured_urls and not api_host:
        errors.append(
            Error(
                "Superfícies operacionais publicadas sem SHOPMAN_OPERATOR_API_HOST.",
                hint=(
                    "Defina SHOPMAN_OPERATOR_API_HOST para o host de API que os apps Nuxt "
                    "de operador usam como upstream, ex.: api.boulangerie.com.br."
                ),
                id="SHOPMAN_E014",
            )
        )
    if (configured_urls or api_host) and not cookie_domain:
        errors.append(
            Error(
                "Zona operacional publicada sem SHOPMAN_OPERATOR_COOKIE_DOMAIN.",
                hint=(
                    "Defina SHOPMAN_OPERATOR_COOKIE_DOMAIN com o domínio-pai dos apps "
                    "operacionais, ex.: .boulangerie.com.br. Sem isso, login/CSRF ficam "
                    "host-only e quebram ao alternar entre gestor, KDS, PDV e produção."
                ),
                id="SHOPMAN_E014",
            )
        )
        return errors

    invalid_hosts = []
    for key, value in configured_urls.items():
        host = (urlparse(str(value)).hostname or "").lower()
        if host and host != bare_domain and not host.endswith("." + bare_domain):
            invalid_hosts.append(f"{key}={host}")

    if api_host and api_host != bare_domain and not api_host.endswith("." + bare_domain):
        invalid_hosts.append(f"SHOPMAN_OPERATOR_API_HOST={api_host}")

    if invalid_hosts:
        errors.append(
            Error(
                "Host operacional fora de SHOPMAN_OPERATOR_COOKIE_DOMAIN.",
                hint=(
                    "Todos os hosts de operador precisam estar sob o domínio-pai do cookie "
                    f"({cookie_domain}): " + ", ".join(invalid_hosts)
                ),
                id="SHOPMAN_E014",
            )
        )
    return errors


@register(deploy=True)
def check_staging_autopilot(app_configs, **kwargs):
    """O piloto automático move pedidos sozinho — só fora de produção.

    Em produção isto avançaria pedido de cliente de verdade sem ninguém ter
    encostado (cobrando, baixando estoque, emitindo nota). É erro de boot, não
    aviso.
    """
    messages = []
    if not getattr(settings, "SHOPMAN_STAGING_AUTOPILOT", False):
        return messages

    if is_production():
        messages.append(
            Error(
                "SHOPMAN_STAGING_AUTOPILOT está habilitado fora de ambiente não produtivo.",
                hint=(
                    "Desabilite SHOPMAN_STAGING_AUTOPILOT. Em produção ele avançaria pedidos "
                    "de clientes reais sem operador — cobrando, baixando estoque e emitindo nota."
                ),
                id="SHOPMAN_E012",
            )
        )
    else:
        messages.append(
            Warning(
                "Piloto automático de staging ligado: pedidos avançam sozinhos até 'concluído'.",
                hint=(
                    "Só para staging/dev, onde o testador não tem cozinha nem gestor do outro "
                    "lado. Remova SHOPMAN_STAGING_AUTOPILOT antes do go-live."
                ),
                id="SHOPMAN_W011",
            )
        )
    return messages


@register(deploy=True)
def check_mock_capture_exposure(app_configs, **kwargs):
    """O botão "Simular pagamento" é ferramenta de teste, não de venda.

    O adapter mock em staging responde "este ambiente usa gateway simulado". Já
    ``SHOPMAN_EXPOSE_MOCK_CAPTURE`` responde outra pergunta: "o cliente consegue
    clicar e marcar o pedido como pago?". A segunda só pode existir em staging
    técnico acompanhado. Em produção, isto seria captura local sem dinheiro no
    gateway.
    """
    messages = []
    if settings.DEBUG or not getattr(settings, "SHOPMAN_EXPOSE_MOCK_CAPTURE", False):
        return messages

    if is_production():
        messages.append(
            Error(
                "SHOPMAN_EXPOSE_MOCK_CAPTURE está habilitado fora de ambiente não produtivo.",
                hint=(
                    "Desabilite SHOPMAN_EXPOSE_MOCK_CAPTURE antes de produção. "
                    "Esse botão captura intents locais do gateway mock e não representa "
                    "dinheiro recebido no provedor real."
                ),
                id="SHOPMAN_E015",
            )
        )
    else:
        messages.append(
            Warning(
                "Captura simulada exposta em ambiente não-DEBUG.",
                hint=(
                    "Permitido apenas para rodada acompanhada de alpha/staging técnico. "
                    "Desligue SHOPMAN_EXPOSE_MOCK_CAPTURE ao encerrar testes humanos e "
                    "antes de qualquer go-live."
                ),
                id="SHOPMAN_W016",
            )
        )
    return messages


@register(deploy=True)
def check_mock_pix_confirm_conflict(app_configs, **kwargs):
    """As duas confirmações do Pix mock juntas se contradizem — e o relógio ganha.

    ``SHOPMAN_EXPOSE_MOCK_CAPTURE`` promete o botão "Simular pagamento";
    ``SHOPMAN_MOCK_PIX_AUTO_CONFIRM`` confirma sozinho em segundos. Ligadas ao
    mesmo tempo, o auto-confirm sempre vence a corrida e o botão nem chega a
    aparecer. O código já resolve (com o botão exposto, o auto-confirm não é
    injetado — ver ``_adapter_config`` em services/payment.py); este aviso
    existe para a config parar de mentir.
    """
    messages = []
    if getattr(settings, "SHOPMAN_EXPOSE_MOCK_CAPTURE", False) and getattr(
        settings, "SHOPMAN_MOCK_PIX_AUTO_CONFIRM", False
    ):
        messages.append(
            Warning(
                "SHOPMAN_EXPOSE_MOCK_CAPTURE e SHOPMAN_MOCK_PIX_AUTO_CONFIRM estão ligados juntos; "
                "o botão manual vence e o auto-confirm do Pix mock é ignorado.",
                hint=(
                    'Escolha um: botão "Simular pagamento" (SHOPMAN_EXPOSE_MOCK_CAPTURE) ou '
                    "confirmação automática (SHOPMAN_MOCK_PIX_AUTO_CONFIRM). "
                    "Desligue SHOPMAN_MOCK_PIX_AUTO_CONFIRM para silenciar este aviso."
                ),
                id="SHOPMAN_W018",
            )
        )
    return messages


@register(deploy=True)
def check_shared_cache_backend(app_configs, **kwargs):
    errors = []
    if settings.DEBUG:
        return errors

    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if not is_redis_cache_backend(backend):
        errors.append(
            Error(
                "Cache compartilhado Redis não está configurado em produção.",
                hint=(
                    "Defina REDIS_URL. O Shopman usa cache compartilhado para "
                    "django-ratelimit, caches operacionais curtos e fanout SSE "
                    "multi-worker via django-eventstream."
                ),
                id="SHOPMAN_E006",
            )
        )
    return errors


@register()
def check_pricing_backend(app_configs, **kwargs):
    warnings = []
    if not settings.DEBUG:
        offerman = getattr(settings, "OFFERMAN", {}) or {}
        if not offerman.get("PRICING_BACKEND"):
            warnings.append(
                Warning(
                    "OFFERMAN['PRICING_BACKEND'] não está configurado.",
                    hint="Defina OFFERMAN['PRICING_BACKEND'] com o backend de precificação contextual (ex: shopman.shop.adapters.pricing.PromotionPricingBackend).",
                    id="SHOPMAN_W005",
                )
            )
    return warnings


@register()
def check_fiscal_adapter(app_configs, **kwargs):
    """A loja oferece NFC-e no balcão e não há adapter fiscal configurado.

    O gestor liga "Nota fiscal" no Admin e, sem adapter, **nada acontece**: o
    toggle nem aparece no PDV (``backstage/projections/pos._supports_fiscal_document``
    exige os dois) e nenhuma nota sai. Configuração ligada que não faz efeito é o
    que este aviso existe para tirar do silêncio.

    O predicado é o que a loja realmente usa —
    ``Shop.defaults["pos"]["fiscal_toggle"]``, pela função dona da pergunta
    (``shop.services.pos.fiscal_toggle_enabled``). Até 2026-08-19 este check
    olhava ``Channel.config["fiscal"]["enabled"]``, chave que nenhum código do
    sistema escreve: o check nunca disparou uma vez.

    Espelho do ``SHOPMAN_E013`` e não redundante com ele: lá o adapter existe e
    falta a política de emissão (erro, bloqueia deploy); aqui a loja quer emitir
    e falta o adapter (aviso — pré-go-live é um estado legítimo).
    """
    warnings = []
    if getattr(settings, "SHOPMAN_FISCAL_ADAPTER", None):
        return warnings

    from django.db.utils import OperationalError, ProgrammingError

    from shopman.shop.services.pos import fiscal_toggle_enabled

    try:
        offers_fiscal = fiscal_toggle_enabled()
    except (OperationalError, ProgrammingError):
        return warnings  # tables not ready (initial migration)

    if offers_fiscal:
        warnings.append(
            Warning(
                "A loja oferece NFC-e no PDV (Shop.defaults['pos']['fiscal_toggle']) "
                "mas nenhum adapter fiscal está configurado.",
                hint=(
                    "O toggle 'Nota fiscal' não aparece no balcão e nenhuma nota é "
                    "emitida. Defina SHOPMAN_FISCAL_ADAPTER (ex.: "
                    "shopman.shop.adapters.fiscal_focusnfe.FocusNFeBackend) ou desligue "
                    "'Emitir nota fiscal' no Admin da loja."
                ),
                id="SHOPMAN_W003",
            )
        )
    return warnings


@register(deploy=True)
def check_fiscal_emission_resolver(app_configs, **kwargs):
    """Adapter fiscal ligado + canal de venda ativo ⇒ resolver de emissão que resolve.

    Silêncio é o pior modo de falha deste domínio. Quem decide SE a nota sai é o
    resolver (``shop/services/fiscal.emission_resolver``); com o resolver vazio,
    ou apontando para um caminho que não importa, o motor cai no fallback
    (opt-in do operador, ``order.data['fiscal']['issue_document']``) e registra
    um warning no log — e o sistema simplesmente não emite, venda após venda,
    sem nada na tela de ninguém.

    Erro de deploy, não warning: com emissão obrigatória valendo, cada venda que
    passa sem nota é passivo fiscal, e o log de um worker não é onde isso se
    descobre. O espelho deste check é o ``SHOPMAN_W003`` (a loja oferece NFC-e no
    balcão e não há adapter nenhum).
    """
    errors = []
    if settings.DEBUG:
        return errors
    if not getattr(settings, "SHOPMAN_FISCAL_ADAPTER", None):
        return errors

    from django.db.utils import OperationalError, ProgrammingError

    from shopman.shop.models import Channel

    try:
        selling = Channel.objects.filter(is_active=True, commerce_policy=Channel.CommercePolicy.ORDER).exists()
    except (OperationalError, ProgrammingError):
        return errors  # tabelas ainda não existem (migração inicial)
    if not selling:
        return errors

    raw = getattr(settings, "SHOPMAN_FISCAL_EMISSION_RESOLVER", "") or ""
    paths = [p.strip() for p in str(raw).split(",") if p.strip()]
    if not paths:
        errors.append(
            Error(
                "Adapter fiscal configurado e canal de venda ativo, mas SHOPMAN_FISCAL_EMISSION_RESOLVER está vazio.",
                hint=(
                    "Sem resolver, a NFC-e só sai quando o operador marca 'emitir' no "
                    "pedido — em silêncio, venda após venda. Aponte a política fiscal "
                    "do deployment: 'shopman.shop.fiscal_resolvers.always' (toda venda) "
                    "ou '...on_request_or_tax_id' (pediu ou informou CPF). Exemplos e "
                    "combinadores em shopman.shop.fiscal_resolvers."
                ),
                id="SHOPMAN_E013",
            )
        )
        return errors

    from django.utils.module_loading import import_string

    for path in paths:
        try:
            resolver = import_string(path)
        except ImportError as exc:
            errors.append(
                Error(
                    f"SHOPMAN_FISCAL_EMISSION_RESOLVER aponta para '{path}', que não importa: {exc}.",
                    hint=(
                        "O motor engole o erro e cai no fallback (opt-in do operador): "
                        "a emissão fica silenciosamente desligada. Corrija o caminho ou "
                        "remova-o da lista."
                    ),
                    id="SHOPMAN_E013",
                )
            )
            continue
        if not callable(resolver):
            errors.append(
                Error(
                    f"SHOPMAN_FISCAL_EMISSION_RESOLVER aponta para '{path}', que não é chamável.",
                    hint=(
                        "Um resolver é callable(order) -> bool. Fábricas como "
                        "`channels('pdv')` precisam de um wrapper importável já aplicado."
                    ),
                    id="SHOPMAN_E013",
                )
            )
    return errors


@register()
def check_listing_channel_parity(app_configs, **kwargs):
    """Warn when a Listing.ref has no matching Channel.ref (convention: channel.ref == listing.ref)."""
    warnings = []

    from django.db.utils import OperationalError, ProgrammingError

    try:
        from shopman.offerman.models import Listing

        from shopman.shop.models import Channel

        listing_refs = set(Listing.objects.filter(is_active=True).values_list("ref", flat=True))
        channel_refs = set(Channel.objects.values_list("ref", flat=True))

        orphans = listing_refs - channel_refs
        for ref in sorted(orphans):
            warnings.append(
                Warning(
                    f"Listing '{ref}' não tem Channel com ref correspondente.",
                    hint=(
                        "A convenção do Shopman é channel.ref == listing.ref. "
                        "Crie um Channel com este ref ou desative o Listing."
                    ),
                    id="SHOPMAN_W004",
                )
            )
    except (OperationalError, ProgrammingError, ImportError):
        logging.getLogger(__name__).warning("listing_channel_check_unavailable_before_schema_or_optional_app_ready")

    return warnings


@register()
def check_display_channel_price_source(app_configs, **kwargs):
    """Canal `display` precisa de `prices_from` válido — e público, se for rastreado.

    Duas coisas diferentes, e a segunda é a que protege:

    W008 — ``prices_from`` vazio ou apontando para canal inexistente. Sem ponteiro
    válido o renderizador cai em ``Product.base_price_q``, que é justamente o
    comportamento antigo em que o feed anunciava preço que a loja não cobra.

    W009 — canal **rastreado publicamente** (tem ``display.format``, logo é XML que
    Google/Meta buscam) tirando preço de canal cujo preço não é público. Sem isto,
    configurar ``prices_from="pdv"`` num canal Google publicaria o preço do balcão
    para o mundo — e preço alcançável publicamente é preço a honrar (ADR-018 §5.1).
    """
    warnings = []

    from django.db.utils import OperationalError, ProgrammingError

    from shopman.shop.models import Channel

    try:
        channels = list(Channel.objects.filter(is_active=True))
    except (OperationalError, ProgrammingError):
        return warnings  # tabelas ainda não existem (migração inicial)

    by_ref = {c.ref: c for c in channels}
    public_price_refs = {
        c.ref for c in channels if c.commerce_policy == Channel.CommercePolicy.ORDER and c.ref != POS_CHANNEL_REF()
    }

    for channel in channels:
        if channel.commerce_policy != Channel.CommercePolicy.DISPLAY:
            continue
        display = (channel.config or {}).get("display") or {}
        target = (display.get("prices_from") or "").strip()

        if not target or target not in by_ref:
            warnings.append(
                Warning(
                    f"Canal de exibição '{channel.ref}' não aponta preço de canal válido "
                    f"(display.prices_from={target!r}).",
                    hint=(
                        "Sem ponteiro válido o feed/menuboard cai em Product.base_price_q e "
                        "pode anunciar preço que a loja não cobra. Defina "
                        "config.display.prices_from com a ref de um canal de venda."
                    ),
                    id="SHOPMAN_W012",
                )
            )
            continue

        if display.get("format") and target not in public_price_refs:
            warnings.append(
                Warning(
                    f"Canal '{channel.ref}' é rastreado publicamente e tira preço de "
                    f"'{target}', cujo preço não é público.",
                    hint=(
                        "Feed XML é buscado por Google/Meta: publicar o preço do balcão "
                        "obrigaria a honrá-lo para qualquer um. Aponte prices_from para o "
                        "canal da loja."
                    ),
                    id="SHOPMAN_W013",
                )
            )

    return warnings


def POS_CHANNEL_REF() -> str:
    """Ref do canal de balcão — cujo preço NÃO é público (ADR-018 §5.1)."""
    from django.conf import settings

    return getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv")


@register(deploy=True)
def check_whatsapp_flow_coverage(app_configs, **kwargs):
    """Block an unsafe ManyChat Marketing lane and explain missing flow setup.

    A Meta não deixa texto livre sair para quem não interagiu nas últimas 24 horas
    (`code 3011`). O escape é um **template aprovado**, que no ManyChat vira um *flow* e
    aqui é o `NotificationTemplate.whatsapp_flow_ns`. Sem ele, o adapter cai em
    `sendContent` e a campanha falha **destinatário por destinatário**, com erro do
    provedor — o gestor vê "0 enviados, N falharam" e nenhuma pista do motivo.

    Este check existe porque descobrimos isso do jeito caro: um disparo real para um
    número frio, e um erro opaco. É o tipo de configuração faltando que só aparece no
    dia em que importa, então ela passa a aparecer na subida.

    A ausência de flow é aviso de setup porque a aprovação em runtime já está
    bloqueada. Um flow configurado com o WhatsApp de Marketing fechado (ou em
    ensaio) também é AVISO: o mesmo `safety_state` fecha o envio em runtime, e um
    `Error` aqui derrubava o deploy do sistema inteiro por uma faixa que já não
    podia enviar nada.
    """
    warnings = []

    try:
        from shopman.shop.models import Campaign, NotificationTemplate
    except ImportError:  # pragma: no cover - app registry ainda subindo
        return warnings

    from django.db import DatabaseError

    try:
        targets_whatsapp = [
            campaign for campaign in Campaign.objects.filter(is_active=True) if "whatsapp" in (campaign.platforms or [])
        ]
    except DatabaseError:
        # Check roda antes do migrate (deploy novo, banco vazio): sem tabela não há
        # campanha para avisar sobre, e o check não é o lugar de reclamar de schema.
        return warnings

    if not targets_whatsapp:
        return warnings

    event = "announcement_published"
    has_flow = (
        NotificationTemplate.objects.filter(event=event, is_active=True)
        .exclude(whatsapp_flow_ns="")
        .exists()
    )
    if has_flow:
        from shopman.shop.services import manychat_marketing_safety

        safety = manychat_marketing_safety.safety_state()
        if safety.state == manychat_marketing_safety.STATE_CANARY:
            # Ensaio ligado de propósito: avisar na subida que o público inteiro NÃO
            # recebe, para ninguém ler "deploy verde" como "WhatsApp aberto".
            warnings.append(
                Warning(
                    f"WhatsApp Marketing em ensaio: só {safety.canary_size} contato(s) "
                    "recebem mensagens de Marketing.",
                    hint=(
                        "Voltar SHOPMAN_MARKETING_WHATSAPP_MODE para blocked encerra o "
                        "ensaio; open abre para todo contato elegível."
                    ),
                    id="SHOPMAN_W020",
                )
            )
            return warnings
        if not safety.allows_delivery:
            # AVISO, não erro. O caminho inseguro já falha fechado em RUNTIME
            # (`require_safe_delivery` na aprovação, `delivery_readiness` na tela e
            # o próprio adapter leem o mesmo `safety_state`): nenhum envio real sai
            # com o modo fechado. Como `Error`, este check derrubava o job
            # `release` inteiro (check --deploy) assim que o banco tinha uma
            # campanha de WhatsApp ativa com flow — e o alpha ficou sem deploy
            # de TODO o sistema por causa de uma faixa que já estava bloqueada
            # (16/09, 22:15 em diante, 7 deployments em rollback).
            warnings.append(
                Warning(
                    f"WhatsApp Marketing permanece bloqueado ({safety.reason_code}): "
                    f"{safety.reason}",
                    hint=safety.action,
                    id="SHOPMAN_W020",
                )
            )
        return warnings

    names = ", ".join(sorted(campaign.name for campaign in targets_whatsapp)[:5])
    warnings.append(
        Warning(
            f"{len(targets_whatsapp)} campanha(s) ativa(s) enviam por WhatsApp sem template aprovado: {names}.",
            hint=(
                "Escolha um flow aprovado e ativo no cockpit Marketing → Plataformas. "
                "A configuração exige versão, lista fresca, TOTP e auditoria; o Admin "
                "é somente leitura."
            ),
            id="SHOPMAN_W014",
        )
    )
    return warnings


@register(deploy=True)
def check_marketing_whatsapp_isolation(app_configs, **kwargs):
    """Explicar na subida por que o WhatsApp de Marketing pedido continua fechado.

    ``canary``/``open`` só valem com a reserva por assinante vista por TODOS os
    processos (web e workers). Com cache local cada processo reserva sozinho, a
    serialização não vale, e ``safety_state`` mantém o bloqueio em runtime.

    ⚠️ AVISO, nunca `Error` — a mesma lição do SHOPMAN_W020 (16/09): o runtime já
    falha fechado, e um `Error` aqui derrubaria o `release` do sistema inteiro por uma
    faixa que já não envia nada.
    """
    from shopman.shop.services import manychat_marketing_safety as safety

    raw_mode = str(getattr(settings, "SHOPMAN_MARKETING_WHATSAPP_MODE", "") or "").strip().lower()
    mode = safety.whatsapp_mode()
    if raw_mode and raw_mode not in safety.MODES:
        return [
            Warning(
                f"SHOPMAN_MARKETING_WHATSAPP_MODE={raw_mode!r} não é um modo conhecido: "
                "o WhatsApp de Marketing fica bloqueado.",
                hint="Usar blocked, canary ou open.",
                id="SHOPMAN_W021",
            )
        ]
    if mode == safety.MODE_BLOCKED:
        return []
    warnings = []
    if not safety.serialization_available():
        warnings.append(
            Warning(
                f"SHOPMAN_MARKETING_WHATSAPP_MODE={mode} pedido, mas o cache não é "
                "compartilhado entre processos: a serialização das mensagens com flow "
                "não vale e o WhatsApp de Marketing continua bloqueado.",
                hint="Configurar REDIS_URL (cache Redis) em web e workers, ou voltar o modo para blocked.",
                id="SHOPMAN_W021",
            )
        )
    if mode == safety.MODE_CANARY and not safety.canary_customer_refs():
        warnings.append(
            Warning(
                "SHOPMAN_MARKETING_WHATSAPP_MODE=canary sem nenhum contato em "
                "SHOPMAN_MARKETING_WHATSAPP_CANARY_CUSTOMER_REFS: o WhatsApp de "
                "Marketing continua bloqueado.",
                hint="Informar os customer_ref do ensaio, separados por vírgula, ou voltar o modo para blocked.",
                id="SHOPMAN_W021",
            )
        )
    return warnings


@register(deploy=True)
def check_marketing_media_hosts(app_configs, **kwargs):
    """Fail deployment when a URL/port/wildcard/private IP entered the host list."""

    from shopman.shop.services.marketing_url_policy import (
        invalid_trusted_media_hosts,
    )

    invalid = invalid_trusted_media_hosts()
    if not invalid:
        return []
    return [
        Error(
            "A allowlist de mídia Marketing contém entrada insegura: "
            + ", ".join(invalid),
            hint=(
                "Use somente hostnames exatos controlados, sem esquema, caminho, "
                "porta, wildcard ou IP privado."
            ),
            id="SHOPMAN_E021",
        )
    ]


@register()
def check_sku_namespace_coherence(app_configs, **kwargs):
    """Warn when a SKU's sale and purchase records disagree on the unit.

    Product (cadastro de venda) e Material (cadastro de compra) podem dividir um
    SKU — é a coisa comprada que também se vende — e aí contam o mesmo estoque,
    na mesma unidade. Unidade divergente faz "3" valer 3 kg num lado e 3 potes
    no outro (ver shopman/shop/services/sku_namespace.py).

    Warning, não Error: dado preexistente não pode trancar o dono para fora do
    Admin, que é onde ele conserta. A incoerência nova é recusada no pre_save.
    """
    from django.db.utils import OperationalError, ProgrammingError

    warnings = []
    try:
        from shopman.shop.services.sku_namespace import find_sku_incoherences

        incoherences = find_sku_incoherences()
    except (OperationalError, ProgrammingError, ImportError):
        return warnings  # tables not ready (initial migration) or app absent

    if incoherences:
        warnings.append(
            Warning(
                "SKU com cadastro de venda e de compra em unidades diferentes: "
                + "; ".join(str(item) for item in incoherences)
                + ".",
                hint=(
                    "Os dois cadastros do mesmo SKU contam o mesmo estoque. Acerte a "
                    "unidade de um dos lados para que venda e compra falem a mesma."
                ),
                id="SHOPMAN_W015",
            )
        )
    return warnings


@register(deploy=True)
def check_environment_name_recognized(app_configs, **kwargs):
    """Avisa quando ``SHOPMAN_ENVIRONMENT`` não é nenhum nome conhecido.

    Não é Error porque o valor irreconhecível **já** é tratado como produção:
    `is_production()` só abre a porta para os quatro nomes não-produtivos, então
    um dedo escorregado falha do lado seguro. Mas falhar fechado em silêncio
    esconde a causa — quem digitou `stagin` numa máquina de teste veria os
    comandos de QA recusarem sem entender por quê. Este aviso é o grito.
    """
    if is_recognized_environment():
        return []

    nome = environment_name()
    conhecidos = ", ".join(sorted(NON_PRODUCTION_ENVIRONMENTS)) + ", production"
    return [
        Warning(
            f"SHOPMAN_ENVIRONMENT={nome!r} não é um ambiente conhecido — "
            "esta instância está sendo tratada como PRODUÇÃO.",
            hint=(
                f"Valores conhecidos: {conhecidos}. Um valor fora dessa lista fecha "
                "as travas destrutivas (seed --flush, import_backup, qa_scenarios, "
                "refresh_seed_dates) de propósito. Se esta máquina é de teste, "
                "corrija a variável; se é produção, escreva 'production'."
            ),
            id="SHOPMAN_W017",
        )
    ]


@register(deploy=True)
def check_production_quality_catalog(app_configs, **kwargs):
    """Trava o release quando a classificação de uma fornada não é segura."""
    from django.db import DatabaseError

    from shopman.shop.models import QualityDefect, QualityGrade

    try:
        grades = list(QualityGrade.objects.values("ref", "is_active", "is_default", "markdown_percent"))
        defects = list(QualityDefect.objects.values("ref", "is_active", "forces_discard"))
    except DatabaseError:
        return []  # tabelas ainda não existem durante o primeiro migrate

    errors = []
    active_defaults = [grade for grade in grades if grade["is_active"] and grade["is_default"]]
    if len(active_defaults) != 1:
        errors.append(
            Error(
                "O catálogo de qualidade precisa ter exatamente um grau padrão ativo.",
                hint=("No Admin > Graus de qualidade, mantenha um único grau ativo marcado como padrão."),
                id="SHOPMAN_E016",
            )
        )

    if not any(grade["is_active"] and grade["markdown_percent"] == 0 for grade in grades):
        errors.append(
            Error(
                "O catálogo de qualidade não tem grau ativo a preço cheio.",
                hint=(
                    "Ative ou cadastre ao menos um grau com desconto de 0%; o grau é o único eixo de preço da partição."
                ),
                id="SHOPMAN_E017",
            )
        )

    incoherent_refs = [grade["ref"] for grade in grades if grade["is_default"] and not grade["is_active"]]
    incoherent_refs.extend(defect["ref"] for defect in defects if defect["forces_discard"] and not defect["is_active"])
    incoherent_refs.extend(
        str(entry["ref"] or "<vazia>")
        for entry in (*grades, *defects)
        if entry["is_active"]
        and (not isinstance(entry["ref"], str) or not entry["ref"].strip() or entry["ref"] != entry["ref"].strip())
    )
    if incoherent_refs:
        errors.append(
            Error(
                "O catálogo de qualidade contém referências ou políticas incoerentes: "
                f"{', '.join(sorted(incoherent_refs))}.",
                hint=(
                    "Use refs ativas, não vazias e sem espaços externos; reative a referência "
                    "ou remova conscientemente o marcador padrão/veto antes do release."
                ),
                id="SHOPMAN_E018",
            )
        )

    return errors


@register(deploy=True)
def check_production_configuration(app_configs, **kwargs):
    """Valida a configuração resolvida que governará produção no release."""
    from django.db import DatabaseError
    from redis.exceptions import RedisError

    from shopman.shop.production_config import ProductionConfig

    try:
        ProductionConfig.load()
    except (DatabaseError, RedisError):
        # O check de deploy é deliberadamente offline: nem o banco nem o cache
        # precisam estar acessíveis para validar settings e contratos estáticos.
        # A configuração persistida é validada novamente no readiness semeado.
        return []
    except (TypeError, ValueError) as exc:
        return [
            Error(
                f"Configuração de produção inválida: {exc}",
                hint=("Corrija os campos estruturados em Admin > Configuração > Produção antes do release."),
                id="SHOPMAN_E019",
            )
        ]
    return []


@register(deploy=True)
def check_production_provider_environments(app_configs, **kwargs):
    """The release job already calls check --deploy; reuse canonical provider facts."""
    if not is_production():
        return []
    from shopman.shop.adapters.provider_readiness import build_provider_readiness

    try:
        facts = build_provider_readiness(mode="runtime")
    except Exception:
        logging.getLogger(__name__).warning("production_provider_readiness_unavailable")
        return [Error("Não foi possível verificar os ambientes dos provedores.",
                      hint="Execute production-readiness no ambiente alvo e corrija a leitura antes do deploy.",
                      id="SHOPMAN_E022")]
    return [Error(
        f"Provedor {fact.label} incompatível com produção.",
        hint="Corrija os requisitos de ambiente: " + ", ".join(fact.missing),
        id="SHOPMAN_E022",
    ) for fact in facts if fact.status == "error"]


@register(deploy=True)
def check_google_maps_credential_boundary(app_configs, **kwargs):
    if not is_production():
        return []
    browser = str(getattr(settings, "GOOGLE_MAPS_BROWSER_API_KEY", "") or "").strip()
    server = str(getattr(settings, "GOOGLE_MAPS_SERVER_API_KEY", "") or "").strip()
    legacy = str(getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()
    if legacy or not browser or not server or browser == server:
        return [Error("Google Maps exige credenciais separadas e completas em produção.",
                      hint="Remova GOOGLE_MAPS_API_KEY e provisione chaves distintas para browser (referrers) e servidor (Geocoding).",
                      id="SHOPMAN_E023")]
    return []


@register(deploy=True)
def check_vapid_configuration(app_configs, **kwargs):
    private_key = str(getattr(settings, "VAPID_PRIVATE_KEY", "") or "").strip()
    public_key = str(getattr(settings, "VAPID_PUBLIC_KEY", "") or "").strip()
    claims_email = str(getattr(settings, "VAPID_CLAIMS_EMAIL", "") or "").strip()
    configured = (private_key, public_key, claims_email)

    if not any(configured):
        if not is_production():
            return []
        return [Warning(
            "Web Push do backstage está desativado porque as chaves VAPID não foram configuradas.",
            hint=(
                "Provisione VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY e VAPID_CLAIMS_EMAIL "
                "como um único conjunto antes de habilitar Web Push."
            ),
            id="SHOPMAN_W019",
        )]

    invalid = not all(configured) or private_key == public_key or len(private_key) < 32 or len(public_key) < 32
    try:
        validate_email(claims_email)
    except ValidationError:
        invalid = True
    if not invalid:
        return []
    return [Error(
        "A configuração VAPID está parcial ou inválida.",
        hint=(
            "Defina em conjunto VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY e um "
            "VAPID_CLAIMS_EMAIL válido; nunca reutilize a mesma chave nos dois campos."
        ),
        id="SHOPMAN_E024",
    )]


@register(deploy=True)
def check_privacy_receipt_hmac_configuration(app_configs, **kwargs):
    """Block non-debug releases with an unusable privacy receipt keyring."""
    if settings.DEBUG:
        return []

    current_key = str(
        getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY", "") or ""
    ).encode("utf-8")
    raw_version = getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_KEY_VERSION", 1)
    raw_previous = getattr(settings, "SHOPMAN_PRIVACY_RECEIPT_HMAC_PREVIOUS_KEYS", {})

    invalid = len(current_key) < 32
    try:
        current_version = int(raw_version)
        invalid = invalid or current_version < 1
    except (TypeError, ValueError):
        current_version = None
        invalid = True

    if isinstance(raw_previous, str):
        try:
            previous = json.loads(raw_previous)
        except (TypeError, ValueError, json.JSONDecodeError):
            previous = None
    else:
        previous = raw_previous

    if not isinstance(previous, Mapping):
        invalid = True
    else:
        for raw_previous_version, raw_previous_key in previous.items():
            try:
                previous_version = int(raw_previous_version)
            except (TypeError, ValueError):
                invalid = True
                continue
            previous_key = str(raw_previous_key or "").encode("utf-8")
            if previous_version < 1 or len(previous_key) < 32:
                invalid = True
            if (
                current_version is not None
                and previous_version == current_version
                and not hmac.compare_digest(previous_key, current_key)
            ):
                invalid = True

    if not invalid:
        return []
    return [
        Error(
            "A configuração HMAC dos recibos de privacidade está ausente ou inválida.",
            hint=(
                "Defina uma chave atual exclusiva com ao menos 32 bytes, versão inteira "
                "positiva e um keyring JSON de chaves anteriores igualmente válidas."
            ),
            id="SHOPMAN_E025",
        )
    ]


#: O que cada variável decide, na voz do erro. A chave é o nome da env.
_PROVIDER_ENVIRONMENT_DECISIONS = {
    "EFI_SANDBOX": (
        "o ambiente de cobrança do Pix (Efí)",
        "EFI_SANDBOX=false para cobrar de verdade",
    ),
    "FOCUS_NFE_ENVIRONMENT": (
        "o ambiente fiscal da NFC-e (Focus NFe)",
        "FOCUS_NFE_ENVIRONMENT=producao para emitir nota com validade",
    ),
}


@register(deploy=True)
def check_provider_environments_declared(app_configs, **kwargs):
    """Produção não sobe com ambiente de cobrança ou fiscal herdado do default.

    O default de ``EFI_SANDBOX`` é ``true`` e o de ``FOCUS_NFE_ENVIRONMENT`` é
    ``homologacao``: servem o dev e o staging, e em produção seriam Pix que não
    entra na conta e NFC-e que não existe no SEFAZ. O ``SHOPMAN_E022`` já
    reprova o VALOR de teste em produção; este reprova a OMISSÃO, com a
    mensagem que diz qual variável escrever. São perguntas diferentes: "o
    valor está errado" e "ninguém decidiu".
    """
    if not is_production():
        return []
    undeclared = tuple(getattr(settings, "SHOPMAN_UNDECLARED_PROVIDER_ENVIRONMENTS", ()) or ())
    errors = []
    for name in undeclared:
        what, example = _PROVIDER_ENVIRONMENT_DECISIONS.get(name, (name, f"{name}=<valor>"))
        errors.append(
            Error(
                f"{name} não foi declarada: {what} está vindo do default de teste.",
                hint=f"Declare a variável no spec de deploy de produção (ex.: {example}).",
                id="SHOPMAN_E026",
            )
        )
    return errors


_STRIPE_LIVE_PREFIXES = ("sk_live_", "pk_live_", "rk_live_")


def _declared_adapter_paths(adapter_type: str, settings_name: str) -> dict[str, str]:
    """Caminhos de adapter declarados, por origem: settings E ``Shop.integrations``.

    A união das duas camadas, e não só a que vence: o Admin pode apontar o Pix
    para a Efí por cima de um settings simulado (ou o contrário), e a pergunta
    aqui é "algum caminho deste tipo leva a dinheiro de verdade?". Chave do
    dicionário é o rótulo que a mensagem mostra.
    """
    found: dict[str, str] = {}

    def collect(origin: str, value) -> None:
        if isinstance(value, Mapping):
            for method, path in value.items():
                if path:
                    label = (
                        f"SHOPMAN_{str(method).upper()}_ADAPTER"
                        if origin == "SHOPMAN_PAYMENT_ADAPTERS"
                        else f"{origin}[{method}]"
                    )
                    found[label] = str(path)
        elif value:
            found[origin] = str(value)

    collect(settings_name, getattr(settings, settings_name, None))
    try:
        from shopman.shop.adapters import _shop_integrations_value

        collect(f"Shop.integrations[{adapter_type}]", _shop_integrations_value(adapter_type))
    except Exception:
        # Sem banco (build, check sem migração) vale o que o settings declara,
        # mas em WARNING: um override do Admin pode estar fora desta conta.
        logging.getLogger(__name__).warning(
            "live_provider_check: Shop.integrations ilegível; só o settings foi conferido", exc_info=True
        )
    return found


def _live_provider_facts() -> list[str]:
    """O que, nesta configuração, mexe com dinheiro ou nota de verdade.

    Chave live do Stripe vale por si: é credencial de cobrança. Efí fora do
    sandbox só é dinheiro quando algum pagamento passa por ``payment_efi``, e
    Focus em produção só é nota quando o emissor fiscal é a Focus. Efí em
    sandbox com ``payment_efi`` (o ensaio do Pix, D-031) não é dinheiro.
    """
    from shopman.shop.adapters.fiscal_focusnfe import PRODUCTION_URL, _base_url

    facts = []
    stripe = getattr(settings, "SHOPMAN_STRIPE", {}) or {}
    for key, label in (("secret_key", "STRIPE_SECRET_KEY"), ("publishable_key", "STRIPE_PUBLISHABLE_KEY")):
        if str(stripe.get(key) or "").strip().startswith(_STRIPE_LIVE_PREFIXES):
            facts.append(f"{label} live (cartão cobra de verdade)")

    payment_paths = _declared_adapter_paths("payment", "SHOPMAN_PAYMENT_ADAPTERS")
    efi = getattr(settings, "SHOPMAN_EFI", {}) or {}
    if not efi.get("sandbox", True) and any("payment_efi" in path for path in payment_paths.values()):
        facts.append("EFI_SANDBOX=false com Pix na Efí (Pix cobra de verdade)")

    fiscal_paths = _declared_adapter_paths("fiscal", "SHOPMAN_FISCAL_ADAPTER")
    focus = getattr(settings, "SHOPMAN_FOCUS_NFE", {}) or {}
    if (
        focus
        and _base_url(focus) == PRODUCTION_URL
        and any("fiscal_focusnfe" in path for path in fiscal_paths.values())
    ):
        facts.append("Focus NFe em produção (NFC-e com validade no SEFAZ)")
    return facts


def _open_test_doors() -> list[str]:
    """As portas de teste abertas, cada uma com o que fazer para fechá-la."""
    doors = []
    if settings.DEBUG:
        doors.append("DJANGO_DEBUG=true: escreva DJANGO_DEBUG=false")
    if not is_production():
        doors.append(
            f"SHOPMAN_ENVIRONMENT={environment_name()} (libera seed --flush, qa_scenarios e as "
            "travas de produção desligadas): escreva SHOPMAN_ENVIRONMENT=production"
        )
    for name, what in (
        ("SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS", "simulador de pagamento permitido"),
        ("SHOPMAN_EXPOSE_MOCK_CAPTURE", 'botão "Simular pagamento" para o cliente'),
        ("SHOPMAN_MOCK_PIX_AUTO_CONFIRM", "Pix simulado se confirma sozinho"),
        ("SHOPMAN_STAGING_AUTOPILOT", "pedidos avançam sozinhos"),
    ):
        if getattr(settings, name, False):
            doors.append(f"{name}=true ({what}): apague a variável")
    for origin, path in sorted(_declared_adapter_paths("payment", "SHOPMAN_PAYMENT_ADAPTERS").items()):
        if "payment_mock" in path:
            doors.append(f"{origin}=payment_mock (pagamento simulado): aponte para o gateway real")
    return doors


@register(deploy=True)
def check_live_provider_without_test_doors(app_configs, **kwargs):
    """Dinheiro ou nota de verdade só com TODAS as portas de teste fechadas.

    O ``SHOPMAN_E022`` e o ``SHOPMAN_E026`` barram a virada pela metade num
    sentido: produção com chave de teste. Este barra o outro: chave live (ou Efí
    fora do sandbox, ou Focus em produção) com o ambiente ainda ``staging``, o
    simulador permitido, o botão "Simular pagamento", o OTP na resposta, o
    piloto automático ou DEBUG. Esse estado subia calado: cobrança de verdade
    numa loja em que o cliente ainda consegue marcar o pedido como pago com um
    clique. Roda em QUALQUER ambiente, porque a porta aberta é justamente o
    ambiente não ser produção. O alpha (tudo de teste) e o ensaio do Pix
    (``EFI_SANDBOX=true`` com ``payment_efi``) não têm fato live e passam.
    """
    live = _live_provider_facts()
    if not live:
        return []
    doors = _open_test_doors()
    if not doors:
        return []
    return [
        Error(
            "Dinheiro ou nota de verdade com porta de teste aberta: " + "; ".join(live) + ".",
            hint=(
                "Feche todas as portas na mesma gravação do spec (ou volte as chaves para teste): "
                + "; ".join(doors)
                + "."
            ),
            id="SHOPMAN_E027",
        )
    ]
