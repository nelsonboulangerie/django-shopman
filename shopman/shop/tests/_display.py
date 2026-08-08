"""Fábrica de canal de exibição para os testes de quadro e feed."""

from __future__ import annotations


def display_channel(ref, name, *, collections, fmt="", prices_from="", paused=None):
    """Canal de exibição para os testes.

    ``fmt`` vazio = menuboard (rota nossa); ``google_merchant``/``meta_catalog`` =
    feed de plataforma (dialeto de terceiro). ``prices_from`` é o canal transacional
    de onde o preço vem.
    """
    from shopman.shop.models import Channel

    return Channel.objects.create(
        ref=ref,
        name=name,
        commerce_policy=Channel.CommercePolicy.DISPLAY,
        is_active=True,
        config={
            "display": {
                "format": fmt,
                "collections": list(collections),
                "prices_from": prices_from,
                "paused_skus": list(paused or []),
            }
        },
    )
