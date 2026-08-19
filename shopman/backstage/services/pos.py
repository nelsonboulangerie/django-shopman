"""Mutações de caixa do PDV, sobre o ``cashman``.

O balcão fala em "abrir caixa", "sangria", "pedir troco"; o pacote fala em turno
e lançamento. Este módulo é a tradução: recebe o que a tela manda (texto de
dinheiro, tipo em português, PIN de gerente), valida o que é da superfície e
chama o único escritor do livro (``shopman.cashman.services``). Nada aqui grava
``Entry`` por conta própria, e nada aqui soma o livro: esperado e diferença são
do pacote e da retaguarda, nunca do terminal (fechamento cego, ADR-011 §4).
"""

from __future__ import annotations

from shopman.backstage.services.exceptions import POSError, POSPermissionError

#: Vocabulário do balcão ↔ tipo do livro. O PDV (rota ``pos/cash/movement/``,
#: relatório X/Z, capability ``movement_kinds``) fala ``sangria``/``suprimento``
#: porque é assim que o operador brasileiro chama; o livro fala ``cash_out``/
#: ``cash_in`` porque é assim que o pacote nomeia o efeito. A tradução mora aqui,
#: num lugar só, para o resto do backstage não decorar os dois dialetos.
MOVEMENT_KIND_BY_API: dict[str, str] = {"sangria": "cash_out", "suprimento": "cash_in"}
MOVEMENT_API_BY_KIND: dict[str, str] = {kind: api for api, kind in MOVEMENT_KIND_BY_API.items()}


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
    """Abre o turno do operador com o fundo de troco; devolve o já aberto se houver.

    Idempotente de propósito: a tela reenvia "abrir" depois de um refresh, e um
    segundo turno para a mesma pessoa é o que a constraint do pacote proíbe.
    """
    from shopman.cashman import services as cash
    from shopman.cashman.exceptions import CashError

    existing = cash.open_shift_for(operator)
    if existing:
        return existing

    terminal = _terminal(terminal_ref)
    float_q = max(0, parse_money_to_q(opening_amount_raw))
    try:
        return cash.open_shift(operator=operator, terminal=terminal, float_q=float_q)
    except CashError as exc:
        if exc.code == "SHIFT_ALREADY_OPEN":
            # A tela distingue "terminal ocupado" (409, escolha outro terminal ou
            # feche o turno alheio) de qualquer outra falha (400) por esta mensagem.
            raise POSError("Terminal POS já possui turno aberto.") from exc
        raise POSError(exc.message) from exc


def movement_removes_cash(movement_type: str, amount_q: int) -> bool:
    """O movimento TIRA dinheiro da gaveta?

    Só a sangria. É o único caminho pelo qual dinheiro sai E a contagem cega
    ainda bate — o próprio lançamento justifica a falta, e por isso ele exige a
    segunda assinatura. Suprimento só cria sobra, que aparece na conferência
    sozinha e não tem como esconder desfalque.
    """
    return movement_type == "sangria"


def register_cash_movement(
    *,
    operator,
    movement_type: str = "sangria",
    amount_raw="0",
    reason: str = "",
    manager_approval: dict | None = None,
):
    """Lança sangria (``cash_out``) ou suprimento (``cash_in``) no turno aberto.

    Retirada exige PIN de gerente — SEM limiar, em qualquer valor. Antes um
    operador sozinho lançava sangria à vontade: como o esperado é a soma do
    livro, uma sangria inventada abaixava o esperado e a contagem cega fechava
    redonda. O dinheiro saía e o caixa batia. Agora a retirada tem duas
    assinaturas: quem lança (``operator``) e quem autoriza (``approved_by``),
    ambas gravadas na mesma linha do livro.
    """
    from shopman.shop.services.pos import validate_manager_override

    shift = _open_shift_or_raise(operator)

    api_kind = movement_type if movement_type in MOVEMENT_KIND_BY_API else "sangria"
    amount_q = parse_money_to_q(amount_raw)
    # Sempre positivo na entrada: o sinal vive no TIPO. Aceitar negativo aqui
    # daria um segundo jeito de lançar sangria — disfarçada de suprimento, e sem
    # gerente. O livro recebe o valor já assinado.
    if amount_q <= 0:
        raise POSError("Valor inválido.")

    # O motivo da SAÍDA é exigência do servidor, não da tela. Ele era só do
    # `pos-nuxt`, e um contrato que só a superfície cobra não é contrato: quem
    # chamasse a API crua lançava sangria sem dizer para onde foi o dinheiro, e
    # a segunda assinatura ficaria autorizando um vazio. Na ENTRADA não se
    # pergunta: "entrada de caixa" já é a resposta inteira, e um campo com uma
    # opção só ensina o balcão a preencher qualquer coisa para passar.
    reason = str(reason or "").strip()[:120]
    if api_kind == "sangria" and not reason:
        raise POSError("Informe o motivo da saída.")

    approved_by = None
    if movement_removes_cash(api_kind, amount_q):
        approval = manager_approval or {}
        validate_manager_override(
            approval,
            operator_username=operator.get_username(),
            action=f"cash_{api_kind}",
        )
        approved_by = _approver(approval)

    kind = MOVEMENT_KIND_BY_API[api_kind]
    signed_q = -amount_q if kind == "cash_out" else amount_q
    return _record(
        kind,
        shift=shift,
        operator=operator,
        amount_q=signed_q,
        approved_by=approved_by,
        reason=reason,
    )


