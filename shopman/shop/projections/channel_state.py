"""Leitura do toggle "Ativo" de um canal para as superfícies.

A regra (período, relógio, janela) mora em ``shop.services.channel_switch``; a
apresentação lê daqui, do lado de leitura.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelCapabilities:
    """Read model with the channel capabilities needed by presentation."""

    fulfillment_types: tuple[str, ...]
    can_checkout: bool


def accepting_orders(channel_ref: str) -> bool:
    """O canal está ligado AGORA (o período do toggle resolvido pelo relógio)?"""
    from shopman.shop.services.channel_switch import is_channel_active

    return is_channel_active(channel_ref)


def channel_capabilities(channel_ref: str) -> ChannelCapabilities:
    """Materialize the policy result as a presentation-safe read model."""
    from shopman.shop.services.channel_policy import resolve_channel_policy

    policy = resolve_channel_policy(channel_ref)
    return ChannelCapabilities(
        fulfillment_types=policy.fulfillment_types,
        can_checkout=policy.can_checkout,
    )


__all__ = ["ChannelCapabilities", "accepting_orders", "channel_capabilities"]
