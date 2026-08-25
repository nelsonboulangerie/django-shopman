"""Console notification adapter for development and testing."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    ctx = context or {}
    order_ref = ctx.get("order_ref") or ctx.get("order", {}).get("ref", "")
    status = ctx.get("status_label") or ctx.get("status", "")
    shop_name = ctx.get("shop_name", "Loja")

    lines = [
        f"📱 *{shop_name}*",
        f"Evento: `{template}`",
    ]
    if order_ref:
        lines.append(f"Pedido: *{order_ref}*")
    if status:
        lines.append(f"Status: {status}")
    if ctx.get("purchase_ref"):
        lines.append(f"Compra: *{ctx['purchase_ref']}*")
    if ctx.get("receipt_ref"):
        lines.append(f"Recebimento: *{ctx['receipt_ref']}*")
    if ctx.get("supplier_name"):
        lines.append(f"Fornecedor: {ctx['supplier_name']}")
    if ctx.get("document_ref"):
        lines.append(f"Documento: {ctx['document_ref']}")
    if ctx.get("reason"):
        lines.append(f"Motivo: {ctx['reason']}")
    if ctx.get("lines_text"):
        lines.append(str(ctx["lines_text"]))
    for key in ("customer_name", "total_display", "eta_display"):
        if ctx.get(key):
            lines.append(f"{key}: {ctx[key]}")

    logger.info(
        "\n╔══ NOTIFICAÇÃO ══╗\nTo: %s\n%s\n╚════════════════╝",
        recipient,
        "\n".join(lines),
    )
    return True


def is_available(recipient: str | None = None, **config) -> bool:
    """Console adapter is always available."""
    return True
