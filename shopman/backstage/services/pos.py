"""POS mutation service for backstage cash-shift mutations."""

from __future__ import annotations

from shopman.backstage.services.exceptions import POSError, POSPermissionError


def parse_money_to_q(raw) -> int:
    """Converte entrada do operador ("120", "120,50", "-10") em centavos.

    Entrada ilegível levanta POSError — devolver 0 silencioso num fechamento
    CEGO transformaria um typo ("12,,30") numa diferença gigante sem aviso.
    """
    from decimal import InvalidOperation

    from shopman.utils.monetary import brl_to_q

    text = str(raw or "").strip().replace("R$", "").replace(" ", "").replace(",", ".")
    if not text:
        return 0
    try:
        # brl_to_q usa ROUND_HALF_UP (não banker's rounding), consistente com
        # o resto do sistema.
        return brl_to_q(text)
    except InvalidOperation as exc:
        raise POSError("Valor inválido.") from exc


def open_cash_shift(*, operator, opening_amount_raw="0", terminal_ref: str = ""):
    from shopman.backstage.models import CashShift

    existing = CashShift.get_open_for_operator(operator)
    if existing:
        return existing

    terminal = _terminal(terminal_ref)
    terminal_open = CashShift.get_open_for_terminal(terminal)
    if terminal_open:
        raise POSError("Terminal POS já possui turno aberto.")

    opening_amount_q = max(0, parse_money_to_q(opening_amount_raw))
    return CashShift.objects.create(
        terminal=terminal,
        operator=operator,
        opening_amount_q=opening_amount_q,
    )


def movement_removes_cash(movement_type: str, amount_q: int) -> bool:
    """O movimento TIRA dinheiro da gaveta?

    Sangria (qualquer valor) e ajuste negativo reduzem o esperado do fechamento.
    São os dois caminhos pelos quais dinheiro sai e a contagem cega ainda bate:
    o próprio lançamento justifica a falta. Suprimento e ajuste positivo só criam
    sobra, que aparece na conferência — esses seguem sem gerente.
    """
    return movement_type == "sangria" or (movement_type == "ajuste" and amount_q < 0)


def register_cash_movement(
    *,
    operator,
    movement_type: str = "sangria",
    amount_raw="0",
    reason: str = "",
    manager_approval: dict | None = None,
):
    """Registra um movimento de gaveta.

    Retirada exige PIN de gerente — SEM limiar, em qualquer valor. Antes um
    operador sozinho lançava sangria à vontade: como o fechamento calcula
    ``esperado = abertura + vendas + suprimentos + ajustes − sangrias``, uma
    sangria inventada abaixava o esperado e a contagem cega fechava redonda.
    O dinheiro saía e o caixa batia. Agora a retirada tem duas assinaturas: quem
    lança e quem autoriza, ambas gravadas.
    """
    from shopman.backstage.models import CashMovement, CashShift
    from shopman.shop.services.pos import validate_manager_override

    shift = CashShift.get_open_for_operator(operator)
    if not shift:
        raise POSError("Caixa não aberto.")
    if shift.status != CashShift.Status.OPEN:
        raise POSError("Turno de caixa já fechado.")

    normalized_type = movement_type if movement_type in {"sangria", "suprimento", "ajuste"} else "sangria"
    amount_q = parse_money_to_q(amount_raw)
    # Ajuste aceita valor negativo (falta/quebra na conferência); sangria e
    # suprimento continuam estritamente positivos.
    if normalized_type == "ajuste":
        if amount_q == 0:
            raise POSError("Valor inválido.")
    elif amount_q <= 0:
        raise POSError("Valor inválido.")

    approved_by = ""
    if movement_removes_cash(normalized_type, amount_q):
        approval = manager_approval or {}
        validate_manager_override(
            approval,
            operator_username=operator.username,
            action=f"cash_{normalized_type}",
        )
        approved_by = str(approval.get("username") or "").strip()

    return CashMovement.objects.create(
        shift=shift,
        movement_type=normalized_type,
        amount_q=amount_q,
        reason=reason.strip(),
        created_by=operator.username,
        approved_by=approved_by,
    )


