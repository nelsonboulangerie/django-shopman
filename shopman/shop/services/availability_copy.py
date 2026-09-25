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


def availability_note(available_qty) -> str:
    """A quantidade no aviso de fornada, SEM ponto final e nunca vazia.

    O ponto é do texto (``notification_copy``): o template da Meta não pode
    terminar em variável, e variável vazia ele recusa. Texto do dono, 25/09/2026.
    """
    qty = _positive_decimal(available_qty)
    if qty is None:
        return "Já está disponível para pedido"
    if qty == qty.to_integral_value():
        text = str(int(qty))
    else:
        text = format(qty.normalize(), "f").replace(".", ",")
    if qty == Decimal("1"):
        return f"No momento temos {text} un. disponível"
    return f"No momento temos {text} un. disponíveis"


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
