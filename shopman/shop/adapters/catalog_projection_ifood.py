"""
iFood Catalog Projection adapter — catalog v2.0 (verified live 2026-06-30).

Implements ``CatalogProjectionBackend`` (Offerman) by pushing the internal
catalog (``ProjectedItem`` snapshots) to the iFood Merchant Catalog API.

Live contract (test store ``f36a17d0-…``)
----------------------------------------

Structure: **Merchant → Catálogos → Categorias → Itens**.

- **Upsert an item** — ``PUT /catalog/v2.0/merchants/{mid}/items`` → ``200``.
  Body is a *FullItemDto*::

        {
          "item":     {"id", "productId", "status", "price", "categoryId",
                       "externalCode", "index", "shifts"},
          "products": [{"id", "name", "description", "externalCode"}]
        }

  ``item.id``, ``item.productId`` and ``products[0].id`` **must be UUIDs**, and
  ``item.productId`` must equal ``products[0].id``. We derive both UUIDs
  deterministically from ``(merchant_id, sku)`` (uuid5), so re-syncing the same
  SKU upserts the same item instead of duplicating it.

- **Toggle availability / retract** — ``PATCH /catalog/v2.0/merchants/{mid}/items/status``
  → ``200``. Body is a single object ``{"itemId": <item uuid>, "status":
  "AVAILABLE"|"UNAVAILABLE"}``.

Authentication is OAuth 2.0 ``client_credentials`` via
:mod:`shopman.shop.services.ifood_auth` (Bearer + the mandatory own User-Agent —
iFood's WAF answers ``403`` to a generic UA). Config lives in the
``SHOPMAN_IFOOD`` Django setting:

    merchant_id:         iFood merchant UUID.
    api_base:            Base URL (default ``https://merchant-api.ifood.com.br``).
    catalog_category_map: ``{internal_collection_ref: ifood_category_uuid}``.
    catalog_default_category: iFood category UUID for items with no mapped
                         collection (optional). Items with neither a mapped
                         collection nor a default are reported as errors — an
                         item cannot be pushed without a target category.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import uuid
from io import BytesIO
from urllib.parse import unquote, urlparse

import requests
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult

from shopman.shop.services import ifood_auth

logger = logging.getLogger(__name__)

# Fixed namespace so item/product UUIDs are stable across processes and syncs.
_UUID_NS = uuid.UUID("f0f4d7e2-0e2a-5c7a-9d1b-6b1e2a3c4d5e")
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_IMAGE_PATHS: dict[tuple[str, str], str] = {}


class IFoodRateLimitError(Exception):
    """Raised when the iFood API responds with 429 Too Many Requests."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"iFood rate limit hit; retry after {retry_after}s")


class IFoodCategoryError(Exception):
    """Raised when an item has no resolvable iFood category."""


class IFoodImageError(Exception):
    """A foto não pôde ser lida, validada ou enviada ao iFood."""


def _get_config(channel: str = "ifood") -> dict:
    from django.conf import settings
    return getattr(settings, "SHOPMAN_IFOOD", {})


class IFoodCatalogWriteBlocked(Exception):
    """Escrita não autorizada para um merchant explicitamente de teste."""


def ensure_catalog_write_allowed(cfg: dict | None = None) -> None:
    """Nega por padrão, sem OAuth/HTTP ou inferência do tipo de loja."""
    from django.conf import settings

    policy = getattr(settings, "SHOPMAN_IFOOD_CATALOG_WRITE_POLICY", None)
    cfg = _get_config() if cfg is None else cfg
    message = ("Escrita de catálogo iFood bloqueada. Requer política explícita de teste "
               "SHOPMAN_IFOOD_CATALOG_WRITE_POLICY e merchant autorizado na allowlist.")
    if not isinstance(policy, dict) or policy.get("environment") != "test" or not isinstance(cfg, dict):
        raise IFoodCatalogWriteBlocked(message)
    merchants = policy.get("merchant_allowlist")
    if not isinstance(merchants, list) or not merchants:
        raise IFoodCatalogWriteBlocked(message)
    for merchant in merchants:
        if not isinstance(merchant, str):
            raise IFoodCatalogWriteBlocked(message)
        try:
            canonical = str(uuid.UUID(merchant))
        except (ValueError, AttributeError) as exc:
            raise IFoodCatalogWriteBlocked(message) from exc
        if canonical != merchant:
            raise IFoodCatalogWriteBlocked(message)
    if cfg.get("merchant_id") not in merchants:
        raise IFoodCatalogWriteBlocked(message)


