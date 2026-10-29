"""
Google Merchant projection — o catálogo do canal de plataforma pela Merchant API.

Implementa ``CatalogProjectionBackend`` (Offerman) para o canal de exibição do Google
(``google-shopping``). É o ESCRITOR ÚNICO do catálogo no Merchant Center: a fonte de
dados da conta é do tipo API, sem o arquivo do feed ao lado
(``docs/plans/CATALOG-PUSH-GOOGLE-META-PLAN.md``).

Contrato (Merchant API, ``products_v1``)
---------------------------------------

- **project** → ``POST /products/v1/accounts/{conta}/productInputs:insert?dataSource=…``
  com o produto INTEIRO. O insert é upsert pela chave ``contentLanguage`` +
  ``feedLabel`` + ``offerId`` (o SKU). Não usamos ``productInputs.patch`` para
  preço e disponibilidade: a atualização rápida por atributo está restrita a contas
  liberadas pelo Google (developers.google.com/merchant/api/latest-updates).
- **retirada na loja** → ``POST /inventories/v1/accounts/{conta}/products/{id}/localInventories:insert``
  com o estoque da loja física (``storeCode`` do Perfil da Empresa): a MESMA
  disponibilidade e o mesmo preço do item online, retirada grátis no mesmo dia
  (``pickupMethod=BUY``, ``pickupSla=SAME_DAY``). É o que faz o Google mostrar
  "Retirada na loja". Só vai para item visível; sem ``store_code`` não vai nada.
- **retract** → ``DELETE /products/v1/accounts/{conta}/productInputs/{id}?dataSource=…``.
  Só para o item que SAIU da composição do canal. Pausado, oculto e esgotado
  continuam na conta, cada um com o seu estado, vindo de ``services/display_catalog``
  (oculto = todos os destinos em ``excludedDestinations``).

A decisão de cada item (entra, preço, disponível, oculto) NÃO mora aqui: o handler
entrega ``ProjectedItem.metadata["display"]``, a mesma decisão que o XML do feed lê.
Este módulo só traduz para a grafia da API (camelCase, enums em maiúsculas, preço em
micros).

Autenticação: service account (JWT RS256 assinado com PyJWT + cryptography, trocado
por access token no ``token_uri``), o mesmo desenho de ``backup/drive.py``. Escopo
``https://www.googleapis.com/auth/content``.

Onde mora a config (ADR-042): o que é DADO DA LOJA fica em
``Shop.defaults["google_merchant"]``; só o segredo e o técnico ficam no ``settings``
(``SHOPMAN_GOOGLE_MERCHANT``), porque o cofre por loja ainda não existe.

    Shop.defaults["google_merchant"]:
        account_id:        id da conta do Merchant Center.
        data_source_id:    id da fonte de dados do tipo API (primária).
        content_language:  ISO 639-1 dos produtos (default ``pt``).
        feed_label:        rótulo do feed (default ``BR``).
        store_code:        código da loja no Perfil da Empresa (retirada na loja).
                           Ausente = só o produto online, sem retirada.
    SHOPMAN_GOOGLE_MERCHANT:
        service_account_b64:   JSON da service account em base64 (segredo do deployment).
                               Base64 porque o editor de variáveis da DigitalOcean
                               recusa o JSON cru, com quebras de linha.
        api_base:              base da API (default ``https://merchantapi.googleapis.com``).
        timeout:               segundos por chamada (default 30).
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass

import jwt
import requests
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult

from shopman.shop.services import display_catalog

logger = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/content"
_TOKEN_MARGIN_SECONDS = 120
_CONDITIONS = {"new": "NEW", "used": "USED", "refurbished": "REFURBISHED"}

_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()


class GoogleMerchantRateLimitError(Exception):
    """A Merchant API respondeu 429 (cota)."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Google Merchant rate limit hit; retry after {retry_after}s")


def _get_config() -> dict:
    """O técnico e o segredo (``settings``) com o dado da loja (``Shop.defaults``) por cima."""
    from django.conf import settings

    from shopman.shop.models import Shop

    shop = Shop.load()
    store = ((shop.defaults or {}).get("google_merchant") or {}) if shop else {}
    return {**(getattr(settings, "SHOPMAN_GOOGLE_MERCHANT", {}) or {}), **store}


def _service_account(cfg: dict) -> dict | None:
    raw = str(cfg.get("service_account_b64") or "").strip()
    if not raw:
        return None
    try:
        creds = json.loads(base64.b64decode(raw, validate=True))
    except ValueError:
        logger.error("catalog_projection_google: service_account_b64 não é o JSON da chave em base64")
        return None
    if not all(creds.get(key) for key in ("client_email", "private_key", "token_uri")):
        return None
    return creds


def _configured(cfg: dict) -> bool:
    return bool(cfg.get("account_id") and cfg.get("data_source_id") and _service_account(cfg))


