"""Receivers que mantêm a vitrine espelhada igual à fonte (``services/listing_mirror``).

Síncronos, na mesma transação da escrita: se a escrita na loja online volta atrás,
o espelho volta junto, e nunca há uma janela em que o WhatsApp oferece o que o site
já tirou.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save

logger = logging.getLogger(__name__)


def _on_listing_item_changed(sender, instance, **kwargs) -> None:
    from shopman.shop.services import listing_mirror

    if listing_mirror.is_syncing() or kwargs.get("raw"):
        return
    from django.core.exceptions import ObjectDoesNotExist

    try:
        listing_ref = instance.listing.ref
    except ObjectDoesNotExist:  # a vitrine inteira está sendo apagada
        return
    if not listing_ref:
        return
    listing_mirror.realign(listing_ref, product_ids=[instance.product_id])


def _on_channel_saved(sender, instance, **kwargs) -> None:
    from shopman.shop.services import listing_mirror

    if kwargs.get("raw") or not listing_mirror.source_ref_from_config(instance.config):
        return
    listing_mirror.realign(instance.ref)


def connect() -> None:
    """Liga os receivers. Chamado uma vez por ``register_all``."""
    from shopman.offerman.models import ListingItem

    from shopman.shop.models import Channel

    post_save.connect(
        _on_listing_item_changed,
        sender=ListingItem,
        dispatch_uid="shopman.shop.handlers.listing_mirror.item_saved",
        weak=False,
    )
    post_delete.connect(
        _on_listing_item_changed,
        sender=ListingItem,
        dispatch_uid="shopman.shop.handlers.listing_mirror.item_deleted",
        weak=False,
    )
    post_save.connect(
        _on_channel_saved,
        sender=Channel,
        dispatch_uid="shopman.shop.handlers.listing_mirror.channel_saved",
        weak=False,
    )
