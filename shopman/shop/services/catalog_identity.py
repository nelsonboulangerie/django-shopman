"""Resolve a identidade remota usada pela projeção de catálogo iFood."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_UUID_NS = uuid.UUID("f0f4d7e2-0e2a-5c7a-9d1b-6b1e2a3c4d5e")


class CatalogIdentityConflict(ValueError):
    """O vínculo não permite escolher uma identidade remota sem ambiguidade."""


@dataclass(frozen=True, slots=True)
class CatalogIdentity:
    item_id: str
    product_id: str
    category_ref: str
    origin: str


def _derived_identity(merchant_id: str, sku: str) -> CatalogIdentity:
    return CatalogIdentity(
        item_id=str(uuid.uuid5(_UUID_NS, f"{merchant_id}:item:{sku}")),
        product_id=str(uuid.uuid5(_UUID_NS, f"{merchant_id}:product:{sku}")),
        category_ref="",
        origin="derived",
    )


def resolve_catalog_identity(
    sku: str,
    channel: str,
    *,
    config: dict | None = None,
) -> CatalogIdentity:
    """Retorna a identidade iFood vigente de ``sku`` no escopo configurado.

    ``catalog_id`` e ``catalog_context`` estreitam o escopo quando configurados.
    Sem esses dois valores, um único vínculo da conta continua sendo utilizável;
    mais de um vínculo vira conflito explícito em vez de escolha por ordem do banco.
    """
    if config is None:
        from django.conf import settings

        config = dict(getattr(settings, "SHOPMAN_IFOOD", {}) or {})

    merchant_id = str(config.get("merchant_id") or "")
    derived = _derived_identity(merchant_id, sku)
    if not channel:
        return derived

    from shopman.shop.models import CatalogBinding

    bindings = CatalogBinding.objects.filter(
        channel__ref=channel,
        product__sku=sku,
        provider="ifood",
        account_ref=merchant_id,
    )
    catalog_ref = str(config.get("catalog_id") or config.get("catalog_ref") or "").strip()
    context = str(config.get("catalog_context") or config.get("context") or "").strip()
    if catalog_ref:
        bindings = bindings.filter(catalog_ref=catalog_ref)
    if context:
        bindings = bindings.filter(context=context)

    matches = list(bindings.order_by("-revision", "-confirmed_at", "-pk")[:2])
    if len(matches) > 1:
        raise CatalogIdentityConflict(
            f"Mais de um vínculo iFood serve ao SKU {sku!r} no escopo configurado."
        )
    if not matches:
        other_accounts = CatalogBinding.objects.filter(
            channel__ref=channel,
            product__sku=sku,
            provider="ifood",
        ).exclude(account_ref=merchant_id)
        if other_accounts.exists():
            logger.warning(
                "catalog_identity.binding_ignored sku=%s channel=%s merchant=%s reason=account_mismatch",
                sku,
                channel,
                merchant_id,
            )
        return derived

    binding = matches[0]
    conflicting_skus = list(
        CatalogBinding.objects.filter(
            provider="ifood",
            account_ref=binding.account_ref,
            resource_id=binding.resource_id,
        )
        .exclude(product_id=binding.product_id)
        .values_list("product__sku", flat=True)
        .distinct()[:2]
    )
    if conflicting_skus:
        raise CatalogIdentityConflict(
            f"O item remoto {binding.resource_id!r} está vinculado aos SKUs "
            f"{sku!r} e {conflicting_skus[0]!r}."
        )

    return CatalogIdentity(
        item_id=binding.resource_id,
        product_id=binding.external_product_ref,
        category_ref=binding.category_ref,
        origin="binding",
    )