def _access_token(cfg: dict) -> str:
    creds = _service_account(cfg)
    key = creds["client_email"]
    now = time.time()
    with _token_lock:
        cached = _token_cache.get(key)
        if cached and cached[1] > now:
            return cached[0]
        assertion = jwt.encode(
            {"iss": key, "scope": _SCOPE, "aud": creds["token_uri"], "iat": int(now), "exp": int(now) + 3600},
            creds["private_key"],
            algorithm="RS256",
        )
        resp = requests.post(
            creds["token_uri"],
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            timeout=_timeout(cfg),
        )
        resp.raise_for_status()
        body = resp.json()
        token = body["access_token"]
        expires_in = int(body.get("expires_in") or 3600)
        _token_cache[key] = (token, now + max(60, expires_in - _TOKEN_MARGIN_SECONDS))
        return token


def _timeout(cfg: dict) -> int:
    return int(cfg.get("timeout") or 30)


def _base(cfg: dict) -> str:
    return str(cfg.get("api_base") or "https://merchantapi.googleapis.com").rstrip("/")


def _account(cfg: dict) -> str:
    return f"accounts/{cfg['account_id']}"


def _data_source(cfg: dict) -> str:
    return f"{_account(cfg)}/dataSources/{cfg['data_source_id']}"


def _language(cfg: dict) -> str:
    return str(cfg.get("content_language") or "pt")


def _feed_label(cfg: dict) -> str:
    return str(cfg.get("feed_label") or "BR")


def product_input_id(sku: str, cfg: dict) -> str:
    """O segmento ``{productInput}``: ``idioma~rótulo~SKU`` em base64url sem padding.

    O formato codificado é o recomendado pela API para qualquer SKU (o simples quebra
    com ``/``, ``%`` ou ``~``).
    """
    plain = f"{_language(cfg)}~{_feed_label(cfg)}~{sku}"
    return base64.urlsafe_b64encode(plain.encode()).decode().rstrip("=")


def _store_code(cfg: dict) -> str:
    return str(cfg.get("store_code") or "").strip()


def build_local_inventory(item: display_catalog.DisplayItem, cfg: dict) -> dict:
    """O ``LocalInventory`` da loja física: o mesmo estoque do online, com retirada.

    O estoque é um só; o Google só pede que a retirada chegue em outro recurso,
    preso ao código da loja no Perfil da Empresa.
    """
    return {
        "storeCode": _store_code(cfg),
        "localInventoryAttributes": {
            "availability": "IN_STOCK" if item.available else "OUT_OF_STOCK",
            "price": {"amountMicros": str(int(item.price_q) * 10_000), "currencyCode": "BRL"},
            "pickupMethod": "BUY",
            "pickupSla": "SAME_DAY",
        },
    }


def build_product_input(item: display_catalog.DisplayItem, cfg: dict) -> dict:
    """O ``ProductInput`` de um item, traduzido da decisão de ``display_catalog``."""
    attributes: dict = {
        "title": item.title,
        "description": item.description,
        "link": item.link,
        "imageLink": item.image_link,
        "availability": "IN_STOCK" if item.available else "OUT_OF_STOCK",
        "price": {
            "amountMicros": str(int(item.price_q) * 10_000),
            "currencyCode": "BRL",
        },
        "condition": _CONDITIONS.get((item.condition or "new").lower(), "NEW"),
        "productTypes": [item.product_type] if item.product_type else [],
        "customLabel0": item.custom_label_0,
    }
    if item.additional_image_links:
        attributes["additionalImageLinks"] = list(item.additional_image_links)
    if item.brand:
        attributes["brand"] = item.brand
    if item.gtin:
        attributes["gtins"] = [item.gtin]
    if item.mpn:
        attributes["mpn"] = item.mpn
    if item.google_product_category:
        attributes["googleProductCategory"] = item.google_product_category
    if item.hidden:
        attributes["excludedDestinations"] = [api for _feed, api in display_catalog.GOOGLE_DESTINATIONS]
    return {
        "offerId": item.sku,
        "contentLanguage": _language(cfg),
        "feedLabel": _feed_label(cfg),
        "productAttributes": attributes,
    }


@dataclass(frozen=True)
class DeveloperRegistration:
    """Resultado do registro do projeto do Google Cloud na conta do Merchant Center."""

    ok: bool
    gcp_ids: tuple[str, ...] = ()
    error: str = ""