def register_drawer_opening(*, operator, reason: str = ""):
    """Registra uma abertura de gaveta SEM venda e sem movimento (``drawer_open``).

    Os outros momentos que abrem a gaveta já deixam rastro sozinhos: a venda em
    dinheiro tem a linha ``sale``, a sangria e o suprimento têm a sua. Este não
    teria nada — é o operador abrindo para conferir, trocar nota, ou por
    qualquer motivo que só ele sabe. Sem registro, é exatamente o buraco que a
    chave física deixava. Efeito zero no saldo; o motivo é a substância.

    ⚠️ Isto NÃO decide quem pode abrir. A política de autorização de gaveta é da
    frente de estresse do PDV (retirada exige PIN em qualquer valor); aqui é o
    caminho físico.
    """
    reason = str(reason or "").strip()[:120]
    if not reason:
        raise POSError("Informe o motivo da abertura.")
    shift = _open_shift_or_raise(operator)
    return _record("drawer_open", shift=shift, operator=operator, reason=reason)


def unlock_drawer(*, operator, manager_approval: dict | None = None, drawer_raw: str = ""):
    """O gerente libera a próxima venda com a gaveta ainda aberta (``drawer_unlock``).

    A trava é do PDV: ele recusa INICIAR a próxima venda enquanto SABE que a
    gaveta está aberta (venda começada nunca vira refém; estado desconhecido
    nunca trava; sem carência). Este é o único jeito de passar por ela, e existe
    para a gaveta emperrada, que existe. Cada liberação vale UMA venda: a
    exceção tratada como exceção é a que se escancara; virasse rotina, o balcão
    aprenderia a pedir o PIN de olhos fechados.

    O lançamento é o produto: quem liberou, para quem, quando, efeito zero. É a
    contagem de "quantos destraves por operador, em que horário" que motivou o
    livro. ``drawer_raw`` é o byte que o sensor devolveu na hora: prova de que a
    trava agiu porque SABIA, não por palpite.
    """
    from shopman.shop.services.pos import validate_manager_override

    shift = _open_shift_or_raise(operator)
    validate_manager_override(
        manager_approval or {},
        operator_username=operator.get_username(),
        action="drawer_unlock",
    )
    payload = {}
    drawer_raw = str(drawer_raw or "").strip()[:16]
    if drawer_raw:
        payload["drawer_raw"] = drawer_raw
    return _record(
        "drawer_unlock",
        shift=shift,
        operator=operator,
        approved_by=_approver(manager_approval or {}),
        payload=payload,
    )


#: As cédulas e moedas que o balcão pode pedir, do maior para o menor.
#:
#: Não é a lista do dinheiro brasileiro — é a lista do que se PEDE como troco.
#: R$ 50, R$ 100 e R$ 200 existem e não estão aqui: ninguém pede troco em nota
#: grande, é o oposto do problema. `shape` só diz o desenho do botão (retangular
#: para cédula, redondo para moeda), porque é assim que a mão reconhece no
#: balcão sem ler.
#:
#: ⚠️ Esta é a FONTE. A tela recebe a lista pela projection (`cash_management`)
#: em vez de repetir os números em TypeScript: duas listas viram uma divergência
#: no dia em que a moeda de R$ 0,25 sair de circulação, e o pedido passaria a
#: falar de um dinheiro que não existe.
CHANGE_DENOMINATIONS: tuple[dict, ...] = (
    {"q": 2000, "label": "20", "shape": "note"},
    {"q": 1000, "label": "10", "shape": "note"},
    {"q": 500, "label": "5", "shape": "note"},
    {"q": 200, "label": "2", "shape": "note"},
    {"q": 100, "label": "1", "shape": "coin"},
    {"q": 50, "label": "0,50", "shape": "coin"},
    {"q": 25, "label": "0,25", "shape": "coin"},
    {"q": 10, "label": "0,10", "shape": "coin"},
    {"q": 5, "label": "0,05", "shape": "coin"},
)

