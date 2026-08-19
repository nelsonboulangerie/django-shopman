"""O livro: gravar lançamentos e ler o que eles provam.

``record`` é o ÚNICO escritor de ``Entry`` fora de ``shifts.open_shift`` e
``shifts.close_shift`` (que gravam ``float_in`` e ``count``, os dois tipos que
só existem como parte de abrir e fechar). Sinal, ``parent`` e segunda assinatura
são validados aqui, antes do banco, com mensagem em português; o CheckConstraint
do model é a rede de baixo.

O estado do turno é a exceção deliberada: ele NÃO é validado na instância
recebida, e sim relido sob ``select_for_update`` na mesma transação que grava
(ver ``record``). Custódia muda por outra conexão — a do gerente fechando — e
uma leitura velha aqui é dinheiro entrando depois da contagem.
"""

from __future__ import annotations

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from shopman.cashman.exceptions import CashError
from shopman.cashman.models import Entry, Shift
from shopman.cashman.signals import entry_recorded

Kind = Entry.Kind

#: Só abrir e fechar gravam estes. Aceitá-los em ``record`` daria dois jeitos de
#: pôr fundo de troco ou contagem no livro, e o segundo jeito escaparia do lock
#: e das regras do fechamento.
_RESERVED_KINDS = frozenset({Kind.FLOAT_IN, Kind.COUNT})

#: O que ainda faz sentido num turno FECHADO: a correção auditada da contagem,
#: a anotação do gerente, e o resultado de um comprovante cuja impressão o
#: navegador só confirmou depois. Todo o resto exige turno aberto.
_ALLOWED_ON_CLOSED = frozenset({Kind.COUNT_CORRECTION, Kind.NOTE, Kind.RECEIPT_RESULT})


def record(
    kind: str,
    *,
    shift: Shift,
    operator,
    amount_q: int = 0,
    approved_by=None,
    order_ref: str = "",
    payment_ref: str = "",
    parent: Entry | None = None,
    reason: str = "",
    payload: dict | None = None,
    at=None,
) -> Entry:
    """Grava um lançamento no livro do turno e anuncia ``entry_recorded``.

    Levanta ``CashError`` (código legível) antes de tocar no banco quando o
    tipo é desconhecido ou reservado, o sinal não bate, o ``parent`` falta ou
    é do tipo/turno errado, ou a segunda assinatura falta.

    **A custódia é relida do banco, sob lock, antes de gravar.** O ``shift`` que
    chega é a instância que quem chamou leu ANTES — numa venda, antes até do
    commit do pedido. Se o status viesse dela, uma venda em voo entraria depois
    da contagem, num turno já CLOSED: o ``count`` congela "contado − esperado no
    instante do fechamento", e uma linha posterior faria o livro provar um saldo
    que a gaveta nunca teve. ``close_shift`` já tranca o turno com
    ``select_for_update``; sem o mesmo lock aqui os dois caminhos não se
    serializam. O custo é um ``SELECT … FOR UPDATE`` por lançamento — irrelevante
    no volume de um balcão, e é ele que faz do fechamento cego uma garantia de
    construção em vez de disciplina. Provado em
    ``tests/test_concurrency.py``.

    ⚠️ O que isto NÃO desfaz: a venda recusada aqui já aconteceu no balcão, e o
    dinheiro está na gaveta depois da contagem. O lançamento tardio é impedido —
    o buraco vira uma sobra na conferência, que é o que o fechamento cego existe
    para revelar. Quem cruza os dois livros é o ``cash_ledger_mismatch``
    (``shopman/backstage/services/financial_reconciliation.py``).
    """
    kind = str(kind or "")
    if kind not in Kind.values:
        raise CashError("INVALID_KIND", f"Tipo de lançamento desconhecido: {kind!r}.")
    if kind in _RESERVED_KINDS:
        raise CashError(
            "INVALID_KIND",
            "Fundo de troco e contagem só nascem ao abrir e fechar o turno.",
            {"kind": kind},
        )

    amount_q = int(amount_q or 0)
    if not Entry.sign_allows(kind, amount_q):
        raise CashError(
            "INVALID_AMOUNT",
            f"Valor {amount_q} não é válido para {Kind(kind).label}: o sinal vive no tipo.",
            {"kind": kind, "amount_q": amount_q},
        )

    expected_parent_kinds = Entry.PARENT_KIND_BY_KIND.get(kind)
    if expected_parent_kinds:
        if parent is None:
            raise CashError("PARENT_REQUIRED", f"{Kind(kind).label} precisa do lançamento que responde.", {"kind": kind})
        if parent.kind not in expected_parent_kinds or parent.shift_id != shift.pk:
            raise CashError(
                "PARENT_MISMATCH",
                f"{Kind(kind).label} só responde a {', '.join(str(Kind(k).label) for k in expected_parent_kinds)} do mesmo turno.",
                {"kind": kind, "parent_kind": parent.kind},
            )
    elif parent is not None and parent.shift_id != shift.pk:
        raise CashError("PARENT_MISMATCH", "O lançamento respondido é de outro turno.", {"kind": kind})

    if kind in Entry.APPROVAL_REQUIRED and approved_by is None:
        raise CashError("APPROVAL_REQUIRED", f"{Kind(kind).label} exige a assinatura de quem autorizou.", {"kind": kind})

    payload = dict(payload or {})
    _validate_payload(kind, payload)

    with transaction.atomic():
        locked = _locked_shift(shift)
        if not locked.is_open and kind not in _ALLOWED_ON_CLOSED:
            raise CashError("SHIFT_NOT_OPEN", "O turno já está fechado.", {"shift_id": shift.pk})
        if kind == Kind.COUNT_CORRECTION and locked.is_open:
            raise CashError("SHIFT_NOT_CLOSED", "A correção da contagem é para turno fechado.", {"shift_id": shift.pk})

        try:
            with transaction.atomic():
                entry = Entry.objects.create(
                    shift=shift,
                    operator=operator,
                    approved_by=approved_by,
                    at=at or timezone.now(),
                    kind=kind,
                    amount_q=amount_q,
                    order_ref=str(order_ref or ""),
                    payment_ref=str(payment_ref or ""),
                    parent=parent,
                    reason=str(reason or "").strip()[:200],
                    payload=payload,
                )
        except IntegrityError as exc:
            # Um pedido entra uma vez por turno, por tipo (UniqueConstraint
            # parcial no model): dois submits do mesmo fechamento dobrariam o
            # esperado. Quem decide é o banco; a mensagem continua sendo da casa.
            raise CashError(
                "DUPLICATE_ENTRY",
                f"{Kind(kind).label} do pedido {order_ref} já está no livro deste turno.",
                {"kind": kind, "order_ref": str(order_ref or ""), "shift_id": shift.pk},
            ) from exc
        transaction.on_commit(lambda: entry_recorded.send(sender=Entry, entry=entry))
    return entry