#: Teto da trilha de aberturas guardada no turno. Um turno normal abre a gaveta
#: dezenas de vezes; 500 cobre o pior sábado com folga e impede que um clique
#: preso engorde o JSONField sem limite.
_DRAWER_OPENING_LOG_CAP = 500


def register_drawer_opening(*, operator, reason: str = ""):
    """Registra uma abertura de gaveta SEM venda e sem movimento.

    Os outros três momentos que abrem a gaveta já deixam rastro sozinhos: a
    venda em dinheiro tem o pedido, a sangria e o suprimento têm o
    ``CashMovement``. Este não tem nada — é o operador abrindo para conferir,
    trocar nota, ou por qualquer motivo que só ele sabe. Sem registro, é
    exatamente o buraco que a chave física deixava.

    ⚠️ Isto NÃO decide quem pode abrir. A política de autorização de gaveta é da
    frente de estresse do PDV (retirada exige PIN em qualquer valor); aqui é o
    caminho físico. O motivo é substância da auditoria, não portaria.

    Mora em ``CashShift.metadata`` porque é dado contextual de um turno — o
    idioma do projeto para isso é JSONField, não migração.
    """
    from django.db import transaction
    from django.utils import timezone

    from shopman.backstage.models import CashShift

    reason = str(reason or "").strip()[:120]
    if not reason:
        raise POSError("Informe o motivo da abertura.")

    with transaction.atomic():
        # Sem o lock, duas aberturas quase simultâneas leem a mesma lista e a
        # segunda sobrescreve a primeira — uma abertura sumiria da trilha.
        shift = (
            CashShift.objects.select_for_update()
            .filter(operator=operator, status=CashShift.Status.OPEN)
            .first()
        )
        if not shift:
            raise POSError("Caixa não aberto.")
        metadata = dict(shift.metadata or {})
        openings = list(metadata.get("drawer_openings") or [])
        openings.append(
            {
                "at": timezone.now().isoformat(),
                "by": operator.username,
                "reason": reason,
            }
        )
        metadata["drawer_openings"] = openings[-_DRAWER_OPENING_LOG_CAP:]
        shift.metadata = metadata
        shift.save(update_fields=["metadata"])
    return shift


#: O que o balcão pode pedir. Refs em inglês (contrato), rótulo em pt-BR na tela.
#: `amount` é o pedido que só fala de valor ("me traz uns R$ 50 em troco").
CHANGE_REQUEST_KINDS = ("coins", "small_bills", "amount")

#: Teto da lista de pedidos guardada no turno. Um turno pede troco meia dúzia de
#: vezes no pior sábado; 50 cobre isso com folga e impede que um botão repetido
#: engorde o JSONField sem limite.
_CHANGE_REQUEST_LOG_CAP = 50


def _change_request_ref() -> str:
    """Identificador curto do pedido — é por ele que a tela atende e cancela.

    Aleatório, não sequencial: o índice na lista mudaria quando o teto apara as
    entradas antigas, e aí "atender o pedido 3" atenderia outro pedido.
    """
    import secrets

    return secrets.token_hex(4)


