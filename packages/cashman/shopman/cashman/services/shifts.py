"""A custódia: abrir, fechar e corrigir turnos.

Abrir grava o turno E o fundo de troco (``float_in``) na mesma transação; fechar
grava a contagem (``count``) E fecha o turno na mesma transação. Nenhum dos
dois existe sem o outro: turno sem fundo de troco é um saldo mentiroso, e
contagem sem fechar é um turno que continua recebendo dinheiro depois de
contado.
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone
from shopman.cashman.exceptions import CashError
from shopman.cashman.models import Entry, Shift, Terminal
from shopman.cashman.services import ledger
from shopman.cashman.signals import entry_recorded, shift_closed, shift_opened

Kind = Entry.Kind


def open_shift_for(operator) -> Shift | None:
    return Shift.objects.filter(operator=operator, status=Shift.Status.OPEN).select_related("terminal").first()


def open_shift_for_terminal(terminal: Terminal) -> Shift | None:
    return Shift.objects.filter(terminal=terminal, status=Shift.Status.OPEN).select_related("terminal", "operator").first()


def is_closed(shift_id) -> bool:
    """O turno referido já fechou (ou não existe mais)?"""
    try:
        shift = Shift.objects.filter(pk=int(shift_id)).only("status").first()
    except (TypeError, ValueError):
        return False
    return bool(shift and shift.status == Shift.Status.CLOSED)


def open_shift(*, operator, terminal: Terminal | None = None, float_q: int = 0, at=None) -> Shift:
    """Abre a custódia e lança o fundo de troco.

    Recusa se o operador ou o terminal já têm turno aberto: a unicidade é
    constraint do banco, mas a mensagem tem de ser da casa, não um
    ``IntegrityError`` na tela do balcão.
    """
    terminal = terminal or Terminal.default()
    float_q = int(float_q or 0)
    if float_q < 0:
        raise CashError("INVALID_AMOUNT", "O fundo de troco não pode ser negativo.", {"float_q": float_q})

    with transaction.atomic():
        existing = open_shift_for(operator)
        if existing:
            raise CashError("SHIFT_ALREADY_OPEN", "Este operador já tem um turno aberto.", {"shift_id": existing.pk})
        blocking = open_shift_for_terminal(terminal)
        if blocking:
            raise CashError(
                "SHIFT_ALREADY_OPEN",
                "Este terminal já tem um turno aberto.",
                {"shift_id": blocking.pk, "operator": blocking.operator.get_username()},
            )
        try:
            shift = Shift.objects.create(terminal=terminal, operator=operator, opened_at=at or timezone.now())
        except IntegrityError as exc:
            # Duas aberturas no mesmo instante: a constraint decide, e a
            # mensagem continua sendo a nossa.
            raise CashError("SHIFT_ALREADY_OPEN", "Já existe um turno aberto para este operador ou terminal.") from exc
        transaction.on_commit(lambda: shift_opened.send(sender=Shift, shift=shift))
        # float_q == 0: nada a lançar; o livro começa vazio e o saldo é zero.
        if float_q > 0:
            float_entry = Entry.objects.create(
                shift=shift, operator=operator, at=shift.opened_at, kind=Kind.FLOAT_IN, amount_q=float_q
            )
            transaction.on_commit(lambda: entry_recorded.send(sender=Entry, entry=float_entry))
    return shift


def close_shift(shift: Shift, *, counted_q: int, actor, notes: str = "", at=None) -> Entry:
    """Fechamento cego: grava a contagem como ajuste e fecha a custódia.

    ``count.amount_q = contado − saldo``. Depois disto ``Σ`` do livro é o que a
    gaveta tinha de fato; a diferença é o próprio lançamento. O operador nunca
    viu o saldo (é o ponto do fechamento cego); quem vê é a retaguarda, no livro.
    ``actor`` pode não ser o dono do turno (fechamento supervisório): fica no
    lançamento como quem agiu, e o payload diz que foi supervisório.
    """
    counted_q = int(counted_q or 0)
    if counted_q < 0:
        raise CashError("INVALID_AMOUNT", "A contagem não pode ser negativa.", {"counted_q": counted_q})

    with transaction.atomic():
        locked = Shift.objects.select_for_update().get(pk=shift.pk)
        if not locked.is_open:
            raise CashError("SHIFT_NOT_OPEN", "O turno já está fechado.", {"shift_id": locked.pk})
        now = at or timezone.now()
        expected_q = ledger.expected_before_count(locked)
        count = Entry.objects.create(
            shift=locked,
            operator=actor,
            at=now,
            kind=Kind.COUNT,
            amount_q=counted_q - expected_q,
            payload={
                "counted_q": counted_q,
                "notes": str(notes or "").strip(),
                "supervisory": bool(actor is not None and locked.operator_id != getattr(actor, "pk", None)),
            },
        )
        locked.status = Shift.Status.CLOSED
        locked.closed_at = now
        locked.save(update_fields=["status", "closed_at"])
        transaction.on_commit(lambda: entry_recorded.send(sender=Entry, entry=count))
        transaction.on_commit(lambda: shift_closed.send(sender=Shift, shift=locked, count=count))
    shift.status = locked.status
    shift.closed_at = locked.closed_at
    return count


def correct_count(shift: Shift, *, delta_q: int, actor, approved_by, reason: str) -> Entry:
    """Ajuste gerencial auditado da contagem, depois do fechamento (ADR-011).

    Não edita a contagem: lança a correção apontando para ela. ``delta_q`` é
    quanto a contagem real difere da informada (contou R$ 100, era R$ 105 →
    +500). A diferença vigente passa a ser ``Σ count + Σ count_correction``.
    """
    delta_q = int(delta_q or 0)
    if delta_q == 0:
        raise CashError("INVALID_AMOUNT", "Correção de zero não corrige nada.")
    if not str(reason or "").strip():
        raise CashError("INVALID_AMOUNT", "Informe o motivo da correção.")
    count = Entry.objects.filter(shift=shift, kind=Kind.COUNT).order_by("id").first()
    if count is None:
        raise CashError("SHIFT_NOT_CLOSED", "O turno ainda não foi contado.", {"shift_id": shift.pk})
    return ledger.record(
        Kind.COUNT_CORRECTION,
        shift=shift,
        operator=actor,
        approved_by=approved_by,
        amount_q=delta_q,
        parent=count,
        reason=reason,
    )
