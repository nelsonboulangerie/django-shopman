"""Decide se a data de um pedido é anterior à fornada que a sacola espera.

"Um pedido, uma data": a sacola guarda o item numa fornada planejada, e o pedido
só pode ser para o dia dela ou depois. Pedido para antes seria uma promessa
impossível (retirar hoje o pão que sai na quarta; laudo de 09/11/2026). A recusa
nomeia o item e o dia da fornada, e aponta o campo da data.

Só contam reservas de itens DESTE pedido: reserva tardia de SKU que já saiu da
sacola é sobra não reconciliada, e não recusa nada.

A fornada da sacola não é piso absoluto (dono, 10/11/2026): se depois de o item
entrar na fila surgir saldo de verdade numa data anterior (fornada extra, pão
pronto), o pedido para essa data vale, e a reserva muda para lá no fechamento.
Saldo de verdade é quantidade reservável naquele dia; registro de demanda sem
lote não conta.
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


def order_date_before_batch_refusal(session_key: str, order_day, items, *, channel_ref: str | None = None):
    """A recusa para ``order_day``, ou ``None`` quando a data serve.

    A mesma pergunta do gate de commit, para quem valida a data ANTES de fechar
    (a concierge, ao gravar retirada ou entrega). Devolve o ``ValidationError``
    pronto (item, dia da fornada, campo da data). Com ``channel_ref``, a data
    anterior à fornada da sacola serve quando o dia tem saldo para os itens que
    esperavam (o fechamento move a reserva para lá).
    """
    if not session_key or order_day is None:
        return None
    too_late = late_holds_of_order(session_key, order_day, items)
    if not too_late:
        return None
    if channel_ref and day_has_room({sku for _hold, sku, _date in too_late}, order_day, items, channel_ref):
        return None
    return refusal_error(items, too_late, order_day)


def day_has_room(skus, day, items, channel_ref: str) -> bool:
    """``day`` tem saldo reservável para TODA a quantidade destes SKUs no pedido?

    Lê o estoque do dia no recorte do canal, a mesma leitura da fila de espera.
    A reserva que a sessão tem na fornada posterior não pesa nesse dia. Qualquer
    dúvida (leitura falhou, item pausado, sem saldo) é "não": a data segue fechada.
    """
    needed = _needed_by_sku(items, set(skus))
    if not needed:
        return False
    try:
        from shopman.shop.services import availability, waitlist

        readings = availability.stock_on_dates(
            list(needed), [day], **waitlist.scope_kwargs(channel_ref),
        ).get(day) or {}
    except Exception:
        logger.debug("order_date_before_batch.day_has_room degraded day=%s", day, exc_info=True)
        return False
    for sku, qty in needed.items():
        reading = readings.get(sku) or {}
        if reading.get("is_paused"):
            return False
        if Decimal(str(reading.get("total_promisable") or 0)) < qty:
            return False
    return True


def earliest_day_with_room(sku: str, qty, batch_day, *, channel_ref: str, first_day=None):
    """A data mais cedo, antes de ``batch_day``, em que a linha inteira tem saldo; ou ``None``.

    Candidatas: ``first_day`` (o primeiro dia em que a casa atende) e as fornadas
    planejadas do SKU antes da que a sacola espera.
    """
    try:
        from shopman.shop.services import waitlist

        first_day = first_day or timezone.localdate()
        candidates = sorted(
            {first_day, *waitlist.batch_dates_until([sku], batch_day)}
        )
    except Exception:
        logger.debug("order_date_before_batch.earliest_day_with_room degraded sku=%s", sku, exc_info=True)
        return None
    line = [{"sku": sku, "qty": qty}]
    for day in candidates:
        if first_day <= day < batch_day and day_has_room({sku}, day, line, channel_ref):
            return day
    return None


def _needed_by_sku(items, skus: set[str]) -> dict[str, Decimal]:
    """Quanto o pedido precisa de cada um destes SKUs, abrindo os combos."""
    needed: dict[str, Decimal] = {}
    for item in items or ():
        sku = _line_value(item, "sku")
        if not sku:
            continue
        qty = Decimal(str(_line_value(item, "qty") or 0))
        for comp_sku, comp_qty in _components(sku, qty):
            if comp_sku in skus:
                needed[comp_sku] = needed.get(comp_sku, Decimal("0")) + comp_qty
    return needed


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
    return {comp_sku for comp_sku, _qty in _components(sku, Decimal("1"))}


def _components(sku: str, qty: Decimal) -> list[tuple[str, Decimal]]:
    """``(SKU, quantidade)`` do que a linha reserva (a própria linha quando não é combo)."""
    try:
        return [
            (comp["sku"], Decimal(str(comp["qty"])))
            for comp in get_adapter("catalog").expand_bundle(sku, qty)
        ]
    except Exception as exc:
        if getattr(exc, "code", "") != "NOT_A_BUNDLE":
            logger.exception("order_date_before_batch: erro ao abrir o combo sku=%s", sku)
        return [(sku, qty)]


def _product_name(sku: str) -> str:
    """Nome de catálogo do SKU, para a mensagem ao cliente (vazio se não houver)."""
    try:
        from shopman.offerman.models import Product

        return str(Product.objects.filter(sku=sku).values_list("name", flat=True).first() or "")
    except Exception:
        logger.debug("order_date_before_batch._product_name degraded sku=%s", sku, exc_info=True)
        return ""
