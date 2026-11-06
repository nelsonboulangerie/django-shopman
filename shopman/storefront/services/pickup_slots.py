"""Horários de retirada da loja: a grade da casa, anotada para o carrinho.

A grade NÃO é desta superfície. Ela sai de ``shop/services/fulfillment_window``,
a mesma que a entrega da loja, a concierge e o PDV leem, e a DATA escolhe qual:

- **HOJE** → as meias horas do expediente que ainda dão: de agora mais a
  antecedência (``business_calendar.DELIVERY_SLOT_LEAD_MINUTES``) até o
  fechamento. O "mais cedo" de hoje é sempre um horário que ainda vem, e o
  pedido nunca grava um começo que já passou (o "A partir das 15h" escolhido às
  18:36 entrava na Cozinha atrasado e no PDV com hora vencida). Sem meia hora
  sobrando, hoje não tem horário: a lista vem vazia e a tela manda escolher
  outra data.
- **OUTRO DIA (encomenda)** → os turnos canônicos da casa
  (``Shop.defaults["pickup_slots"]``, editáveis no Admin) que cabem no
  expediente daquele dia. Encomenda é turno de fornada, não hora marcada.

A prontidão dos itens corta as duas grades do mesmo jeito (``fulfillment_window
.annotate``): a janela que começa antes de o item ficar pronto aparece riscada,
com o produto e a hora no motivo.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

logger = logging.getLogger(__name__)


PICKUP_SLOT_REQUIRED = "Selecione um horário de retirada."
PICKUP_SLOT_PASSED = "Este horário já passou. Selecione um horário futuro."
PICKUP_TODAY_OVER = "Não há mais horário de retirada hoje. Escolha outra data."
PICKUP_SLOT_UNKNOWN = "Esse horário não está na lista de retirada desse dia. Escolha um dos horários da lista."


def get_slots() -> list[dict]:
    """Os turnos de encomenda da casa: UMA fonte, lida do orquestrador.

    Delegado a ``shop/services/fulfillment_window.canonical_slots`` porque o PDV
    faz a MESMA pergunta e não pode importar o storefront.
    """
    from shopman.shop.services.fulfillment_window import canonical_slots

    return canonical_slots()


def _day_from(delivery_date: str, *, now: datetime | None = None) -> date | None:
    """A data pedida; em branco é hoje. ``None`` quando a data não se lê."""
    from shopman.shop.services.fulfillment_window import _local_today

    if not delivery_date:
        return _local_today(now=now)
    try:
        return date.fromisoformat(delivery_date)
    except ValueError:
        return None


def annotate_slots_for_checkout(
    cart_skus: list[str],
    *,
    delivery_date: str = "",
    now: datetime | None = None,
) -> dict:
    """Os horários de retirada da data pedida, anotados para este carrinho.

    Devolve::

        {
            "pickup_slots": [{"ref", "label", "starts_at", "enabled", "reason", "is_earliest"}, …],
            "earliest_slot_ref": "19:30-20:00",  # o primeiro oferecível, ou None
            "grid": "half_hour" | "canonical",
        }

    Lista vazia: não há retirada nesse dia (fechado, feriado, ou o expediente de
    hoje já não comporta a antecedência). Nada de horário morto oferecido.
    """
    from shopman.shop.services import fulfillment_window
    from shopman.shop.services.product_readiness import format_clock

    day = _day_from(delivery_date, now=now) or fulfillment_window._local_today(now=now)
    context = fulfillment_window.annotate(day, list(cart_skus or []), now=now)
    earliest = context.get("earliest_ref") or None
    slots = []
    for window in context.get("windows") or []:
        ref = str(window.get("ref") or "")
        start = fulfillment_window._window_start(window)
        slots.append(
            {
                "ref": ref,
                "label": str(window.get("label") or "").strip() or ref,
                "starts_at": format_clock(start) if start else "",
                "enabled": bool(window.get("enabled")),
                "reason": str(window.get("reason") or ""),
                "is_earliest": ref == earliest,
            }
        )
    return {
        "pickup_slots": slots,
        "earliest_slot_ref": earliest,
        "grid": context.get("grid") or "canonical",
    }


def validate_pickup_slot_selection(
    delivery_time_slot: str,
    *,
    delivery_date: str = "",
    cart_skus: list[str] | None = None,
    now: datetime | None = None,
) -> str | None:
    """Erro ao cliente quando o horário de retirada não pode ser aceito.

    O cliente escolhe sozinho, sem a dona do lado, e por isso o horário tem de
    estar na grade que a loja oferece para o dia (como na entrega). Depois, a
    prontidão dos itens (``fulfillment_window.validate``).
    """
    from shopman.shop.services import business_calendar, fulfillment_window

    ref = str(delivery_time_slot or "").strip()
    if not ref:
        return PICKUP_SLOT_REQUIRED
    day = _day_from(delivery_date, now=now)
    if day is None:
        return PICKUP_SLOT_UNKNOWN

    grid = fulfillment_window.delivery_windows_for(day, now=now)
    if ref not in {window["ref"] for window in grid}:
        if day != fulfillment_window._local_today(now=now):
            return PICKUP_SLOT_UNKNOWN
        if not grid:
            return PICKUP_TODAY_OVER
        # As meias horas do dia INTEIRO, lidas da véspera (o relógio não corta
        # nada): se o ref está nelas e não na grade de agora, foi o relógio que
        # o tirou.
        from django.utils import timezone

        eve = datetime.combine(day - timedelta(days=1), time(12, 0))
        if timezone.is_naive(eve):
            eve = timezone.make_aware(eve)
        whole_day = {w.get("ref") for w in business_calendar.delivery_slots_for(day, now=eve)}
        if ref in whole_day:
            return PICKUP_SLOT_PASSED
        return PICKUP_SLOT_UNKNOWN

    return fulfillment_window.validate(day, ref, list(cart_skus or []), now=now)


def annotate_delivery_windows_for_checkout(cart_skus: list[str], *, delivery_date: str = "") -> dict:
    """As janelas de ENTREGA da data pedida (hoje, sem data), anotadas para o carrinho.

    A grade é ``fulfillment_window.delivery_windows_for`` (meia hora hoje, turno
    na encomenda), a mesma da retirada, da concierge e a que o commit confere com
    ``delivery_window_error``. Devolve o contexto de ``fulfillment_window.annotate``.
    """
    from shopman.shop.services import fulfillment_window

    day = _day_from(delivery_date) or fulfillment_window._local_today()
    return fulfillment_window.annotate(day, list(cart_skus or []))