def register_gcp(cfg: dict | None = None) -> DeveloperRegistration:
    """Registra, uma vez, o projeto do Google Cloud da service account na conta.

    Sem esse registro, toda chamada da Merchant API responde 401
    (developers.google.com/merchant/api/guides/quickstart/registration). Quem chama
    é a própria service account, e ela precisa de acesso de Administrador na conta.
    Chamar de novo é seguro: o registro é do par conta e projeto, e o Google
    devolve o mesmo vínculo; projeto já registrado em OUTRA conta volta como erro
    (``ALREADY_REGISTERED``), com a mensagem dele.
    """
    cfg = _get_config() if cfg is None else cfg
    if not (cfg.get("account_id") and _service_account(cfg)):
        return DeveloperRegistration(
            ok=False,
            error="Grave a conta do Merchant Center e configure a chave da service account antes de registrar.",
        )
    try:
        token = _access_token(cfg)
        resp = requests.post(
            f"{_base(cfg)}/accounts/v1/{_account(cfg)}/developerRegistration:registerGcp",
            json={},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=_timeout(cfg),
        )
    except requests.RequestException as exc:
        logger.warning("catalog_projection_google.register_gcp sem resposta", exc_info=True)
        return DeveloperRegistration(ok=False, error=f"A chamada ao Google falhou (chave recusada ou sem resposta): {exc}")
    if resp.status_code >= 400:
        return DeveloperRegistration(ok=False, error=_google_error(resp))
    body = resp.json() if resp.content else {}
    return DeveloperRegistration(ok=True, gcp_ids=tuple(str(gcp) for gcp in body.get("gcpIds") or ()))


def _google_error(resp: requests.Response) -> str:
    """A mensagem do Google, com o motivo provável quando é falta de acesso."""
    try:
        error = (resp.json() or {}).get("error") or {}
    except ValueError:
        error = {}
    message = str(error.get("message") or resp.text[:300] or f"HTTP {resp.status_code}")
    status = str(error.get("status") or "")
    detail = f"{message} ({status})" if status else message
    if resp.status_code in (401, 403):
        return (
            f"{detail}. Confira se a service account está em Pessoas e acesso do Merchant "
            "Center com acesso de Administrador."
        )
    return detail


def _check(resp: requests.Response, *, missing_ok: bool = False) -> None:
    if resp.status_code == 429:
        raise GoogleMerchantRateLimitError(retry_after=int(resp.headers.get("Retry-After", 60)))
    if missing_ok and resp.status_code == 404:
        return
    resp.raise_for_status()


class GoogleMerchantProjection:
    """Envia o catálogo do canal de plataforma do Google pela Merchant API."""

    def project(
        self,
        items: list[ProjectedItem],
        *,
        channel: str,
        full_sync: bool = False,
    ) -> ProjectionResult:
        cfg = _get_config()
        if not _configured(cfg):
            return ProjectionResult(
                success=False,
                errors=["Google Merchant não configurado (conta, fonte de dados ou service account)"],
                channel=channel,
            )
        headers = {"Authorization": f"Bearer {_access_token(cfg)}", "Content-Type": "application/json"}
        url = f"{_base(cfg)}/products/v1/{_account(cfg)}/productInputs:insert"
        store_code = _store_code(cfg)
        errors: list[str] = []
        projected = 0
        for item in items:
            decided = item.metadata.get("display") if isinstance(item.metadata, dict) else None
            if not isinstance(decided, display_catalog.DisplayItem):
                errors.append(f"{item.sku}: item sem a decisão do canal (display_catalog)")
                continue
            try:
                resp = requests.post(
                    url,
                    params={"dataSource": _data_source(cfg)},
                    json=build_product_input(decided, cfg),
                    headers=headers,
                    timeout=_timeout(cfg),
                )
                _check(resp)
                if store_code and not decided.hidden:
                    resp = requests.post(
                        f"{_base(cfg)}/inventories/v1/{_account(cfg)}/products/"
                        f"{product_input_id(decided.sku, cfg)}/localInventories:insert",
                        json=build_local_inventory(decided, cfg),
                        headers=headers,
                        timeout=_timeout(cfg),
                    )
                    _check(resp)
                projected += 1
            except GoogleMerchantRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_google.project degraded", exc_info=True)
                errors.append(f"{item.sku}: {exc}")
        return ProjectionResult(success=not errors, projected=projected, errors=errors, channel=channel)

    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult:
        cfg = _get_config()
        if not _configured(cfg):
            return ProjectionResult(
                success=False,
                errors=["Google Merchant não configurado (conta, fonte de dados ou service account)"],
                channel=channel,
            )
        headers = {"Authorization": f"Bearer {_access_token(cfg)}"}
        errors: list[str] = []
        retracted = 0
        for sku in skus:
            url = f"{_base(cfg)}/products/v1/{_account(cfg)}/productInputs/{product_input_id(sku, cfg)}"
            try:
                resp = requests.delete(
                    url, params={"dataSource": _data_source(cfg)}, headers=headers, timeout=_timeout(cfg),
                )
                # Já ausente na conta é o estado pedido.
                _check(resp, missing_ok=True)
                retracted += 1
            except GoogleMerchantRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_google.retract degraded", exc_info=True)
                errors.append(f"{sku}: {exc}")
        return ProjectionResult(success=not errors, projected=retracted, errors=errors, channel=channel)
