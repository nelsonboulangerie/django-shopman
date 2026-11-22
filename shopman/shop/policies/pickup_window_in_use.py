"""Janela da grade que pedido aberto ainda usa não sai da grade (#2644).

A grade de janelas da casa mora em ``Shop.defaults["pickup_slots"]``, e o pedido
guarda o ref da janela combinada em ``Order.data["delivery_time_slot"]``. Janela
que sai da grade (ou troca de ref) com pedido aberto nela faz o pedido perder o
rótulo: a equipe lê "horário não reconhecido" e o cliente "horário a confirmar"
(``fulfillment_window.window_label``, #2555). Aquela frase é o último recurso;
falhar fechado é não deixar o dado chegar a esse estado.

A casa reagenda os pedidos antes, e a recusa diz quais. Pedido terminado
(concluído, cancelado, devolvido) não segura janela nenhuma.
"""

from __future__ import annotations

from datetime import date

#: Quantos pedidos a recusa lista antes de resumir o resto.
LISTED_ORDERS = 10


def removal_refusal(*, previous, kept: set[str]) -> str:
    """A frase que recusa tirar da grade as janelas em uso, ou ``""`` quando nada impede.

    ``previous`` é a grade gravada (a lista de ``pickup_slots``); ``kept``, os refs
    que continuam nela depois de salvar.
    """
    from shopman.orderman.models import Order

    slots = [slot for slot in (previous if isinstance(previous, list) else []) if isinstance(slot, dict)]
    labels = {str(slot.get("ref") or ""): str(slot.get("label") or "").strip() for slot in slots}
    removed = sorted(ref for ref in labels if ref and ref not in kept)
    if not removed:
        return ""
    rows = list(
        Order.objects.exclude(status__in=Order.TERMINAL_STATUSES)
        .filter(data__delivery_time_slot__in=removed)
        .order_by("created_at", "pk")
        .values_list("ref", "data")
    )
    if not rows:
        return ""
    windows = sorted({str((data or {}).get("delivery_time_slot") or "") for _ref, data in rows})
    names = ", ".join(f"“{labels.get(ref) or ref}”" for ref in windows)
    listed = [_order_line(ref, data) for ref, data in rows[:LISTED_ORDERS]]
    rest = len(rows) - len(listed)
    orders = ", ".join(listed) + (f" e mais {rest}" if rest else "")
    noun, pronoun = ("a janela", "nela") if len(windows) == 1 else ("as janelas", "nelas")
    return (
        f"Não dá para tirar da grade {noun} {names}: ainda há pedido aberto {pronoun}. "
        f"Reagende antes estes pedidos: {orders}."
    )


def _order_line(ref: str, data) -> str:
    """``WEB-261121-K3P (25/11)``: o pedido e o dia combinado, quando há."""
    raw = str((data or {}).get("delivery_date") or "").strip()[:10]
    try:
        day = date.fromisoformat(raw).strftime("%d/%m")
    except ValueError:
        return ref
    return f"{ref} ({day})"
