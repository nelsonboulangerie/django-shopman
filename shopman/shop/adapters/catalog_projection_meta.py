"""
Meta Catalog Projection adapter — Commerce Catalog via Graph ``items_batch``.

Implements ``CatalogProjectionBackend`` (Offerman) by pushing the platform channel
(``meta-catalog``) to a **Meta Commerce Catalog**, which backs Instagram Shopping +
Facebook Shop (and, curated, WhatsApp — Arc G). One adapter, three surfaces: the
catalog is the single source Meta fans out from. Este envio é o ESCRITOR ÚNICO do
catálogo na Meta (``docs/plans/CATALOG-PUSH-GOOGLE-META-PLAN.md``).

A decisão de cada item (entra, preço, disponível, oculto) NÃO mora aqui: o handler
entrega ``ProjectedItem.metadata["display"]``, a decisão de ``services/display_catalog``
que o XML do feed também lê. Este módulo só traduz para a grafia da Meta.

Contract (Graph API, ``POST /v{N}/{catalog_id}/items_batch``)
-------------------------------------------------------------

Body::

    {
      "item_type": "PRODUCT_ITEM",
      "allow_upsert": true,
      "requests": [
        {"method": "UPDATE", "retailer_id": "<sku>", "data": { …product fields… }},
        …
      ]
    }

- ``retailer_id`` is our stable SKU — re-syncing upserts the same product instead of
  duplicating (``allow_upsert`` makes UPDATE create-if-missing, so we never need to
  track Meta's internal id).
- **project** → ``method: "UPDATE"`` with the full ``data``. Pausado sai
  ``availability: "out of stock"`` ("esgotado" na loja, fora dos anúncios); oculto sai
  ``status: "archived"`` ("Only active items can be seen by people in your ads,
  shops", developers.facebook.com/docs/commerce-platform/catalog/fields).
- **retract** → ``method: "UPDATE"`` with ``data: {"status": "archived"}``: o item
  saiu da composição do canal. Arquivar é reversível, e DELETE jogaria fora o item.
  (Batch cap ≤5000 requests/call; Meta throttles ~100 calls/h.)

Price format (documented choice)
--------------------------------
Meta's **batch** API takes ``price`` as an **integer in the currency's minor unit**
(cents) plus a separate ``currency`` (ISO 4217) — NOT the ``"9.99 BRL"`` string the
CSV/RSS *feed* uses. That lines up 1:1 with our ``_q`` centavos convention.

Availability enum is ``"in stock"`` / ``"out of stock"`` (with the space).

Authentication is a System User token via
:mod:`shopman.shop.services.meta_auth` (Bearer). Config lives in ``SHOPMAN_META``:

    catalog_id:    Meta Commerce Catalog id.
    access_token:  System User access token (Business Manager).
    api_version:   Graph version (default ``v21.0``).
    api_base:      Base URL (default ``https://graph.facebook.com``).
    currency:      ISO 4217 for ``price`` (default ``BRL``).
    batch_size:    Max requests per ``items_batch`` call (default 5000, capped there).
"""

from __future__ import annotations

import logging

import requests
from shopman.offerman.protocols.projection import ProjectedItem, ProjectionResult

from shopman.shop.services import display_catalog, meta_auth

logger = logging.getLogger(__name__)

_MAX_BATCH = 5000  # Graph hard cap for items_batch
_AVAILABILITY_IN = "in stock"
_AVAILABILITY_OUT = "out of stock"


class MetaRateLimitError(Exception):
    """Raised when the Graph API responds with 429 Too Many Requests."""

    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Meta rate limit hit; retry after {retry_after}s")


def _get_config() -> dict:
    from django.conf import settings

    return getattr(settings, "SHOPMAN_META", {}) or {}


def _base_url(cfg: dict) -> str:
    return str(cfg.get("api_base") or "https://graph.facebook.com").rstrip("/")


def _api_version(cfg: dict) -> str:
    return str(cfg.get("api_version") or "v21.0").strip("/")


def _endpoint(cfg: dict) -> str:
    return f"{_base_url(cfg)}/{_api_version(cfg)}/{cfg['catalog_id']}/items_batch"


def _batch_size(cfg: dict) -> int:
    size = int(cfg.get("batch_size") or _MAX_BATCH)
    return max(1, min(size, _MAX_BATCH))


def _chunk(seq: list, size: int):
    for start in range(0, len(seq), size):
        yield seq[start : start + size]


