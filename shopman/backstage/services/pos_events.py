"""Escrita e leitura do log de eventos do PDV (``POSEvent``).

Um só ponto de escrita para que todo evento nasça com o mesmo formato: quem,
quando, em qual turno, de que tipo. Os services de caixa chamam ``record`` no
mesmo ``transaction.atomic`` da mutação que registram — o evento e o fato são
uma coisa só, ou nenhum dos dois.
"""

from __future__ import annotations

from django.utils import timezone


def record(
    kind: str,
    *,
    shift=None,
    operator=None,
    payload: dict | None = None,
    movement=None,
    order_ref: str = "",
    at=None,
):
    """Grava um evento. Devolve a linha criada.

    ``operator`` vazio significa "o sistema" (reconciliação, varredura). O
    terminal sai do turno quando há turno; evento sem turno (dia fechado) fica
    sem terminal, porque não é de nenhum.
    """
    from shopman.backstage.models import POSEvent

    return POSEvent.objects.create(
        kind=kind,
        at=at or timezone.now(),
        shift=shift,
        operator=operator,
        payload=dict(payload or {}),
        movement=movement,
        order_ref=str(order_ref or ""),
    )


def for_shift(shift):
    """A linha do tempo de um turno, na ordem em que aconteceu."""
    from shopman.backstage.models import POSEvent

    return POSEvent.objects.filter(shift=shift).select_related("operator").order_by("at", "id")


def change_requests(shift) -> list[dict]:
    """Os pedidos de troco do turno, com o estado atual de cada um.

    O estado NÃO mora numa coluna: é dobrado a partir dos eventos, o pedido e
    depois o atendimento ou o cancelamento que apontam para o mesmo ``ref``.
    Assim o log continua append-only e a lista continua respondendo o que a tela
    precisa (o que ainda está pendente).
    """
    from shopman.backstage.models import POSEvent

    Kind = POSEvent.Kind
    events = POSEvent.objects.filter(
        shift=shift,
        kind__in=(Kind.CHANGE_REQUESTED, Kind.CHANGE_SERVED, Kind.CHANGE_CANCELLED),
    ).order_by("at", "id")

    by_ref: dict[str, dict] = {}
    for event in events:
        payload = event.payload or {}
        ref = str(payload.get("ref") or "")
        if not ref:
            continue
        if event.kind == Kind.CHANGE_REQUESTED:
            by_ref[ref] = {
                "ref": ref,
                "kind": payload.get("kind", ""),
                "amount_q": int(payload.get("amount_q") or 0),
                "note": payload.get("note", ""),
                "status": "pending",
                "requested_by": payload.get("requested_by", ""),
                "requested_at": event.at.isoformat(),
                "served_by": "",
                "served_at": "",
                "cancelled_at": "",
            }
            continue
        entry = by_ref.get(ref)
        if entry is None or entry["status"] != "pending":
            # Resolução sem pedido, ou segunda resolução do mesmo pedido: o log
            # guarda, a dobra ignora — o estado é o da PRIMEIRA resolução.
            continue
        if event.kind == Kind.CHANGE_SERVED:
            entry["status"] = "served"
            entry["served_by"] = payload.get("served_by", "")
            entry["served_at"] = event.at.isoformat()
        else:
            entry["status"] = "cancelled"
            entry["cancelled_at"] = event.at.isoformat()
    return list(by_ref.values())
