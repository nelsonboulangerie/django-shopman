"""Customer-facing availability copy for notifications and campaigns."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def availability_phrase(available_qty) -> str:
    """Human-ready availability line for approved WhatsApp templates."""
    qty = _positive_decimal(available_qty)
    if qty is None:
        return "Já está disponível para pedido."

    if qty == qty.to_integral_value():
        text = str(int(qty))
    else:
        text = format(qty.normalize(), "f").replace(".", ",")
    unit = "unidade" if qty == Decimal("1") else "unidades"
    return f"Neste momento ainda temos {text} {unit}."


def _positive_decimal(value) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        qty = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return qty if qty > 0 else None
