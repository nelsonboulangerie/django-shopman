"""Fábrica de canal de exibição para os testes de quadro e feed."""

from __future__ import annotations


def display_channel(
    ref, name, *, collections, fmt="", prices_from="", paused=None, rotate_seconds=0, items_per_page=0
):
    """Canal de exibição para os testes.

    ``fmt`` vazio = menuboard (rota nossa); ``google_merchant``/``meta_catalog`` =
    feed de plataforma (dialeto de terceiro). ``prices_from`` é o canal transacional
    de onde o preço vem. ``rotate_seconds``/``items_per_page`` ligam a rotação de
    páginas do quadro (ambos > 0, ou ambos 0 = tudo numa tela).
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
                "rotate_seconds": rotate_seconds,
                "items_per_page": items_per_page,
            }
        },
    )
