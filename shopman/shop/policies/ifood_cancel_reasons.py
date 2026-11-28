"""Quais motivos da lista única o pedido do iFood oferece (dono, 07/11/2026)."""

from __future__ import annotations

#: Motivos que o pedido do iFood não oferece no recusar/cancelar: o pedido do iFood
#: é pago no iFood, e o "cliente pediu" chega pela negociação do próprio iFood.
IFOOD_HIDDEN_KEYS = frozenset({"customer_request", "payment_not_confirmed"})


def offered_on_ifood(key: str) -> bool:
    """O motivo aparece no recusar/cancelar de um pedido do iFood?"""
    return str(key or "").strip() not in IFOOD_HIDDEN_KEYS


__all__ = ["IFOOD_HIDDEN_KEYS", "offered_on_ifood"]
