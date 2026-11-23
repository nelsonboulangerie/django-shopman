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


def done_text(value: Any) -> str:
    """O estado do recibo dito como efeito: ``success`` → ``Done.`` (a casa diz na língua dela)."""
    return {"success": "Done."}.get(str(value), str(value))


def items_text(value: Any) -> str:
    """As linhas dos termos: ``2 × Item A: XTS 9.00``, uma por linha. O nome vem do fato do item."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("itens sem lista")
    return "\n".join(f"{line['quantity']} × {line.get('name') or line['ref']}: {money_text(line['line_total'])}"
                     for line in value)


def fulfillment_text(value: Any) -> str:
    """O recebimento dos termos: o modo e, quando há, o começo da janela (instante canônico)."""
    if not isinstance(value, Mapping) or "mode" not in value:
        raise ValueError("recebimento sem modo")
    start = value.get("window_start")
    return f"{value['mode']} from {start}" if start else str(value["mode"])


def conditions_text(value: Any) -> str:
    """As condições dos termos, ``código: valor``; nenhuma vira texto vazio."""
    if not isinstance(value, Mapping):
        raise ValueError("condições sem mapa")
    return "; ".join(f"{code}: {item}" for code, item in value.items())


def options_text(value: Any) -> str:
    """Uma lista de opções (forma de pagamento, condição que falta), em texto neutro."""
    if not isinstance(value, (list, tuple)):
        raise ValueError("opções sem lista")
    return ", ".join(str(option) for option in value)


DEFAULT_FORMATTERS = {"price": money_text, "price_a": money_text, "price_b": money_text, "total": money_text,
                      "done": done_text, "items": items_text, "fulfillment": fulfillment_text,
                      "conditions": conditions_text, "payment_method": options_text, "missing": options_text}