CHANGE_DENOMINATION_VALUES: frozenset[int] = frozenset(d["q"] for d in CHANGE_DENOMINATIONS)


def _clean_denominations(raw) -> list[int]:
    """As cédulas e moedas pedidas, em centavos, do maior para o menor.

    Lista vazia é um pedido completo — "me traz R$ 100" basta, e exigir escolha
    travaria a fila por um detalhe que o gerente resolve com o que tiver no
    cofre. O que NÃO se aceita é valor fora da lista: um pedido de R$ 0,03 não
    é um pedido, é um dedo errado, e ele viajaria calado até o balcão.
    """
    if not raw:
        return []
    if not isinstance(raw, (list, tuple)):
        raise POSError("Denominações inválidas.")
    limpas: set[int] = set()
    for item in raw:
        try:
            valor = int(item)
        except (TypeError, ValueError):
            raise POSError("Denominações inválidas.") from None
        if valor not in CHANGE_DENOMINATION_VALUES:
            raise POSError("Denominação que não existe no troco.")
        limpas.add(valor)
    return sorted(limpas, reverse=True)


def request_change(*, operator, amount_raw="0", denominations=None, note: str = ""):
    """O operador PEDE troco (``change_requested``). Ninguém sai do balcão.

    Este é o ponto todo da feature: quando falta troco, o operador atravessava a
    loja com dinheiro até o cofre, por um trajeto que a câmera só cobre em parte.
    Se sumisse dinheiro ali, ninguém provava nem desprovava, e a falta só
    aparecia no fechamento, horas depois, misturada com o turno inteiro. Aqui o
    dinheiro fica onde está: o operador pede, alguém traz, e a troca acontece no
    balcão, à vista, entre duas pessoas.

    ⚠️ Um pedido NÃO mexe no saldo e nunca vai mexer. Trocar uma nota de R$ 50
    por cinco de R$ 10 é NET ZERO: o total da gaveta não muda. O lançamento tem
    ``amount_q = 0`` por construção (CheckConstraint do pacote); se isto tivesse
    valor, o esperado cairia por um dinheiro que nunca saiu e o turno fecharia
    com falta fantasma — foi exatamente o defeito que o PR #178 teve de desfazer.
    """
    amount_q = parse_money_to_q(amount_raw)
    # O VALOR é o pedido, e é exato. Antes havia um tipo "aproximado" ao lado de
    # "moedas" e "notas pequenas": quem ia buscar o troco lia "moedas" e tinha de
    # adivinhar quanto, e voltava com o que achou. Um número redondo pedido de
    # verdade é o que faz a viagem valer.
    if amount_q <= 0:
        raise POSError("Informe o valor do troco.")

    denominations = _clean_denominations(denominations)
    note = str(note or "").strip()[:120]

    shift = _open_shift_or_raise(operator)
    entry = _record(
        "change_requested",
        shift=shift,
        operator=operator,
        payload={"amount_q": amount_q, "denominations": denominations, "note": note},
    )
    _announce_change_request(shift, _change_request(shift, entry.pk))
    return entry


def serve_change_request(*, operator, request_ref: str, manager_approval: dict | None = None):
    """O gerente traz o troco e assina no balcão (``change_served``). A gaveta abre; o esperado, não.

    Mesma permissão de quem autoriza uma sangria (``cashman.adjust_shift``)
    porque a gaveta abre com dinheiro dentro e alguém de fora do turno mexe nela:
    sem a segunda assinatura, "atender um pedido" viraria um jeito de abrir a
    gaveta sem ninguém olhando — o buraco que este fluxo existe para fechar.
    """
    from shopman.shop.services.pos import validate_manager_override

    validate_manager_override(
        manager_approval or {},
        operator_username=operator.get_username(),
        action="cash_change_request_serve",
    )
    approved_by = _approver(manager_approval or {})

    shift = _open_shift_or_raise(operator)
    request = _pending_request(shift, request_ref)
    entry = _record(
        "change_served",
        shift=shift,
        operator=operator,
        approved_by=approved_by,
        parent=request,
    )
    _announce_change_request(shift, _change_request(shift, request.pk))
    return entry