def request_change(*, operator, kind: str = "coins", amount_raw="0", note: str = ""):
    """O operador PEDE troco. Ninguém sai do balcão.

    Este é o ponto todo da feature: quando falta troco, o operador atravessava a
    loja com dinheiro até o cofre, por um trajeto que a câmera só cobre em parte.
    Se sumisse dinheiro ali, ninguém provava nem desprovava, e a falta só
    aparecia no fechamento, horas depois, misturada com o turno inteiro. Aqui o
    dinheiro fica onde está: o operador pede, alguém traz, e a troca acontece no
    balcão, à vista, entre duas pessoas.

    ⚠️ Um pedido NÃO é movimento de caixa e nunca vai virar um. Trocar uma nota
    de R$ 50 por cinco de R$ 10 é NET ZERO: o total da gaveta não muda. Se isto
    criasse ``CashMovement``, o ``expected_amount_q`` cairia por um dinheiro que
    nunca saiu e o turno fecharia com falta fantasma — foi exatamente o defeito
    que o PR #178 teve de desfazer.

    Mora em ``CashShift.metadata`` porque é dado contextual de um turno — o
    idioma do projeto para isso é JSONField, não migração.
    """
    from django.db import transaction
    from django.utils import timezone

    from shopman.backstage.models import CashShift

    kind = str(kind or "").strip()
    if kind not in CHANGE_REQUEST_KINDS:
        raise POSError("Tipo de pedido inválido.")
    amount_q = max(0, parse_money_to_q(amount_raw))
    # O pedido "amount" É o valor: sem número ele não diz nada a quem vai trazer.
    # Nos outros o valor é opcional, porque "faltou moeda" já é um pedido inteiro.
    if kind == "amount" and amount_q <= 0:
        raise POSError("Informe o valor aproximado.")
    note = str(note or "").strip()[:120]

    with transaction.atomic():
        # Sem o lock, dois pedidos quase simultâneos leem a mesma lista e o
        # segundo sobrescreve o primeiro — um pedido sumiria antes de ser visto.
        shift = (
            CashShift.objects.select_for_update()
            .filter(operator=operator, status=CashShift.Status.OPEN)
            .first()
        )
        if not shift:
            raise POSError("Caixa não aberto.")
        entry = {
            "ref": _change_request_ref(),
            "kind": kind,
            "amount_q": amount_q,
            "note": note,
            "status": "pending",
            "requested_by": operator.username,
            "requested_at": timezone.now().isoformat(),
            "served_by": "",
            "served_at": "",
            "cancelled_at": "",
        }
        _save_change_requests(shift, [*_change_requests(shift), entry])

    _announce_change_request(shift, entry)
    return entry


def serve_change_request(*, operator, request_ref: str, manager_approval: dict | None = None):
    """O gerente traz o troco e assina no balcão. A gaveta abre; o esperado, não.

    Mesma permissão de quem autoriza uma sangria (``backstage.adjust_cashshift``)
    porque a gaveta abre com dinheiro dentro e alguém de fora do turno mexe nela:
    sem a segunda assinatura, "atender um pedido" viraria um jeito de abrir a
    gaveta sem ninguém olhando — o buraco que este fluxo existe para fechar.

    ⚠️ NÃO cria ``CashMovement`` e NÃO toca em ``expected_amount_q``. A troca é
    net zero (saem R$ 50, entram 5×R$ 10); qualquer lançamento aqui inventaria
    uma diferença no fechamento cego.
    """
    from django.db import transaction
    from django.utils import timezone

    from shopman.backstage.models import CashShift
    from shopman.shop.services.pos import validate_manager_override

    validate_manager_override(
        manager_approval or {},
        operator_username=operator.username,
        action="cash_change_request_serve",
    )
    approved_by = str((manager_approval or {}).get("username") or "").strip()

    with transaction.atomic():
        shift = (
            CashShift.objects.select_for_update()
            .filter(operator=operator, status=CashShift.Status.OPEN)
            .first()
        )
        if not shift:
            raise POSError("Caixa não aberto.")
        requests = _change_requests(shift)
        entry = _find_pending(requests, request_ref)
        entry["status"] = "served"
        entry["served_by"] = approved_by
        entry["served_at"] = timezone.now().isoformat()
        _save_change_requests(shift, requests)

    _announce_change_request(shift, entry)
    return entry


def cancel_change_request(*, operator, request_ref: str):
    """O operador achou troco na gaveta e o pedido não vale mais.

    Sem esta saída o pendente fica pendurado para sempre, e uma lista com
    pedidos mortos é uma lista em que ninguém acredita — daí a próxima falta de
    troco volta a ser resolvida na caminhada até o cofre.
    """
    from django.db import transaction
    from django.utils import timezone

    from shopman.backstage.models import CashShift

    with transaction.atomic():
        shift = (
            CashShift.objects.select_for_update()
            .filter(operator=operator, status=CashShift.Status.OPEN)
            .first()
        )
        if not shift:
            raise POSError("Caixa não aberto.")
        requests = _change_requests(shift)
        entry = _find_pending(requests, request_ref)
        entry["status"] = "cancelled"
        entry["cancelled_at"] = timezone.now().isoformat()
        _save_change_requests(shift, requests)

    _announce_change_request(shift, entry)
    return entry