def _validate_payload(kind: str, payload: dict) -> None:
    """O payload dos tipos que TÊM schema é conferido pelo único escritor.

    Contrato que só a superfície cobra não é contrato — é a mesma razão pela qual
    o motivo da sangria é exigido no servidor. Quem chama a API crua (ou um
    comando, ou o seed) não passa pelo ``backstage``, e um pedido de troco de
    ``-500`` viajaria calado até a tela de quem vai buscar o dinheiro.

    Só os dois tipos que carregam DECISÃO no payload entram aqui. Os demais
    guardam contexto livre (``note.text``, ``sale.intents``), e inventar schema
    para eles seria regra sem defeito para prevenir.

    ⚠️ O que este validador NÃO faz: dizer QUAIS cédulas o balcão pode pedir.
    Esse catálogo é política da superfície, tem fonte única em
    ``backstage/services/pos.py::CHANGE_DENOMINATIONS`` e viaja para a tela pela
    projection; copiá-lo para cá criaria a segunda lista que aquele comentário
    existe para evitar — e o pacote não pode importar o backstage (ADR-001).
    Aqui se confere a FORMA: lista de centavos positivos.
    """
    if kind == Kind.CHANGE_REQUESTED:
        amount_q = payload.get("amount_q")
        if not isinstance(amount_q, int) or isinstance(amount_q, bool) or amount_q <= 0:
            raise CashError(
                "INVALID_PAYLOAD",
                "O pedido de troco precisa do valor pedido, em centavos.",
                {"kind": kind, "amount_q": amount_q},
            )
        denominations = payload.get("denominations") or []
        if not isinstance(denominations, (list, tuple)) or any(
            not isinstance(v, int) or isinstance(v, bool) or v <= 0 for v in denominations
        ):
            raise CashError(
                "INVALID_PAYLOAD",
                "As cédulas e moedas pedidas são uma lista de valores em centavos.",
                {"kind": kind, "denominations": denominations},
            )
        return

    if kind == Kind.RECEIPT_RESULT:
        status = payload.get("status")
        if status not in Entry.RECEIPT_STATUSES:
            raise CashError(
                "INVALID_PAYLOAD",
                "O resultado do comprovante é impresso, falhou ou sem impressora.",
                {"kind": kind, "status": status},
            )


