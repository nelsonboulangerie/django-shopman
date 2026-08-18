"""Projection da conferência de comprovante — o que a tela responde ao papel.

Alguém está com um papel na mão e uma pergunta só: **isto é verdadeiro?** A tela
existe para responder isso e nada mais. Não é lista, não é relatório, não edita.

⚠️ O que ela pode afirmar é estreito, e a honestidade importa aqui mais do que em
qualquer outra tela: o código prova que **o lançamento existe** no livro
(``cashman.Entry`` de sangria/suprimento) e mostra o que ele diz. Não prova que
este papel é o único — fotocópia de comprovante legítimo confere igual.
Confundir as duas coisas é o jeito de a conferência dar uma segurança que ela
não tem.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReceiptVerification:
    """A resposta à pergunta do papel."""

    #: O papel confere com um lançamento registrado?
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
    #: O que o balcão registrou sobre a impressão (o último ``receipt_result``
    #: que responde à linha). Um papel na mão de alguém e um registro dizendo
    #: "falhou" não é contradição boba: ou reimprimiram sem passar pelo sistema,
    #: ou o papel não é deste lançamento.
    receipt_status: str = ""
    receipt_detail: str = ""


#: Rótulo do resultado da impressão. ``pending`` é a ausência de resultado: o
#: navegador do balcão nunca confirmou nada, e assumir "impresso" transformaria
#: papel que faltou em papel que alguém escondeu.
RECEIPT_STATUS_LABELS = {
    "pending": "Sem confirmação",
    "printed": "Impresso",
    "failed": "Falhou",
    "skipped": "Sem impressora",
}


def build_receipt_verification(code: str) -> ReceiptVerification:
    """Resolve ``code`` para o lançamento, ou explica por que não resolve."""
    from shopman.cashman.models import Entry

    from shopman.backstage.services.pos import receipt_result_for
    from shopman.backstage.services.receipt_verify import InvalidReceiptCode, entry_id_from

    limpo = str(code or "").strip().upper()
    try:
        entry_id = entry_id_from(limpo)
    except InvalidReceiptCode as exc:
        return ReceiptVerification(
            valid=False,
            verdict="Este comprovante não confere.",
            problem=(f"{exc} Ou o código foi digitado errado, ou este papel não saiu deste sistema."),
            code=limpo,
        )

    entry = (
        Entry.objects.select_related("shift", "shift__terminal", "operator", "approved_by")
        .filter(pk=entry_id, kind__in=[Entry.Kind.CASH_OUT, Entry.Kind.CASH_IN])
        .first()
    )
    if entry is None:
        # Assinatura válida e lançamento ausente só acontece se alguém apagou o
        # registro por fora (o livro não apaga pelo app). Dizer "não confere"
        # esconderia justamente isso.
        return ReceiptVerification(
            valid=False,
            verdict="O código é legítimo, mas o lançamento não está mais no sistema.",
            problem="O registro foi apagado depois de impresso. Procure quem tem acesso ao banco.",
            code=limpo,
        )

    result = receipt_result_for(entry)
    result_payload = (result.payload or {}) if result is not None else {}
    status = str(result_payload.get("status") or "pending")

    return ReceiptVerification(
        valid=True,
        verdict="Confere. Este comprovante corresponde a um lançamento registrado.",
        code=limpo,
        movement_type=str(entry.get_kind_display()),
        amount=_money(abs(int(entry.amount_q))),
        shift_label=_shift_label(entry.shift),
        created_by=entry.operator.get_username() if entry.operator_id else "—",
        approved_by=entry.approved_by.get_username() if entry.approved_by_id else "",
        created_at=_local(entry.at),
        reason=entry.reason or "—",
        receipt_status=RECEIPT_STATUS_LABELS.get(status, status),
        receipt_detail=str(result_payload.get("detail") or ""),
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