def _base_url(cfg: dict) -> str:
    return str(cfg.get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def _product_uuid(merchant_id: str, sku: str) -> str:
    return str(uuid.uuid5(_UUID_NS, f"{merchant_id}:product:{sku}"))


def _item_uuid(merchant_id: str, sku: str) -> str:
    return str(uuid.uuid5(_UUID_NS, f"{merchant_id}:item:{sku}"))


def _resolve_category_id(item: ProjectedItem, cfg: dict) -> str:
    """Map the item's internal collection to an iFood category UUID.

    Raises :class:`IFoodCategoryError` when neither a mapped collection nor a
    configured default is available — pushing to the wrong category silently
    would be worse than failing loudly.
    """
    category_map = cfg.get("catalog_category_map") or {}
    if item.category and item.category in category_map:
        return str(category_map[item.category])
    default = cfg.get("catalog_default_category")
    if default:
        return str(default)
    raise IFoodCategoryError(
        f"no iFood category for collection={item.category!r} "
        "(set catalog_category_map or catalog_default_category in SHOPMAN_IFOOD)"
    )


def _item_payload(
    item: ProjectedItem,
    *,
    merchant_id: str,
    category_id: str,
    in_stock: bool = True,
    image_path: str = "",
) -> dict:
    """Build the FullItemDto body for ``PUT /items`` from a ProjectedItem.

    ``in_stock`` é a resposta de :mod:`shopman.shop.services.external_availability`:
    vendável zerado sai ``UNAVAILABLE``, e a pausa (``is_sellable``) continua vencendo.
    """
    price = round(item.price_q / 100, 2)
    product_id = _product_uuid(merchant_id, item.sku)
    item_id = _item_uuid(merchant_id, item.sku)
    available = item.is_published and item.is_sellable and in_stock
    product = {
        "id": product_id,
        "name": item.name,
        "description": item.description,
        "externalCode": item.sku,
    }
    if image_path:
        product["imagePath"] = image_path
    return {
        "item": {
            "id": item_id,
            "productId": product_id,
            "status": "AVAILABLE" if available else "UNAVAILABLE",
            "price": {"value": price, "originalValue": price},
            "categoryId": category_id,
            "externalCode": item.sku,
            "index": 0,
            "shifts": [],
        },
        "products": [product],
    }


def _storage_image(image_url: str) -> bytes | None:
    """Lê uma foto nossa direto do storage, sem dar uma volta por HTTP."""
    from django.core.files.storage import default_storage

    parsed = urlparse(image_url)
    path = unquote(parsed.path).lstrip("/")
    base_path = urlparse(str(getattr(default_storage, "base_url", "") or "")).path.strip("/")
    candidates = [path]
    if base_path and path.startswith(f"{base_path}/"):
        candidates.insert(0, path[len(base_path) + 1 :])
    if "/products/" in f"/{path}":
        candidates.append(f"products/{path.split('/products/', 1)[1]}")

    for name in dict.fromkeys(candidate for candidate in candidates if candidate):
        try:
            if not default_storage.exists(name):
                continue
            with default_storage.open(name, "rb") as source:
                return source.read(_MAX_IMAGE_BYTES + 1)
        except Exception:  # silêncio-deliberado: probe local falhou; o download HTTP é a segunda fonte.
            logger.debug("catalog_projection_ifood.storage_image degraded", exc_info=True)
    return None


def _download_image(image_url: str, cfg: dict) -> bytes:
    stored = _storage_image(image_url)
    if stored is not None:
        return stored
    try:
        response = requests.get(
            image_url,
            stream=True,
            timeout=int(cfg.get("image_timeout") or cfg.get("timeout") or 30),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise IFoodImageError("Não foi possível baixar a foto do produto.") from exc
    try:
        declared_size = int(response.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        declared_size = 0
    if declared_size > _MAX_IMAGE_BYTES:
        response.close()
        raise IFoodImageError("A foto excede o limite de 5 MB do iFood.")
    chunks: list[bytes] = []
    size = 0
    try:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > _MAX_IMAGE_BYTES:
                raise IFoodImageError("A foto excede o limite de 5 MB do iFood.")
            chunks.append(chunk)
    finally:
        response.close()
    return b"".join(chunks)


def _validated_image(image_url: str, cfg: dict) -> tuple[bytes, str, str]:
    from PIL import Image, UnidentifiedImageError

    payload = _download_image(image_url, cfg)
    if len(payload) > _MAX_IMAGE_BYTES:
        raise IFoodImageError("A foto excede o limite de 5 MB do iFood.")
    try:
        with Image.open(BytesIO(payload)) as image:
            image_format = str(image.format or "").upper()
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise IFoodImageError("A foto não é um arquivo JPG, JPEG ou PNG válido.") from exc
    content_types = {"JPEG": "image/jpeg", "PNG": "image/png"}
    content_type = content_types.get(image_format)
    if not content_type:
        raise IFoodImageError("O iFood aceita somente fotos JPG, JPEG ou PNG.")
    return payload, content_type, hashlib.sha256(payload).hexdigest()


def _upload_image(payload: bytes, content_type: str, cfg: dict, headers: dict) -> str:
    merchant_id = cfg["merchant_id"]
    url = f"{_base_url(cfg)}/catalog/v2.0/merchants/{merchant_id}/image/upload"
    encoded = base64.b64encode(payload).decode("ascii")
    try:
        response = requests.post(
            url,
            json={"image": f"data:{content_type};base64,{encoded}"},
            headers=headers,
            timeout=int(cfg.get("timeout") or 30),
        )
        _check_rate_limit(response)
        response.raise_for_status()
    except IFoodRateLimitError:
        raise
    except requests.RequestException as exc:
        raise IFoodImageError("Não foi possível enviar a foto ao iFood.") from exc
    try:
        image_path = str(response.json()["imagePath"]).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise IFoodImageError("O iFood recebeu a foto, mas não devolveu o caminho da imagem.") from exc
    if not image_path:
        raise IFoodImageError("O iFood recebeu a foto, mas devolveu um caminho vazio.")
    return image_path


def _image_path(image_url: str, cfg: dict, headers: dict, *, channel: str) -> str:
    """Resolve ``sha256(bytes) → imagePath`` em memória e no banco."""
    from django.db import transaction

    from shopman.shop.models import CatalogImageUpload

    payload, content_type, digest = _validated_image(image_url, cfg)
    merchant_id = str(cfg["merchant_id"])
    memory_key = (merchant_id, digest)
    if cached := _IMAGE_PATHS.get(memory_key):
        return cached

    record, _ = CatalogImageUpload.objects.get_or_create(
        channel_ref=channel,
        merchant_id=merchant_id,
        sha256=digest,
    )
    with transaction.atomic():
        record = CatalogImageUpload.objects.select_for_update().get(pk=record.pk)
        if not record.image_path:
            record.image_path = _upload_image(payload, content_type, cfg, headers)
            record.content_type = content_type
            record.size = len(payload)
            record.save(update_fields=["image_path", "content_type", "size", "updated_at"])
    _IMAGE_PATHS[memory_key] = record.image_path
    return record.image_path


def _check_rate_limit(resp: requests.Response) -> None:
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        raise IFoodRateLimitError(retry_after=retry_after)


def _headers(cfg: dict) -> tuple[dict | None, str]:
    """``(headers, "")`` or ``(None, reason)`` — the reason names the real cause.

    "No token" is not the same as "no credentials": the iFood edge also refuses
    the token call. Reporting the wrong cause sends whoever debugs to an
    environment variable that is already correct.
    """
    ensure_catalog_write_allowed(cfg)
    return ifood_auth.headers_with_reason({"Content-Type": "application/json"})


def _upsert_item(
    item: ProjectedItem,
    cfg: dict,
    headers: dict,
    *,
    in_stock: bool = True,
    image_path: str = "",
) -> None:
    ensure_catalog_write_allowed(cfg)
    merchant_id = cfg["merchant_id"]
    category_id = _resolve_category_id(item, cfg)
    url = f"{_base_url(cfg)}/catalog/v2.0/merchants/{merchant_id}/items"
    resp = requests.put(
        url,
        json=_item_payload(
            item,
            merchant_id=merchant_id,
            category_id=category_id,
            in_stock=in_stock,
            image_path=image_path,
        ),
        headers=headers,
        timeout=int(cfg.get("timeout") or 30),
    )
    _check_rate_limit(resp)
    resp.raise_for_status()


def _set_item_status(sku: str, status: str, cfg: dict, headers: dict) -> None:
    ensure_catalog_write_allowed(cfg)
    merchant_id = cfg["merchant_id"]
    url = f"{_base_url(cfg)}/catalog/v2.0/merchants/{merchant_id}/items/status"
    resp = requests.patch(
        url,
        json={"itemId": _item_uuid(merchant_id, sku), "status": status},
        headers=headers,
        timeout=int(cfg.get("timeout") or 30),
    )
    _check_rate_limit(resp)
    resp.raise_for_status()


class IFoodCatalogProjection:
    """Pushes catalog items to the iFood Merchant Catalog API (v2.0)."""

    def project(
        self,
        items: list[ProjectedItem],
        *,
        channel: str,
        full_sync: bool = False,
    ) -> ProjectionResult:
        cfg = _get_config(channel)
        try:
            ensure_catalog_write_allowed(cfg)
        except IFoodCatalogWriteBlocked as exc:
            return ProjectionResult(success=False, errors=[str(exc)], channel=channel)
        headers, reason = _headers(cfg)
        if not headers:
            return ProjectionResult(
                success=False,
                errors=[ifood_auth.failure_message(reason)],
                channel=channel,
            )

        from shopman.shop.services import external_availability

        errors: list[str] = []
        projected = 0
        for item in items:
            try:
                # Estoque só se consulta para o que as flags já deixariam vender.
                in_stock = (
                    external_availability.in_stock(item.sku, channel_ref=channel)
                    if item.is_published and item.is_sellable
                    else True
                )
                image_path = (
                    _image_path(item.image_url, cfg, headers, channel=channel)
                    if item.image_url
                    else ""
                )
                _upsert_item(item, cfg, headers, in_stock=in_stock, image_path=image_path)
                projected += 1
            except IFoodRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_ifood.project degraded", exc_info=True)
                errors.append(f"{item.sku}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=projected,
            errors=errors,
            channel=channel,
        )

    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult:
        cfg = _get_config(channel)
        try:
            ensure_catalog_write_allowed(cfg)
        except IFoodCatalogWriteBlocked as exc:
            return ProjectionResult(success=False, errors=[str(exc)], channel=channel)
        headers, reason = _headers(cfg)
        if not headers:
            return ProjectionResult(
                success=False,
                errors=[ifood_auth.failure_message(reason)],
                channel=channel,
            )

        errors: list[str] = []
        retracted = 0
        for sku in skus:
            try:
                _set_item_status(sku, "UNAVAILABLE", cfg, headers)
                retracted += 1
            except IFoodRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_ifood.retract degraded", exc_info=True)
                errors.append(f"{sku}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=retracted,
            errors=errors,
            channel=channel,
        )
