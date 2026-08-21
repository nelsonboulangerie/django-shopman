"""O livro-caixa (``cashman.Entry``/``Shift``) como evento e turno canônicos.

Ledger nativo: lido no lugar, nunca copiado. A diferença de um turno é
provada pelo livro (``Σ count + Σ count_correction``), em lote — a janela do
B.I. pode ter centenas de turnos, e é a mesma soma que o pacote define.
Turno sem contagem responde ``None``, não zero: ausência não é zero.
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone

from shopman.backstage.bi.canonical import CanonicalCashEvent, CanonicalShift, local_window


def read_events(window) -> list[CanonicalCashEvent]:
    """Todo lançamento com ``at`` na janela [início, fim), em ordem do livro."""
    from shopman.cashman.models import Entry

    rows = (
        Entry.objects.filter(at__range=window)
        .order_by("at", "id")
        .values_list(
            "id", "shift_id", "operator__username", "approved_by__username",
            "kind", "amount_q", "at", "order_ref", "parent_id",
        )
    )
    events: list[CanonicalCashEvent] = []
    for pk, shift_id, operator, approver, kind, amount_q, at, order_ref, parent_id in rows:
        local = timezone.localtime(at)
        events.append(
            CanonicalCashEvent(
                key=pk,
                shift_key=shift_id,
                operator_key=operator or "sistema",
                approved_by_key=approver or "",
                kind=kind,
                amount_q=int(amount_q),
                at=local,
                day=local.date(),
                order_ref=order_ref or "",
                parent_key=parent_id,
            )
        )
    return events


def read_closed_shifts(date_from: date, date_to: date) -> list[CanonicalShift]:
    """Turnos fechados no intervalo (data local do fechamento), com a diferença provada pelo livro."""
    from django.db.models import Sum
    from shopman.cashman.models import Entry, Shift

    window_from, window_to = local_window(date_from, date_to)
    shifts = list(
        Shift.objects.filter(status=Shift.Status.CLOSED, closed_at__gte=window_from, closed_at__lt=window_to)
        .values_list("id", "terminal__ref", "opened_by__username", "opened_at", "closed_at")
    )
    if not shifts:
        return []
    shift_ids = [pk for pk, *_ in shifts]
    difference = {
        int(row["shift_id"]): int(row["total"] or 0)
        for row in Entry.objects.filter(
            shift_id__in=shift_ids,
            kind__in=[Entry.Kind.COUNT, Entry.Kind.COUNT_CORRECTION],
        )
        .values("shift_id")
        .annotate(total=Sum("amount_q"))
    }
    # Quem AGIU em cada turno, do livro. Uma consulta para todos os turnos da
    # janela: é o que permite dizer "a quebra é da Joyce" só quando a Joyce foi a
    # única a lançar — e calar quando não foi.
    atuantes: dict[int, set[str]] = {}
    for shift_id, username in (
        Entry.objects.filter(shift_id__in=shift_ids)
        .values_list("shift_id", "operator__username")
        .distinct()
    ):
        atuantes.setdefault(int(shift_id), set()).add(username or "sistema")
    return [
        CanonicalShift(
            key=pk,
            terminal_key=terminal_ref or "",
            opened_by_key=opened_by or "sistema",
            operator_keys=tuple(sorted(atuantes.get(pk, set()))),
            opened_at=timezone.localtime(opened_at),
            closed_at=timezone.localtime(closed_at),
            difference_q=difference.get(pk),
        )
        for pk, terminal_ref, opened_by, opened_at, closed_at in shifts
    ]