def pending_change_requests(shift) -> list[dict]:
    """Os pedidos que ainda esperam alguém trazer o troco."""
    if shift is None:
        return []
    return [r for r in _change_requests(shift) if r.get("status") == "pending"]


def _change_requests(shift) -> list[dict]:
    return [dict(r) for r in (dict(shift.metadata or {}).get("change_requests") or [])]


def _save_change_requests(shift, requests: list[dict]) -> None:
    metadata = dict(shift.metadata or {})
    metadata["change_requests"] = requests[-_CHANGE_REQUEST_LOG_CAP:]
    shift.metadata = metadata
    shift.save(update_fields=["metadata"])


def _find_pending(requests: list[dict], request_ref: str) -> dict:
    """Acha o pedido pendente, ou explica qual dos dois erros aconteceu.

    Atendido/cancelado tem mensagem própria porque o caso real é duas pessoas na
    mesma tela: se o segundo toque dissesse "não encontrado", o gerente
    procuraria defeito no sistema em vez de ver que o pedido já foi resolvido.
    """
    ref = str(request_ref or "").strip()
    for entry in requests:
        if entry.get("ref") == ref:
            if entry.get("status") != "pending":
                raise POSError("Este pedido de troco já foi resolvido.")
            return entry
    raise POSError("Pedido de troco não encontrado.")


def _announce_change_request(shift, entry: dict) -> None:
    """Anuncia o pedido no canal `alerts` do SSE.

    ⚠️ Isto NÃO substitui o operador chamar em voz alta. Numa padaria pequena
    ninguém está com a tela de alertas aberta esperando — e hoje as superfícies
    de operador leem alertas por POLL, não por este canal. O que o registro
    entrega de verdade é a trilha (quem pediu, o quê, quando) e o dado para o
    B.I. depois: quantas vezes por dia falta troco, e em qual horário. Prometer
    recado entregue seria mentira, e mentira de tela vira dinheiro no chão.
    """
    from shopman.shop.handlers._sse_emitters import emit_change_request

    emit_change_request(
        {
            "ref": entry.get("ref", ""),
            "status": entry.get("status", ""),
            "kind": entry.get("kind", ""),
            "amount_q": entry.get("amount_q", 0),
            "shift_id": shift.pk,
            "terminal_ref": shift.terminal.ref if shift.terminal_id else "",
            "requested_by": entry.get("requested_by", ""),
        }
    )


def close_cash_shift(*, operator, closing_amount_raw="0", notes: str = ""):
    from shopman.backstage.models import CashShift

    shift = CashShift.get_open_for_operator(operator)
    if not shift:
        raise POSError("Caixa não aberto.")

    shift.close(
        blind_closing_amount_q=parse_money_to_q(closing_amount_raw),
        notes=notes.strip(),
    )
    return shift


def close_blocking_shift(*, actor_user, shift_id, closing_amount_raw="0", notes: str = ""):
    """Fechamento cego SUPERVISÓRIO do turno que bloqueia o terminal.

    Destrava o beco de UX: quando o terminal tem um turno aberto que não é do
    operador atual, ele fica preso sem poder vender. Aqui o GERENTE
    (``perform_closing``) ou o DONO do turno conta a gaveta e fecha o turno
    bloqueante — liberando o terminal. Operador comum não fecha o caixa de
    outro (anti-fraude) → POSPermissionError.
    """
    from shopman.backstage.models import CashShift
    from shopman.backstage.permissions import can_close_day

    shift = CashShift.objects.filter(pk=shift_id, status=CashShift.Status.OPEN).first()
    if not shift:
        raise POSError("Turno não encontrado ou já fechado.")

    is_owner = shift.operator_id == getattr(actor_user, "pk", None)
    if not (can_close_day(actor_user) or is_owner):
        raise POSPermissionError("Sem permissão para fechar o turno de outro operador.")

    shift.close(
        blind_closing_amount_q=parse_money_to_q(closing_amount_raw),
        notes=notes.strip(),
    )
    return shift


