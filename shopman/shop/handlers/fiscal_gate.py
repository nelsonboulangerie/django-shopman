"""Porteiro fiscal do catálogo — recusa publicar vendável sem classificação.

Por que signal e não validação de form: o form do admin é **uma** porta. Sync de
catálogo do iFood, seed, scripts e comandos criam ``Product``/``ListingItem``
pelo ORM e nunca passam por form nenhum. O ``pre_save`` é o ponto por onde todas
elas passam.

Dois receivers, complementares — a publicação exige que produto e item de
vitrine concordem (``Listing``: "Both levels must agree"), então quem liga a
última chave é quem ouve a recusa:

- ``ListingItem``: publicar o item de um produto já publicado;
- ``Product``: publicar um produto que já tem item de vitrine publicado (ou
  apagar a classificação de um produto que já está no ar).

Desligado por padrão (``SHOPMAN_FISCAL_REQUIRE_CLASSIFICATION_ON_PUBLISH``):
no pré-go-live o catálogo ainda está sendo classificado com o contador. Com a
chave desligada os receivers custam um ``getattr`` e voltam.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save

from shopman.shop.services import fiscal_catalog

logger = logging.getLogger(__name__)


def _refuse(product, listing_ref: str, errors: list[str]) -> None:
    where = f" na vitrine '{listing_ref}'" if listing_ref else ""
    raise ValidationError(
        f"Produto {product.sku} ({product.name}) não pode ser publicado{where}: "
        f"{' '.join(errors)} Classifique em Admin → Produtos → Fiscal (perfil + NCM; "
        "CEST na revenda) ou desligue "
        f"{fiscal_catalog.SETTING_REQUIRE_ON_PUBLISH}."
    )


def _on_listing_item_pre_save(sender, instance, **kwargs) -> None:
    if not fiscal_catalog.publication_gate_enabled():
        return
    if not (instance.is_published and instance.is_sellable):
        return
    listing = instance.listing
    if not listing.is_active:
        return
    errors = fiscal_catalog.publication_errors(instance.product, listing_ref=listing.ref)
    if errors:
        _refuse(instance.product, listing.ref, errors)


def _on_product_pre_save(sender, instance, **kwargs) -> None:
    if not fiscal_catalog.publication_gate_enabled():
        return
    if instance.pk is None:
        return  # produto novo ainda não está em vitrine nenhuma
    errors = fiscal_catalog.publication_errors(instance)
    if errors and fiscal_catalog.has_selling_publication(instance.pk):
        _refuse(instance, "", errors)


def connect() -> None:
    """Liga os receivers. Chamado uma vez por ``register_all``."""
    from shopman.offerman.models import ListingItem, Product

    pre_save.connect(
        _on_listing_item_pre_save,
        sender=ListingItem,
        dispatch_uid="shopman.shop.handlers.fiscal_gate.listing_item",
        weak=False,
    )
    pre_save.connect(
        _on_product_pre_save,
        sender=Product,
        dispatch_uid="shopman.shop.handlers.fiscal_gate.product",
        weak=False,
    )
