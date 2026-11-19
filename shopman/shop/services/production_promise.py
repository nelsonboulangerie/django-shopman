"""A promessa de produção que um pedido aceito perdeu (F-6 do plano do Gestor, #2547).

Cancelar um lote solta as reservas que ficaram sem lastro
(``handlers._stock_receivers.on_production_voided``). Até aqui só a SACOLA aberta
ficava sabendo; o pedido aceito, pago e com "Pedido garantido para amanhã" na tela
do cliente perdia a reserva em silêncio, e o Gestor não mostrava nada.

Este módulo transforma a perda em FATO DO PEDIDO, sem decidir nada por ninguém:

- um evento na linha do tempo do pedido (``production_hold_lost``), com o item, a
  quantidade, a data e o lote;
- um aviso no sino do Gestor (``order_promise_lost``, público ``orders``), um por
  pedido e item, nomeando o pedido, o item e o que fazer.

Nunca cancela, remarca nem fala com o cliente: a conversa é decisão de gente, como
no dia fechado (``closed_day_orders``).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.shop.services.observability import create_operator_alert

logger = logging.getLogger(__name__)

ALERT_TYPE = "order_promise_lost"
EVENT_TYPE = "production_hold_lost"

#: Pedido que ainda vai sair da loja. Os demais já saíram (ou acabaram) e o
#: lote cancelado não os alcança mais.
OPEN_STATUSES = ("new", "accepted", "preparing", "ready")

ORDER_REFERENCE_PREFIX = "order:"


def order_ref_from_hold_reference(reference) -> str:
    """``"order:PDV-1"`` → ``"PDV-1"``; qualquer outra coisa (sacola) → ``""``."""
    raw = str(reference or "")
    return raw[len(ORDER_REFERENCE_PREFIX):] if raw.startswith(ORDER_REFERENCE_PREFIX) else ""


def _format_qty(qty) -> str:
    value = Decimal(str(qty or 0))
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))
    return format(value.normalize(), "f").replace(".", ",")


def _product_name(sku: str) -> str:
    try:
        from shopman.offerman.models import Product

        product = Product.objects.filter(sku=sku).only("name").first()
    except Exception:
        logger.debug("production_promise: product lookup failed for %s", sku, exc_info=True)
        product = None
    return (product.name if product is not None else "") or sku


def announce_lost_holds(lost_by_order: dict[str, Decimal], *, sku: str, date, work_order=None) -> int:
    """Registra no pedido e avisa o Gestor. Devolve quantos avisos saíram.

    ``lost_by_order``: ``{order_ref: quantidade que perdeu a reserva}`` deste SKU.
    Best-effort por pedido: um pedido que falha não impede o aviso dos outros.
    """
    if not lost_by_order:
        return 0

    from shopman.orderman.models import Order

    name = _product_name(sku)
    day = date.strftime("%d/%m") if hasattr(date, "strftime") else str(date)
    wo_ref = str(getattr(work_order, "ref", "") or "")
    created = 0
    orders = Order.objects.filter(ref__in=list(lost_by_order), status__in=OPEN_STATUSES).order_by("ref")
    for order in orders:
        qty_text = _format_qty(lost_by_order.get(order.ref) or Decimal("0"))
        try:
            order.emit_event(
                event_type=EVENT_TYPE,
                actor="system",
                payload={
                    "sku": sku,
                    "product_name": name,
                    "qty": qty_text,
                    "date": date.isoformat() if hasattr(date, "isoformat") else str(date),
                    "work_order_ref": wo_ref,
                    "reason": "production_voided",
                },
            )
        except Exception:
            logger.warning("production_promise: could not record event on %s", order.ref, exc_info=True)

        lot = f" (lote {wo_ref})" if wo_ref else ""
        lacks = "falta" if qty_text == "1" else "faltam"
        message = (
            f"Pedido {order.ref}: a produção de {name} para {day} foi cancelada{lot}: "
            f"{lacks} {qty_text} un. Avise o cliente, remarque ou cancele o pedido."
        )
        alert = create_operator_alert(
            type=ALERT_TYPE,
            severity="error",
            message=message,
            order_ref=order.ref,
            # Por pedido + item + data: o mesmo cancelamento não avisa duas vezes,
            # e outro item do mesmo pedido avisa à parte.
            dedupe_key=f"de {name} para {day}",
            debounce_minutes=24 * 60,
            sku=sku,
            work_order_ref=wo_ref,
        )
        if alert is not None:
            created += 1
    return created