def _terminal(terminal_ref: str = ""):
    from shopman.backstage.models import POSTerminal

    ref = str(terminal_ref or "").strip()
    if ref:
        terminal = POSTerminal.objects.filter(ref=ref, is_active=True).first()
        if not terminal:
            raise POSError("Terminal POS inválido.")
        return terminal
    terminal = POSTerminal.objects.filter(is_active=True).order_by("ref").first()
    return terminal or POSTerminal.default()


def cash_movement_receipt_payload(*, operator, movement_id: int, reprint: bool = False) -> dict:
    """Bytes do comprovante, prontos para o agente do balcão imprimir.

    O servidor compõe; a tela só relaia. Devolve base64 porque JSON não carrega
    byte cru, e o caminho todo (tela → agente) já é JSON.
    """
    import base64

    from django.conf import settings

    from shopman.backstage.models import CashMovement, CashShift
    from shopman.backstage.services.receipt_escpos import cash_movement_receipt
    from shopman.backstage.services.receipt_verify import code_for

    shift = CashShift.get_open_for_operator(operator)
    if not shift:
        raise POSError("Caixa não aberto.")
    try:
        # Preso ao turno DO OPERADOR: ninguém tira comprovante do caixa alheio.
        movement = CashMovement.objects.select_related("shift").get(pk=movement_id, shift=shift)
    except CashMovement.DoesNotExist as exc:
        raise POSError("Movimento não encontrado neste turno.") from exc

    code = code_for(movement.pk)
    # A URL sai do host canônico do Admin, não de uma constante inventada.
    #
    # O fallback mora AQUI e não no setting: `SHOPMAN_ADMIN_HOST` também decide
    # que a raiz daquele host redireciona para /admin/, e embutir o host da API
    # nele faria a raiz de `api.` virar porta de Admin — comportamento novo que
    # ninguém pediu. Para o papel, porém, `api.` serve: lá /admin/ responde, e um
    # QR que abre em api. é melhor que um QR mudo.
    host = (
        str(getattr(settings, "SHOPMAN_ADMIN_HOST", "") or "").strip()
        or str(getattr(settings, "SHOPMAN_OPERATOR_API_HOST", "") or "").strip()
    )
    verify_url = f"https://{host}/admin/cash/receipt/{code}/" if host else code
    payload = cash_movement_receipt(
        movement, verify_code=code, verify_url=verify_url, reprint=reprint
    )
    return {
        "movement_id": movement.pk,
        "title": f"comprovante:{movement.movement_type}",
        "payload_b64": base64.b64encode(payload).decode("ascii"),
        "verify_code": code,
    }


def record_receipt_result(*, operator, movement_id: int, status: str, detail: str = ""):
    """Grava o que ACONTECEU com o papel.

    ⚠️ Só o balcão sabe se imprimiu — quem manda ao agente é o navegador. Sem
    este registro, papel que faltou pareceria papel que alguém escondeu, e a
    sangria voltaria a não ter testemunha.

    Nunca volta atrás de `printed`: se já imprimiu uma vez, imprimiu.
    """
    from django.utils import timezone

    from shopman.backstage.models import CashMovement, CashShift

    valores = set(CashMovement.ReceiptStatus.values)
    if status not in valores or status == CashMovement.ReceiptStatus.PENDING:
        raise POSError("Resultado de impressão inválido.")

    shift = CashShift.get_open_for_operator(operator)
    if not shift:
        raise POSError("Caixa não aberto.")
    try:
        movement = CashMovement.objects.get(pk=movement_id, shift=shift)
    except CashMovement.DoesNotExist as exc:
        raise POSError("Movimento não encontrado neste turno.") from exc

    if movement.receipt_status == CashMovement.ReceiptStatus.PRINTED:
        return movement

    movement.receipt_status = status
    movement.receipt_detail = str(detail or "").strip()[:200]
    movement.receipt_at = timezone.now() if status == CashMovement.ReceiptStatus.PRINTED else None
    movement.save(update_fields=["receipt_status", "receipt_detail", "receipt_at"])
    return movement
