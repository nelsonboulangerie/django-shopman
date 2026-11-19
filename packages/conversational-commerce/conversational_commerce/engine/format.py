"""Formatação neutra dos valores de lastro. A casa troca pela dela (moeda, data, língua)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any


def money_text(value: Any) -> str:
    """``{"price_minor": 450, "currency": "XTS"}`` → ``XTS 4.50`` (duas casas, neutro)."""
    if not isinstance(value, Mapping) or "price_minor" not in value or "currency" not in value:
        raise ValueError("valor sem price_minor e currency")
    amount = (Decimal(value["price_minor"]) / 100).quantize(Decimal("0.01"))
    return f"{value['currency']} {amount}"


DEFAULT_FORMATTERS = {"price": money_text, "price_a": money_text, "price_b": money_text, "total": money_text}
