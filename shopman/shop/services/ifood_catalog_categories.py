"""Categorias do catálogo iFood e o mapa local de coleções.

O transporte só executa quando a política de escrita confirma um merchant de
teste. O mapa administrável mora no JSON do canal, sem criar outra fonte de
identidade remota e sem alterar os vínculos de itens.
"""

from __future__ import annotations

from typing import Any

import requests
from django.db import transaction
from shopman.offerman.models import Collection

from shopman.shop.models import Channel
from shopman.shop.services import ifood_auth


class IFoodCategoryOperationError(ValueError):
    """Falha segura de configuração, autenticação ou resposta remota."""


class IFoodCategoryConflict(IFoodCategoryOperationError):
    """A categoria já existe ou mudou e precisa ser reconciliada."""


def _adapter_contract():
    # Import tardio evita um ciclo: o adapter consulta este módulo para resolver
    # o mapa administrável, e este módulo reutiliza a guarda canônica do adapter.
    from shopman.shop.adapters.catalog_projection_ifood import (
        IFoodRateLimitError,
        ensure_catalog_write_allowed,
    )

    return IFoodRateLimitError, ensure_catalog_write_allowed


def _channel(channel_ref: str, *, lock: bool = False) -> Channel:
    query = Channel.objects.select_for_update() if lock else Channel.objects
    channel = query.filter(ref=channel_ref).first()
    if channel is None:
        raise IFoodCategoryOperationError("Canal não encontrado.")
    return channel


def _managed_config(channel: Channel) -> dict[str, Any]:
    config = channel.config if isinstance(channel.config, dict) else {}
    value = config.get("ifood_catalog")
    return value if isinstance(value, dict) else {}


def category_mapping(
    channel_ref: str,
    legacy_config: dict | None = None,
    *,
    channel: Channel | None = None,
) -> tuple[dict[str, str], str]:
    """Retorna mapa/default administráveis, com fallback para settings antigos."""
    managed = _managed_config(channel or _channel(channel_ref))
    managed_map = managed.get("category_map")
    legacy_config = legacy_config if isinstance(legacy_config, dict) else {}
    legacy_map = legacy_config.get("catalog_category_map")
    mapping = dict(legacy_map) if isinstance(legacy_map, dict) else {}
    if isinstance(managed_map, dict):
        mapping.update({str(key): str(value) for key, value in managed_map.items() if key and value})
    default = managed.get("default_category_ref")
    if not isinstance(default, str) or not default:
        default = legacy_config.get("catalog_default_category")
    return mapping, str(default or "")


@transaction.atomic
def set_collection_category(*, channel_ref: str, collection_ref: str, category_ref: str) -> dict[str, str]:
    """Liga uma coleção existente a uma categoria remota escolhida."""
    if not isinstance(collection_ref, str) or not collection_ref.strip():
        raise IFoodCategoryOperationError("Coleção é obrigatória.")
    if not isinstance(category_ref, str) or not category_ref.strip():
        raise IFoodCategoryOperationError("Categoria remota é obrigatória.")
    collection_ref = collection_ref.strip()
    category_ref = category_ref.strip()
    if not Collection.objects.filter(ref=collection_ref).exists():
        raise IFoodCategoryOperationError("Coleção não encontrada.")
    channel = _channel(channel_ref, lock=True)
    config = dict(channel.config or {})
    managed = dict(_managed_config(channel))
    mapping = dict(managed.get("category_map") or {})
    mapping[collection_ref] = category_ref
    managed["category_map"] = mapping
    config["ifood_catalog"] = managed
    channel.config = config
    channel.save(update_fields=["config"])
    return {str(key): str(value) for key, value in mapping.items()}


def resolve_category_ref(*, channel_ref: str, collection_ref: str | None, legacy_config: dict) -> str:
    """Resolve somente configuração; mapa vazio nunca cria categoria."""
    mapping, default = category_mapping(channel_ref, legacy_config)
    if collection_ref and collection_ref in mapping:
        return mapping[collection_ref]
    if default:
        return default
    raise IFoodCategoryOperationError(
        f"Nenhuma categoria iFood foi escolhida para a coleção {collection_ref!r}."
    )


def _request(
    method: str,
    *,
    channel_ref: str,
    catalog_ref: str,
    category_ref: str = "",
    payload: dict | None = None,
):
    from django.conf import settings

    rate_limit_error, ensure_catalog_write_allowed = _adapter_contract()
    cfg = getattr(settings, "SHOPMAN_IFOOD", {}) or {}
    ensure_catalog_write_allowed(cfg)
    merchant_ref = cfg.get("merchant_id")
    if not isinstance(merchant_ref, str) or not merchant_ref:
        raise IFoodCategoryOperationError("Merchant iFood não configurado.")
    _channel(channel_ref)
    headers, reason = ifood_auth.headers_with_reason({"Content-Type": "application/json"})
    if not headers:
        raise IFoodCategoryOperationError(ifood_auth.failure_message(reason))
    base = str(cfg.get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")
    path = f"/catalog/v2.0/merchants/{merchant_ref}/catalogs/{catalog_ref}/categories"
    if category_ref:
        path += f"/{category_ref}"
    elif method == "get":
        path += "?includeItems=true"
    kwargs = {"headers": headers, "timeout": int(cfg.get("timeout") or 30)}
    if payload is not None:
        kwargs["json"] = payload
    response = getattr(requests, method)(base + path, **kwargs)
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 60))
        raise rate_limit_error(retry_after=retry_after, intention=payload)
    if response.status_code == 409:
        raise IFoodCategoryConflict(
            "O iFood recusou a categoria por conflito. Atualize a lista e reconcilie a categoria existente."
        )
    try:
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError, TypeError):
        raise IFoodCategoryOperationError(
            f"A operação de categoria retornou HTTP {response.status_code}."
        ) from None
    return body


def list_categories(*, channel_ref: str, catalog_ref: str):
    return _request("get", channel_ref=channel_ref, catalog_ref=catalog_ref)


def create_category(
    *,
    channel_ref: str,
    catalog_ref: str,
    name: str,
    status: str = "AVAILABLE",
    template: str = "DEFAULT",
    category_ref: str = "",
    external_code: str = "",
    index: int | None = None,
):
    payload: dict[str, Any] = {"name": name, "status": status, "template": template}
    if category_ref:
        payload["id"] = category_ref
    if external_code:
        payload["externalCode"] = external_code
    if index is not None:
        payload["index"] = index
    return _request("post", channel_ref=channel_ref, catalog_ref=catalog_ref, payload=payload)


def rename_category(*, channel_ref: str, catalog_ref: str, category_ref: str, name: str):
    return _request(
        "patch", channel_ref=channel_ref, catalog_ref=catalog_ref,
        category_ref=category_ref, payload={"name": name},
    )


def reorder_category(*, channel_ref: str, catalog_ref: str, category_ref: str, index: int):
    return _request(
        "patch", channel_ref=channel_ref, catalog_ref=catalog_ref,
        category_ref=category_ref, payload={"index": index},
    )


def set_category_status(*, channel_ref: str, catalog_ref: str, category_ref: str, status: str):
    return _request(
        "patch", channel_ref=channel_ref, catalog_ref=catalog_ref,
        category_ref=category_ref, payload={"status": status},
    )


__all__ = [
    "IFoodCategoryConflict",
    "IFoodCategoryOperationError",
    "category_mapping",
    "create_category",
    "list_categories",
    "rename_category",
    "reorder_category",
    "resolve_category_ref",
    "set_category_status",
    "set_collection_category",
]