def _locked_shift(shift: Shift) -> Shift:
    """O turno relido sob ``select_for_update``: só o banco sabe se ele ainda está aberto."""
    try:
        return Shift.objects.select_for_update().only("id", "status").get(pk=shift.pk)
    except Shift.DoesNotExist as exc:
        raise CashError("SHIFT_NOT_OPEN", "Este turno não existe mais.", {"shift_id": shift.pk}) from exc


# ── Leituras: o que o livro prova ─────────────────────────────────────────


def timeline(shift: Shift):
    """A linha do tempo do turno, na ordem em que aconteceu."""
    return Entry.objects.filter(shift=shift).select_related("operator", "approved_by", "parent").order_by("at", "id")


def _sum(qs) -> int:
    return int(qs.aggregate(total=models.Sum("amount_q"))["total"] or 0)


def balance(shift: Shift, *, until: Entry | None = None) -> int:
    """Saldo do livro: ``Σ amount_q``. Com ``until``, só até aquele lançamento (inclusive)."""
    qs = Entry.objects.filter(shift=shift)
    if until is not None:
        qs = qs.filter(id__lte=until.pk)
    return _sum(qs)


def expected_before_count(shift: Shift) -> int:
    """Quanto era para ter na gaveta: tudo menos a contagem e suas correções."""
    return _sum(Entry.objects.filter(shift=shift).exclude(kind__in=[Kind.COUNT, Kind.COUNT_CORRECTION]))


def difference(shift: Shift) -> int | None:
    """Contado − esperado, já com correções. ``None`` enquanto não houve contagem."""
    if not Entry.objects.filter(shift=shift, kind=Kind.COUNT).exists():
        return None
    return _sum(Entry.objects.filter(shift=shift, kind__in=[Kind.COUNT, Kind.COUNT_CORRECTION]))


def counted(shift: Shift) -> int | None:
    """O que a gaveta tinha de fato no fechamento, já com correções. ``None`` sem contagem."""
    diff = difference(shift)
    if diff is None:
        return None
    return expected_before_count(shift) + diff


def change_requests(shift: Shift) -> list[dict]:
    """Os pedidos de troco do turno, com o estado dobrado do livro.

    O estado NÃO mora em coluna: é o pedido e, depois, o atendimento OU o
    cancelamento que aponta para ele por ``parent``. A primeira resolução vale;
    uma segunda fica no livro (é história) e a dobra ignora.
    """
    entries = Entry.objects.filter(
        shift=shift, kind__in=[Kind.CHANGE_REQUESTED, Kind.CHANGE_SERVED, Kind.CHANGE_CANCELLED]
    ).select_related("operator", "approved_by").order_by("at", "id")

    by_id: dict[int, dict] = {}
    for entry in entries:
        if entry.kind == Kind.CHANGE_REQUESTED:
            payload = entry.payload or {}
            by_id[entry.pk] = {
                "entry_id": entry.pk,
                "amount_q": int(payload.get("amount_q") or 0),
                # As cédulas/moedas pedidas, em centavos, do maior para o menor.
                # Vazio é pedido completo ("me traz R$ 100"); a lista só refina.
                "denominations": [int(v) for v in (payload.get("denominations") or [])],
                "note": str(payload.get("note") or ""),
                "status": "pending",
                "requested_by": entry.operator.get_username() if entry.operator_id else "",
                "requested_at": entry.at.isoformat(),
                "served_by": "",
                "served_at": "",
                "cancelled_at": "",
            }
            continue
        request = by_id.get(entry.parent_id)
        if request is None or request["status"] != "pending":
            continue
        if entry.kind == Kind.CHANGE_SERVED:
            request["status"] = "served"
            request["served_by"] = entry.approved_by.get_username() if entry.approved_by_id else ""
            request["served_at"] = entry.at.isoformat()
        else:
            request["status"] = "cancelled"
            request["cancelled_at"] = entry.at.isoformat()
    return list(by_id.values())
