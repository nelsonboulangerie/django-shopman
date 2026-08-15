"""Projection da conferência de comprovante — o que a tela responde ao papel.

Alguém está com um papel na mão e uma pergunta só: **isto é verdadeiro?** A tela
existe para responder isso e nada mais. Não é lista, não é relatório, não edita.

⚠️ O que ela pode afirmar é estreito, e a honestidade importa aqui mais do que em
qualquer outra tela: o código prova que **o movimento existe** e mostra o que ele
diz. Não prova que este papel é o único — fotocópia de comprovante legítimo
confere igual. Confundir as duas coisas é o jeito de a conferência dar uma
segurança que ela não tem.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReceiptVerification:
    """A resposta à pergunta do papel."""

    #: O papel confere com um movimento registrado?
    valid: bool
    #: A frase que o conferente lê primeiro. Sempre preenchida.
    verdict: str
    #: O porquê, quando não confere. Vazio quando confere.
    problem: str = ""
    code: str = ""
    movement_type: str = ""
    amount: str = ""
    shift_label: str = ""
    created_by: str = ""
    approved_by: str = ""
    created_at: str = ""
    reason: str = ""
    #: O que o balcão registrou sobre a impressão. Um papel na mão de alguém e
    #: um registro dizendo "falhou" não é contradição boba: ou reimprimiram sem
    #: passar pelo sistema, ou o papel não é deste movimento.
    receipt_status: str = ""
    receipt_detail: str = ""


def build_receipt_verification(code: str) -> ReceiptVerification:
    """Resolve ``code`` para o movimento, ou explica por que não resolve."""
    from shopman.backstage.models import CashMovement
    from shopman.backstage.services.receipt_verify import (
        InvalidReceiptCode,
        movement_id_from,
    )

    limpo = str(code or "").strip().upper()
    try:
        movement_id = movement_id_from(limpo)
    except InvalidReceiptCode as exc:
        return ReceiptVerification(
            valid=False,
            verdict="Este comprovante não confere.",
            problem=(
                f"{exc} Ou o código foi digitado errado, ou este papel não saiu deste sistema."
            ),
            code=limpo,
        )

    movement = (
        CashMovement.objects.select_related("shift", "shift__terminal")
        .filter(pk=movement_id)
        .first()
    )
    if movement is None:
        # Assinatura válida e movimento ausente só acontece se alguém apagou o
        # registro. Dizer "não confere" esconderia justamente isso.
        return ReceiptVerification(
            valid=False,
            verdict="O código é legítimo, mas o movimento não está mais no sistema.",
            problem="O registro foi apagado depois de impresso. Procure quem tem acesso ao banco.",
            code=limpo,
        )

    return ReceiptVerification(
        valid=True,
        verdict="Confere. Este comprovante corresponde a um movimento registrado.",
        code=limpo,
        movement_type=movement.get_movement_type_display(),
        amount=_money(movement.amount_q),
        shift_label=_shift_label(movement.shift),
        created_by=movement.created_by or "—",
        approved_by=movement.approved_by,
        created_at=_local(movement.created_at),
        reason=movement.reason or "—",
        receipt_status=movement.get_receipt_status_display(),
        receipt_detail=movement.receipt_detail,
    )


def _money(amount_q: int) -> str:
    from shopman.utils.monetary import format_money

    return f"R$ {format_money(amount_q)}"


def _shift_label(shift) -> str:
    terminal = getattr(shift, "terminal", None)
    nome = getattr(terminal, "label", "") or getattr(terminal, "ref", "")
    return f"#{shift.pk} — {nome}" if nome else f"#{shift.pk}"


def _local(quando) -> str:
    from django.utils import timezone

    return timezone.localtime(quando).strftime("%d/%m/%Y às %H:%M")