def cancel_change_request(*, operator, request_ref: str):
    """O operador achou troco na gaveta e o pedido não vale mais (``change_cancelled``).

    Sem esta saída o pendente fica pendurado para sempre, e uma lista com
    pedidos mortos é uma lista em que ninguém acredita — daí a próxima falta de
    troco volta a ser resolvida na caminhada até o cofre.
    """
    shift = _open_shift_or_raise(operator)
    request = _pending_request(shift, request_ref)
    entry = _record("change_cancelled", shift=shift, operator=operator, parent=request)
    _announce_change_request(shift, _change_request(shift, request.pk))
    return entry


def pending_change_requests(shift) -> list[dict]:
    """Os pedidos que ainda esperam alguém trazer o troco.

    O estado não mora em coluna: o pacote dobra ``change_requested`` com o
    ``change_served``/``change_cancelled`` que aponta para ele por ``parent``.
    """
    from shopman.cashman import services as cash

    if shift is None:
        return []
    return [r for r in cash.change_requests(shift) if r.get("status") == "pending"]


def _pending_request(shift, request_ref: str):
    """Acha o pedido pendente, ou explica qual dos dois erros aconteceu.

    Atendido/cancelado tem mensagem própria porque o caso real é duas pessoas na
    mesma tela: se o segundo toque dissesse "não encontrado", o gerente
    procuraria defeito no sistema em vez de ver que o pedido já foi resolvido.
    """
    from shopman.cashman.models import Entry

    entry_id = _int_or_none(request_ref)
    request = (
        Entry.objects.filter(pk=entry_id, shift=shift, kind=Entry.Kind.CHANGE_REQUESTED).first()
        if entry_id is not None
        else None
    )
    if request is None:
        raise POSError("Pedido de troco não encontrado.")
    state = _change_request(shift, request.pk)
    if state.get("status") != "pending":
        raise POSError("Este pedido de troco já foi resolvido.")
    return request


def _change_request(shift, entry_id: int) -> dict:
    from shopman.cashman import services as cash

    for request in cash.change_requests(shift):
        if request["entry_id"] == entry_id:
            return request
    return {"entry_id": entry_id}


def _announce_change_request(shift, request: dict) -> None:
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
            "ref": str(request.get("entry_id") or ""),
            "status": request.get("status", ""),
            "amount_q": request.get("amount_q", 0),
            "denominations": request.get("denominations", []),
            "shift_id": shift.pk,
            "terminal_ref": shift.terminal.ref if shift.terminal_id else "",
            "requested_by": request.get("requested_by", ""),
        }
    )


def close_cash_shift(*, operator, closing_amount_raw="0", notes: str = ""):
    """Fechamento cego do turno do operador: a contagem vira o lançamento ``count``."""
    shift = _open_shift_or_raise(operator)
    _close(shift, actor=operator, counted_raw=closing_amount_raw, notes=notes)
    return shift


def close_blocking_shift(*, actor_user, shift_id, closing_amount_raw="0", notes: str = ""):
    """Fechamento cego SUPERVISÓRIO do turno que bloqueia o terminal.

    Destrava o beco de UX: quando o terminal tem um turno aberto que não é do
    operador atual, ele fica preso sem poder vender. Aqui o GERENTE
    (``perform_closing``) ou o DONO do turno conta a gaveta e fecha o turno
    bloqueante — liberando o terminal. Operador comum não fecha o caixa de
    outro (anti-fraude) → POSPermissionError. Quem fechou fica no lançamento
    ``count`` como quem agiu; o pacote marca ``supervisory`` no payload quando o
    ator não é o dono.
    """
    from shopman.cashman.models import Shift

    from shopman.backstage.permissions import can_close_day

    shift = (
        Shift.objects.filter(pk=_int_or_none(shift_id), status=Shift.Status.OPEN)
        .select_related("terminal", "operator")
        .first()
    )
    if not shift:
        raise POSError("Turno não encontrado ou já fechado.")

    is_owner = shift.operator_id == getattr(actor_user, "pk", None)
    if not (can_close_day(actor_user) or is_owner):
        raise POSPermissionError("Sem permissão para fechar o turno de outro operador.")

    _close(shift, actor=actor_user, counted_raw=closing_amount_raw, notes=notes)
    return shift


def _close(shift, *, actor, counted_raw, notes: str) -> None:
    from shopman.cashman import services as cash
    from shopman.cashman.exceptions import CashError

    try:
        cash.close_shift(shift, counted_q=parse_money_to_q(counted_raw), actor=actor, notes=str(notes or "").strip())
    except CashError as exc:
        raise POSError(exc.message) from exc


