"""Leitura do toggle "Ativo" de um canal para as superfícies.

A regra (período, relógio, janela) mora em ``shop.services.channel_switch``; a
apresentação lê daqui, do lado de leitura.
"""

from __future__ import annotations


def accepting_orders(channel_ref: str) -> bool:
    """O canal está ligado AGORA (o período do toggle resolvido pelo relógio)?"""
    from shopman.shop.services.channel_switch import is_channel_active

    return is_channel_active(channel_ref)


__all__ = ["accepting_orders"]
