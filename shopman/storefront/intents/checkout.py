"""Checkout: o troco para dinheiro na entrega, lido do que o cliente digitou.

Função pura chamada pelo checkout da loja (``parse_change_for``, em
``storefront/api/views.py``). A data de encomenda com lead time mora no
orquestrador (``shop/policies/preorder_date.preorder_date_errors``).
"""

from __future__ import annotations

# ── Payment helpers ───────────────────────────────────────────────────────────


def parse_change_for(raw: str) -> int:
    """'50'/'50,00'/'50.00' (Reais) → centavos. Vazio/inválido → 0."""
    text = (raw or "").strip().replace("R$", "").replace(" ", "").replace(",", ".")
    if not text:
        return 0
    try:
        value = float(text)
    except ValueError:
        return 0
    return max(int(round(value * 100)), 0)
