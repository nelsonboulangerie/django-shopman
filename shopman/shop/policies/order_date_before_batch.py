"""Decide se a data de um pedido é anterior à fornada que a sacola espera.

"Um pedido, uma data": a sacola guarda o item numa fornada planejada, e o pedido
só pode ser para o dia dela ou depois. Pedido para antes seria uma promessa
impossível (retirar hoje o pão que sai na quarta; laudo de 09/11/2026). A recusa
nomeia o item e o dia da fornada, e aponta o campo da data.

Só contam reservas de itens DESTE pedido: reserva tardia de SKU que já saiu da
sacola é sobra não reconciliada, e não recusa nada.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone

from shopman.shop.adapters import get_adapter

logger = logging.getLogger(__name__)

ORDER_DATE_BEFORE_BATCH = "order_date_before_batch"

_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def late_holds_of_order(session_key: str, order_day, items) -> list[tuple[str, str, object]]:
    """As reservas da sacola, de itens deste pedido, presas a fornada depois de ``order_day``."""
    from shopman.shop.services import availability

    too_late = availability.session_holds_after(session_key, order_day)
    if not too_late:
        return []
    order_skus: set[str] = set()
    for item in items or ():
        sku = _line_value(item, "sku")
        if not sku:
            continue
        order_skus.add(sku)
        order_skus.update(_component_skus(sku))
    return [row for row in too_late if row[1] in order_skus]


def order_date_before_batch_refusal(session_key: str, order_day, items):
    """A recusa para ``order_day``, ou ``None`` quando a data serve.

    A mesma pergunta do gate de commit, para quem valida a data ANTES de fechar
    (a concierge, ao gravar retirada ou entrega). Devolve o ``ValidationError``
    pronto (item, dia da fornada, campo da data).
    """
    if not session_key or order_day is None:
        return None
    too_late = late_holds_of_order(session_key, order_day, items)
    if not too_late:
        return None
    return refusal_error(items, too_late, order_day)


def batch_day_phrase(batch_date, *, today=None) -> str:
    """"amanhã, 10/11" / "na quarta, 11/11" / "no sábado, 14/11": quando a fornada sai.

    Só se fala de fornada que sai DEPOIS do dia do pedido: não há frase de "hoje".
    """
    today = today or timezone.localdate()
    stamp = batch_date.strftime("%d/%m")
    if (batch_date - today).days == 1:
        return f"amanhã, {stamp}"
    weekday = _WEEKDAYS[batch_date.weekday()]
    article = "no" if batch_date.weekday() >= 5 else "na"
    return f"{article} {weekday}, {stamp}"


def refusal_error(items, too_late: list, order_day):
    """O ``ValidationError`` da recusa, no dialeto das outras recusas do gate de commit.

    ``checkout.map_checkout_error`` usa o ``field`` do contexto.
    """
    from shopman.orderman.exceptions import ValidationError

    _hold_id, late_sku, batch_date = max(too_late, key=lambda row: row[2])
    display = late_sku
    for item in items or ():
        sku = _line_value(item, "sku")
        if not sku:
            continue
        if sku == late_sku or late_sku in _component_skus(sku):
            display = _line_value(item, "name") or _product_name(sku) or sku
            break
    return ValidationError(
        code=ORDER_DATE_BEFORE_BATCH,
        message=f"{display} sai {batch_day_phrase(batch_date)}. Escolha essa data ou uma depois dela.",
        context={
            "sku": late_sku,
            "field": "delivery_date",
            "order_date": order_day.isoformat(),
            "batch_date": batch_date.isoformat(),
        },
    )


def _line_value(line, key: str):
    """Linha de pedido (dict do snapshot) ou de sacola (dict ou objeto)."""
    if isinstance(line, dict):
        return line.get(key)
    return getattr(line, key, None)


def _component_skus(sku: str) -> set[str]:
    """Os SKUs que um combo reserva (o próprio SKU quando não é combo)."""
    try:
        return {comp["sku"] for comp in get_adapter("catalog").expand_bundle(sku, Decimal("1"))}
    except Exception as exc:
        if getattr(exc, "code", "") != "NOT_A_BUNDLE":
            logger.exception("order_date_before_batch: erro ao abrir o combo sku=%s", sku)
        return {sku}


def _product_name(sku: str) -> str:
    """Nome de catálogo do SKU, para a mensagem ao cliente (vazio se não houver)."""
    try:
        from shopman.offerman.models import Product

        return str(Product.objects.filter(sku=sku).values_list("name", flat=True).first() or "")
    except Exception:
        logger.debug("order_date_before_batch._product_name degraded sku=%s", sku, exc_info=True)
        return ""