def _terminal(terminal_ref: str = ""):
    from shopman.cashman.models import Terminal

    ref = str(terminal_ref or "").strip()
    if ref:
        terminal = Terminal.objects.filter(ref=ref, is_active=True).first()
        if not terminal:
            raise POSError("Terminal POS inválido.")
        return terminal
    terminal = Terminal.objects.filter(is_active=True).order_by("ref").first()
    return terminal or Terminal.default()


def cash_movement_receipt_payload(*, operator, entry_id: int, reprint: bool = False) -> dict:
    """Bytes do comprovante de sangria/suprimento, prontos para o agente do balcão imprimir.

    O servidor compõe a partir da linha do livro; a tela só relaia. Devolve
    base64 porque JSON não carrega byte cru, e o caminho todo (tela → agente) já
    é JSON.
    """
    import base64

    from django.conf import settings

    from shopman.backstage.services.receipt_escpos import cash_movement_receipt
    from shopman.backstage.services.receipt_verify import code_for

    entry = _movement_entry(operator, entry_id)
    code = code_for(entry.pk)
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
    payload = cash_movement_receipt(entry, verify_code=code, verify_url=verify_url, reprint=reprint)
    return {
        "entry_id": entry.pk,
        "title": f"comprovante:{MOVEMENT_API_BY_KIND[entry.kind]}",
        "payload_b64": base64.b64encode(payload).decode("ascii"),
        "verify_code": code,
    }


#: O que o balcão pode dizer sobre o papel. ``pending`` não entra: é o estado de
#: quem ainda não disse nada, e "dizer que não disse" seria linha vazia no livro.
RECEIPT_RESULT_STATUSES = ("printed", "failed", "skipped")


def record_receipt_result(*, operator, entry_id: int, status: str, detail: str = ""):
    """Grava o que ACONTECEU com o papel (``receipt_result`` apontando para a sangria/suprimento).

    ⚠️ Só o balcão sabe se imprimiu — quem manda ao agente é o navegador. Sem
    este registro, papel que faltou pareceria papel que alguém escondeu, e a
    sangria voltaria a não ter testemunha.

    Nunca volta atrás de `printed`: se já imprimiu uma vez, imprimiu — um
    resultado posterior não apaga o anterior (livro é livro), e a leitura
    considera o último; por isso, depois de `printed`, não se grava outro.
    """
    if status not in RECEIPT_RESULT_STATUSES:
        raise POSError("Resultado de impressão inválido.")

    entry = _movement_entry(operator, entry_id)
    last = receipt_result_for(entry)
    if last is not None and (last.payload or {}).get("status") == "printed":
        return last

    return _record(
        "receipt_result",
        shift=entry.shift,
        operator=operator,
        parent=entry,
        payload={"status": status, "detail": str(detail or "").strip()[:200]},
    )


def receipt_result_for(entry):
    """O último ``receipt_result`` que responde a esta linha, ou ``None`` (sem confirmação)."""
    from shopman.cashman.models import Entry

    return entry.children.filter(kind=Entry.Kind.RECEIPT_RESULT).order_by("-at", "-id").first()


def _movement_entry(operator, entry_id: int):
    """A sangria/suprimento pedida, presa aos turnos DO OPERADOR: ninguém tira comprovante do caixa alheio.

    Não exige turno aberto: o navegador pode confirmar a impressão (ou pedir a
    segunda via) depois de o turno fechar, e o pacote aceita ``receipt_result``
    em turno fechado exatamente por isso.
    """
    from shopman.cashman.models import Entry

    entry = (
        Entry.objects.filter(
            pk=_int_or_none(entry_id),
            shift__operator=operator,
            kind__in=list(MOVEMENT_KIND_BY_API.values()),
        )
        .select_related("shift", "shift__terminal", "operator", "approved_by")
        .first()
    )
    if entry is None:
        raise POSError("Movimento não encontrado neste turno.")
    return entry


def _open_shift_or_raise(operator):
    from shopman.cashman import services as cash

    shift = cash.open_shift_for(operator)
    if not shift:
        raise POSError("Caixa não aberto.")
    return shift


def _record(kind, **kwargs):
    """``cashman.services.record`` com a recusa traduzida para o dialeto da superfície."""
    from shopman.cashman import services as cash
    from shopman.cashman.exceptions import CashError

    try:
        return cash.record(kind, **kwargs)
    except CashError as exc:
        raise POSError(exc.message) from exc


def _approver(approval: dict):
    """O gerente que assinou, como User: o livro guarda a pessoa, não o nome digitado."""
    from django.contrib.auth import get_user_model

    username = str(approval.get("username") or "").strip()
    return get_user_model().objects.filter(username=username, is_active=True, is_staff=True).first()


def _int_or_none(value) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