def item_data(item: display_catalog.DisplayItem, cfg: dict) -> dict:
    """O ``data`` de um produto, traduzido da decisão de ``display_catalog``."""
    data: dict = {
        "title": item.title,
        "description": item.description,
        "availability": _AVAILABILITY_IN if item.available else _AVAILABILITY_OUT,
        "status": "archived" if item.hidden else "active",
        "condition": item.condition or "new",
        # Integer minor units (cents) + separate currency — see module docstring.
        "price": int(item.price_q),
        "currency": str(cfg.get("currency") or "BRL"),
        "link": item.link,
        "image_link": item.image_link,
        "product_type": item.product_type,
        "custom_label_0": item.custom_label_0,  # coleção do canal (segmentação de ads)
    }
    if item.brand:
        data["brand"] = item.brand
    if item.gtin:
        data["gtin"] = item.gtin
    if item.google_product_category:
        data["google_product_category"] = item.google_product_category
    # Galeria → additional_image_link (string separada por vírgula, até 10 no Meta).
    if item.additional_image_links:
        data["additional_image_link"] = ",".join(item.additional_image_links)
    return data


def build_batch_requests(items: list[ProjectedItem], cfg: dict) -> list[dict]:
    """The ``requests`` list for a project (upsert) — one UPDATE per item.

    Item sem a decisão do canal (``metadata["display"]``) não tem o que dizer à
    Meta e falha alto: enviar adivinhando seria publicar o que a casa não decidiu.
    """
    requests_list = []
    for item in items:
        decided = item.metadata.get("display") if isinstance(item.metadata, dict) else None
        if not isinstance(decided, display_catalog.DisplayItem):
            raise ValueError(f"{item.sku}: item sem a decisão do canal (display_catalog)")
        requests_list.append({"method": "UPDATE", "retailer_id": item.sku, "data": item_data(decided, cfg)})
    return requests_list


def build_retract_requests(skus: list[str]) -> list[dict]:
    """The ``requests`` list for a retract — o item saiu do canal: arquivado."""
    return [{"method": "UPDATE", "retailer_id": sku, "data": {"status": "archived"}} for sku in skus]


def _check_rate_limit(resp: requests.Response) -> None:
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        raise MetaRateLimitError(retry_after=retry_after)


def _post_batch(requests_list: list[dict], cfg: dict, headers: dict) -> None:
    """POST one chunk of ``requests`` to items_batch (raises on 429 / HTTP error)."""
    resp = requests.post(
        _endpoint(cfg),
        json={
            "item_type": "PRODUCT_ITEM",
            "allow_upsert": True,
            "requests": requests_list,
        },
        headers=headers,
        timeout=int(cfg.get("timeout") or 30),
    )
    _check_rate_limit(resp)
    resp.raise_for_status()


class MetaCatalogProjection:
    """Pushes the platform channel to a Meta Commerce Catalog (Graph items_batch)."""

    def project(
        self,
        items: list[ProjectedItem],
        *,
        channel: str,
        full_sync: bool = False,
    ) -> ProjectionResult:
        cfg = _get_config()
        headers = meta_auth.authorized_headers({"Content-Type": "application/json"})
        if not headers:
            return ProjectionResult(
                success=False,
                errors=["Meta não configurado (access_token/catalog_id)"],
                channel=channel,
            )

        errors: list[str] = []
        projected = 0
        for chunk in _chunk(build_batch_requests(items, cfg), _batch_size(cfg)):
            try:
                _post_batch(chunk, cfg, headers)
                projected += len(chunk)
            except MetaRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_meta.project degraded", exc_info=True)
                skus = ", ".join(r["retailer_id"] for r in chunk)
                errors.append(f"{skus}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=projected,
            errors=errors,
            channel=channel,
        )

    def retract(self, skus: list[str], *, channel: str) -> ProjectionResult:
        cfg = _get_config()
        headers = meta_auth.authorized_headers({"Content-Type": "application/json"})
        if not headers:
            return ProjectionResult(
                success=False,
                errors=["Meta não configurado (access_token/catalog_id)"],
                channel=channel,
            )

        errors: list[str] = []
        retracted = 0
        for chunk in _chunk(build_retract_requests(skus), _batch_size(cfg)):
            try:
                _post_batch(chunk, cfg, headers)
                retracted += len(chunk)
            except MetaRateLimitError:
                raise
            except Exception as exc:
                logger.debug("catalog_projection_meta.retract degraded", exc_info=True)
                ids = ", ".join(r["retailer_id"] for r in chunk)
                errors.append(f"{ids}: {exc}")

        return ProjectionResult(
            success=len(errors) == 0,
            projected=retracted,
            errors=errors,
            channel=channel,
        )
