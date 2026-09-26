"""A régua da DATA de uma encomenda — uma peça, várias portas.

Quem pergunta "esta data pode ser combinada?" é a loja (checkout), o reagendamento
do operador (``services.reschedule``) e, pela metade, o PDV (``pos._validate_schedule``,
que tem voz própria de balcão e não confere dia fechado). As três réguas moravam
na superfície da loja; o reagendamento vive no orquestrador e não pode importar a
superfície, então a parte comum desceu para cá.

Três recusas, na ordem em que o cliente as entende: data passada, além do máximo
da casa (``Shop.defaults["max_preorder_days"]``) e dia fechado
(``Shop.defaults["closed_dates"]``). A antecedência por produto (lead time) NÃO
mora aqui: ela depende do carrinho e do plano da data, e quem a aplica é o gate de
estoque (``stock.hold(require_all=True)`` → ``lead_time``) e o checkout da loja.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def preorder_config() -> tuple[int, list]:
    """``(max_preorder_days, closed_dates)`` da casa — leitura via checkout_context."""
    from shopman.shop.projections import checkout_context

    return checkout_context.preorder_config()


def max_preorder_days() -> int:
    """Até quantos dias à frente a casa aceita encomenda (Admin, default 30)."""
    try:
        return max(0, int(preorder_config()[0]))
    except Exception:
        logger.warning("preorder_dates: could not read max_preorder_days; using 30", exc_info=True)
        return 30


def closed_date(day: date, closed_dates: list) -> tuple[bool, str | None]:
    """O dia cai num fechamento da casa? ``(fechado, rótulo)``.

    Entradas aceitas: ``{"date": "YYYY-MM-DD", "label": ...}`` ou
    ``{"from": ..., "to": ..., "label": ...}`` (intervalo inclusivo). Entrada
    ilegível é ignorada — uma linha mal digitada no Admin não fecha a loja.
    """
    for entry in closed_dates or []:
        label = entry.get("label", "")
        if "date" in entry:
            try:
                if day == date.fromisoformat(entry["date"]):
                    return True, label
            except ValueError:
                pass
        elif "from" in entry and "to" in entry:
            try:
                if date.fromisoformat(entry["from"]) <= day <= date.fromisoformat(entry["to"]):
                    return True, label
            except ValueError:
                pass
    return False, None


def date_refusal(day: date, *, today: date | None = None) -> str | None:
    """Por que esta data não pode ser combinada, ou ``None`` quando pode."""
    today = today or timezone.localdate()
    if day < today:
        return "Não é possível encomendar para uma data passada."
    max_days, closed_dates = preorder_config()
    max_date = today + timedelta(days=max_days)
    if day > max_date:
        return f"Data máxima permitida: {max_date.strftime('%d/%m/%Y')}"
    is_closed, label = closed_date(day, closed_dates)
    if is_closed:
        suffix = f": {label}" if label else ""
        return f"Fechado{suffix} — escolha outra data."
    return None
