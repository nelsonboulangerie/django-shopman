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
    """Abre o turno da GAVETA com o fundo de troco; devolve o já aberto se houver.

    ``operator`` fica no turno como ``opened_by`` — quem declarou o fundo, não
    dono da custódia: o balcão inteiro trabalha nesta mesma gaveta até o fim do
    expediente, e cada ato leva o nome de quem o fez, no livro.

    Idempotente de propósito: a tela reenvia "abrir" depois de um refresh, e a
    constraint do pacote proíbe uma segunda custódia na mesma gaveta.
    """
    from shopman.cashman import services as cash
    from shopman.cashman.exceptions import CashError

    # Idempotência agora é por GAVETA: reenviar "abrir" na mesma gaveta devolve
    # o turno que já está lá, seja quem for que apertou.
    terminal = _terminal(terminal_ref)
    existing = cash.open_shift_for_terminal(terminal)
    if existing:
        return existing

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
        # A segunda assinatura do livro é o User que o PIN autorizou, não uma
        # releitura pelo nome digitado: quem valida é quem persiste.
        approved_by = validate_manager_override(
            manager_approval or {},
            operator_username=operator.get_username(),
            action=f"cash_{api_kind}",
        )

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


def report_drawer_blind(*, operator, reason: str = ""):
    """A trava caiu numa estação que TINHA medição — registra e avisa o gerente.

    A trava só age quando SABE, e estado desconhecido nunca trava: um sensor
    ruim tem que degradar para "sem controle", nunca para "balcão parado com
    fila". Essa escolha está certa e não se reabre aqui — mas ela abria a fuga
    mais barata que existia contra a trava. Deixar a gaveta aberta é trabalhoso
    e visível; **puxar o cabo da gaveta é um gesto, uma vez, e desliga a
    proteção para sempre**. E era silencioso: o PDV lia "não sei", seguia a
    venda, e nada em lugar nenhum dizia que a trava tinha existido e sumido.

    Por isso a distinção que o agente passou a reportar (``calibrated``): a
    estação que NUNCA mediu não tem trava e não é notícia; a que MEDIU e parou
    de responder é regressão, e é esta função. Duas saídas, porque são duas
    perguntas diferentes: o ``note`` no livro responde "quando o caixa ficou
    cego" na conferência do turno, e o alerta responde "isso está acontecendo
    agora" para o gerente, com reconhecimento.

    Falhar aberto é aceitável. Falhar aberto e calado é um convite.
    """
    from shopman.backstage.services.alerts import create_alert

    reason = str(reason or "").strip()[:200]
    shift = _open_shift_or_raise(operator)
    entry = _record(
        "note",
        shift=shift,
        operator=operator,
        reason="Sensor da gaveta parou de responder",
        payload={"event": "drawer_sensor_blind", "detail": reason},
    )
    # O alerta é o que chega ao gerente HOJE; o livro é o que sobrevive à
    # conferência. Um não substitui o outro: alerta reconhecido some da tela.
    create_alert(
        type="pos_drawer_sensor_blind",
        severity="warning",
        message=(
            f"A trava da gaveta parou de agir no terminal de {operator.get_username()}: "
            f"o sensor foi medido nesta estação e agora não responde ({reason or 'sem detalhe'}). "
            "As vendas seguem, mas sem a trava. Confira o cabo da gaveta na impressora."
        ),
    )
    return entry


#: Como um bloqueio da gaveta terminou. `closed` é o caminho normal (o operador
#: fechou a gaveta e o balcão voltou sozinho); os outros são exceção e precisam
#: ser distinguíveis dele no B.I., senão a anomalia some na média.
#:
#: ⚠️ `dismissed` entrou depois, e a lacuna que ele fecha foi achada OLHANDO A
#: TELA, não pelos testes: o X do canto do diálogo encerrava o bloqueio sem
#: gerar linha nenhuma. Não era brecha de venda — a próxima tentativa trava de
#: novo — mas era brecha de rastro, e dava para esbarrar na trava e desistir a
#: manhã inteira sem deixar registro.
DRAWER_OUTCOMES = ("closed", "sensor_lost", "manager_override", "dismissed")


def _drawer_outcome(value, *, default: str) -> str:
    outcome = str(value or "").strip()
    return outcome if outcome in DRAWER_OUTCOMES else default


def _duration_ms(value) -> int:
    """Duração vinda da tela: inteiro, não-negativo, e com teto de 24h.

    O número nasce no relógio do navegador do balcão, então não é confiável por
    construção — um kiosk com a hora errada, ou a aba dormindo, produz duração
    absurda. O teto impede que um outlier desses envenene a média do B.I. sem
    que ninguém entenda de onde veio.
    """
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(ms, 24 * 60 * 60 * 1000))


def record_drawer_block(*, operator, duration_ms: int = 0, outcome: str = "closed", drawer_raw: str = ""):
    """O bloqueio da gaveta terminou — quanto tempo durou e como acabou.

    Este lançamento é a razão de a trava dura valer mais que o pedágio antigo:
    com a liberação vindo do sensor, o sistema passa a saber **quanto tempo a
    gaveta ficou aberta de verdade**. No desenho anterior o PIN cortava a
    medição no meio — liberava a venda e a gaveta seguia aberta sem ninguém
    contando.

    Efeito zero no dinheiro: é um ``note``, e o payload é o que o B.I. lê.
    """
    shift = _open_shift_or_raise(operator)
    payload = {
        "event": "drawer_blocked",
        "outcome": _drawer_outcome(outcome, default="closed"),
        "duration_ms": _duration_ms(duration_ms),
    }
    drawer_raw = str(drawer_raw or "").strip()[:16]
    if drawer_raw:
        payload["drawer_raw"] = drawer_raw
    return _record(
        "note",
        shift=shift,
        operator=operator,
        reason="Bloqueio por gaveta aberta",
        payload=payload,
    )


def report_drawer_left_open(*, operator, minutes: int = 0):
    """A gaveta ficou aberta ENTRE vendas — avisa o gerente e grava.

    A trava dura resolve o instante da venda: com a gaveta aberta, o balcão não
    anda. Mas ela só age quando alguém tenta vender, e a hora morta ficava
    descoberta — ninguém inicia venda, ninguém olha, e a gaveta passa a tarde
    aberta. Este é o olho dessa hora: a página já sonda o agente a cada 60s, e
    passa a ler a gaveta junto.

    O limiar é do dono (regra `pos_drawer_idle_alert`, `minutes`), porque
    "tempo demais" é julgamento de balcão, não constante de código.
    """
    from shopman.backstage.services.alerts import create_alert

    minutes = max(0, int(minutes or 0))
    shift = _open_shift_or_raise(operator)
    entry = _record(
        "note",
        shift=shift,
        operator=operator,
        reason="Gaveta aberta sem venda",
        payload={"event": "drawer_left_open", "minutes": minutes},
    )
    create_alert(
        type="pos_drawer_left_open",
        severity="warning",
        message=(
            f"A gaveta do terminal de {operator.get_username()} está aberta há "
            f"{minutes} min sem nenhuma venda começar. Confira o balcão."
        ),
    )
    return entry


#: O que aconteceu depois de alguém abrir a tela de PIN da trava.
UNLOCK_ATTEMPT_OUTCOMES = ("opened", "abandoned", "denied")


def record_unlock_attempt(*, operator, outcome: str = "opened"):
    """Alguém ABRIU a tela de PIN da trava — mesmo que não tenha destravado.

    A tela de trava não mostra a saída de emergência (botão de PIN ensina o
    bypass: a exceção vira o caminho conhecido). Quem foi treinado sabe que Esc
    abre o PIN. Justamente por ser escondida, **procurar a saída é informação** —
    provavelmente a mais valiosa que essa tela produz.

    Registrar só o destrave bem-sucedido perderia o padrão que interessa: o
    operador que tenta o PIN do gerente cinco vezes por turno e desiste não
    aparece em lugar nenhum, e é exatamente ele que se quer enxergar. Por isso
    ``abandoned`` (Esc de volta) e ``denied`` (PIN recusado) entram no livro do
    mesmo jeito que ``opened``.
    """
    shift = _open_shift_or_raise(operator)
    outcome = str(outcome or "").strip()
    if outcome not in UNLOCK_ATTEMPT_OUTCOMES:
        outcome = "opened"
    return _record(
        "note",
        shift=shift,
        operator=operator,
        reason="Tela de PIN da trava da gaveta",
        payload={"event": "drawer_unlock_attempt", "outcome": outcome},
    )


def unlock_drawer(
    *,
    operator,
    manager_approval: dict | None = None,
    drawer_raw: str = "",
    duration_ms: int = 0,
    outcome: str = "manager_override",
):
    """O gerente libera o balcão pela EMERGÊNCIA (``drawer_unlock``).

    ⚠️ Mudou de natureza (decisão do dono, 29/08). A trava era um pedágio — o
    gerente liberava UMA venda com a gaveta ainda aberta — e virou trava dura:
    o PDV não anda enquanto a gaveta estiver aberta, e **quem libera é o mundo
    físico**, o bloqueio cai sozinho quando o sensor diz que fechou.

    Então este caminho deixou de ser o destrave e passou a ser a **exceção**:
    gaveta emperrada fisicamente aberta, ou sensor morto. No dia normal ninguém
    digita PIN nenhum, porque fechar a gaveta já destrava — e é por isso que a
    fadiga de autorização (o gerente que digita no automático até virar reflexo)
    desapareceu por construção.

    ``outcome`` carrega essa natureza para o livro. Sem ele, a emergência ficaria
    indistinguível do fechamento normal e a anomalia que interessa — o gerente
    que libera 20× por dia — sumiria na média. ``duration_ms`` é quanto tempo a
    gaveta ficou aberta até aqui: antes o PIN mascarava esse número, porque
    liberava a venda sem ninguém saber se foram 10 segundos ou a manhã inteira.

    ``drawer_raw`` é o byte que o sensor devolveu: prova de que a trava agiu
    porque SABIA, não por palpite.
    """
    from shopman.shop.services.pos import validate_manager_override

    shift = _open_shift_or_raise(operator)
    # A segunda assinatura do livro é o User que o PIN autorizou, não uma
    # releitura pelo nome digitado: quem valida é quem persiste.
    approved_by = validate_manager_override(
        manager_approval or {},
        operator_username=operator.get_username(),
        action="drawer_unlock",
    )
    payload = {"outcome": _drawer_outcome(outcome, default="manager_override")}
    drawer_raw = str(drawer_raw or "").strip()[:16]
    if drawer_raw:
        payload["drawer_raw"] = drawer_raw
    duration_ms = _duration_ms(duration_ms)
    if duration_ms:
        payload["duration_ms"] = duration_ms
    return _record(
        "drawer_unlock",
        shift=shift,
        operator=operator,
        approved_by=approved_by,
        payload=payload,
    )


def refund_cash(*, operator, order_ref: str, manager_approval: dict | None = None) -> int:
    """Devolve ao cliente o dinheiro de uma venda cancelada, pela gaveta deste turno.

    Cancelar não é devolver: o cancel (PDV fora da janela, gestor, de noite)
    deixa o dinheiro pendente; este é o gesto físico, com turno aberto e PIN de
    gerente (dinheiro sai da gaveta com segunda assinatura, como a sangria). O
    shop grava o Payman e a linha ``refund`` na mesma transação.
    """
    from shopman.orderman.models import Order

    from shopman.shop.services import payment as payment_service
    from shopman.shop.services.pos import validate_manager_override

    shift = _open_shift_or_raise(operator)
    approved_by = validate_manager_override(
        manager_approval or {},
        operator_username=operator.get_username(),
        action="cash_refund",
    )
    order = Order.objects.filter(ref=str(order_ref or "").strip()).first()
    if order is None:
        raise POSError("Pedido não encontrado.")
    if order.status not in {Order.Status.CANCELLED, Order.Status.RETURNED}:
        raise POSError("Só se devolve dinheiro de venda cancelada ou devolvida.")
    refunded_q = payment_service.refund_cash(
        order,
        shift=shift,
        actor=operator,
        approved_by=approved_by,
        reason="devolução de venda cancelada",
    )
    if refunded_q <= 0:
        raise POSError("Esta venda não tem dinheiro pendente de devolução.")
    return refunded_q


def settle_account(*, operator, customer_ref: str, amount_raw: str, method: str):
    """O cliente acertou (parte d)a conta. Em dinheiro, entra no turno ABERTO de quem recebeu.

    Entrada não exige PIN (suprimento também não). O shop captura os intents
    ``account`` mais antigos inteiros até o valor e, em dinheiro, grava
    ``account_settled`` no livro na mesma transação; pix/cartão/external são
    atestados no balcão (``gateway_data.settled_with``).
    """

    from shopman.shop.services import house_account

    method = str(method or "").strip().lower()
    shift = current_shift() if method == "cash" else None
    try:
        return house_account.settle_account(
            customer_ref,
            parse_money_to_q(amount_raw),
            method,
            shift=shift,
            actor=operator,
        )
    except house_account.HouseAccountError as exc:
        raise POSError(str(exc)) from exc


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
    return _record(
        "change_requested",
        shift=shift,
        operator=operator,
        payload={"amount_q": amount_q, "denominations": denominations, "note": note},
    )


def serve_change_request(*, operator, request_ref: str, manager_approval: dict | None = None):
    """O gerente traz o troco e assina no balcão (``change_served``). A gaveta abre; o esperado, não.

    Mesma permissão de quem autoriza uma sangria (``cashman.adjust_shift``)
    porque a gaveta abre com dinheiro dentro e alguém de fora do turno mexe nela:
    sem a segunda assinatura, "atender um pedido" viraria um jeito de abrir a
    gaveta sem ninguém olhando — o buraco que este fluxo existe para fechar.
    """
    from shopman.shop.services.pos import validate_manager_override

    approved_by = validate_manager_override(
        manager_approval or {},
        operator_username=operator.get_username(),
        action="cash_change_request_serve",
    )

    shift = _open_shift_or_raise(operator)
    request = _pending_request(shift, request_ref)
    return _record(
        "change_served",
        shift=shift,
        operator=operator,
        approved_by=approved_by,
        parent=request,
    )


def cancel_change_request(*, operator, request_ref: str):
    """O operador achou troco na gaveta e o pedido não vale mais (``change_cancelled``).

    Sem esta saída o pendente fica pendurado para sempre, e uma lista com
    pedidos mortos é uma lista em que ninguém acredita — daí a próxima falta de
    troco volta a ser resolvida na caminhada até o cofre.
    """
    shift = _open_shift_or_raise(operator)
    request = _pending_request(shift, request_ref)
    return _record("change_cancelled", shift=shift, operator=operator, parent=request)


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
    state = change_request_state(shift, request.pk)
    if state.get("status") != "pending":
        raise POSError("Este pedido de troco já foi resolvido.")
    return request


def change_request_state(shift, entry_id: int) -> dict:
    """O estado dobrado de UM pedido de troco (pendente, atendido ou cancelado)."""
    from shopman.cashman import services as cash

    for request in cash.change_requests(shift):
        if request["entry_id"] == entry_id:
            return request
    return {"entry_id": entry_id}


def close_cash_shift(*, actor_user, closing_amount_raw="0", notes: str = "", terminal_ref: str = ""):
    """Fechamento cego da GAVETA no fim do expediente. Um caminho, um dono.

    Existiam dois: este e um ``close_blocking_shift`` "supervisório", que servia
    para destravar o beco em que a segunda pessoa do balcão caía — terminal com
    turno aberto de outra pessoa. Esse beco deixou de existir com a custódia na
    gaveta, e com ele o segundo caminho: fechar o caixa é uma coisa só.

    **Quem fecha é quem tem ``perform_closing``** (a gerência). Decisão do dono
    em 21/08/2026: a contagem é cega, então tecnicamente qualquer um poderia
    contar sem conseguir burlar — mas a responsabilidade começa na gerência. Não
    há mais exceção para "o dono do turno": a gaveta não tem dono.

    ⚠️ Consequência operacional: sem ninguém da gerência por perto, a gaveta fica
    aberta e as vendas do dia seguinte caem no turno de ontem. É o mesmo risco
    que já existe (há turno aberto no staging desde 19/08), agora com uma porta a
    menos. Afrouxar é uma linha: somar ``can_operate_pos`` ao teste abaixo.
    """
    from shopman.backstage.permissions import can_close_day

    if not can_close_day(actor_user):
        raise POSPermissionError("Fechar o caixa é da gerência. Peça a quem fecha o dia.")

    shift = current_shift(terminal_ref)
    if not shift:
        raise POSError("Caixa não aberto.")
    _close(shift, actor=actor_user, counted_raw=closing_amount_raw, notes=notes)
    return shift


def _close(shift, *, actor, counted_raw, notes: str) -> None:
    from shopman.cashman import services as cash
    from shopman.cashman.exceptions import CashError

    try:
        cash.close_shift(shift, counted_q=parse_money_to_q(counted_raw), actor=actor, notes=str(notes or "").strip())
    except CashError as exc:
        raise POSError(exc.message) from exc


def current_shift(terminal_ref: str = ""):
    """O turno aberto da GAVETA em que se está trabalhando — ou ``None``.

    Dono único da pergunta "qual é o caixa aberto agora". Substituiu
    ``cash.open_shift_for(operator)``, que perguntava pela PESSOA: num balcão que
    se reveza, a segunda pessoa do dia não tinha turno seu e o sistema concluía
    que não havia caixa aberto.

    ⚠️ Sem ``terminal_ref``, ``_terminal()`` devolve o primeiro terminal ativo.
    Com UMA gaveta isso é exato. Quando a loja tiver balcão + totem, quem chama
    precisa passar o ref — e é por isso que o parâmetro existe desde já, em vez
    de um default escondido que só quebraria no dia da segunda gaveta.
    """
    from shopman.cashman import services as cash

    return cash.open_shift_for_terminal(_terminal(terminal_ref))


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


def cash_movement_receipt_payload(*, operator, entry_id: int, reprint: bool = False, terminal_ref: str = "") -> dict:
    """Bytes do comprovante de sangria/suprimento, prontos para o agente do balcão imprimir.

    O servidor compõe a partir da linha do livro; a tela só relaia. Devolve
    base64 porque JSON não carrega byte cru, e o caminho todo (tela → agente) já
    é JSON.
    """
    import base64

    from django.conf import settings

    from shopman.backstage.services.receipt_escpos import cash_movement_receipt
    from shopman.backstage.services.receipt_verify import code_for

    entry = _movement_entry(operator, entry_id, terminal_ref)
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


def _receipt_result_statuses() -> tuple[str, ...]:
    """O que o balcão pode dizer sobre o papel — a lista é do pacote.

    ``pending`` não entra: é o estado de quem ainda não disse nada, e "dizer que
    não disse" seria linha vazia no livro. A validação aqui existe para a
    mensagem ser do dialeto do balcão; quem recusa de verdade é o único escritor
    (``cashman.services.record``), que lê a MESMA lista.
    """
    from shopman.cashman.models import Entry

    return tuple(sorted(Entry.RECEIPT_STATUSES))


def record_receipt_result(*, operator, entry_id: int, status: str, detail: str = "", terminal_ref: str = ""):
    """Grava o que ACONTECEU com o papel (``receipt_result`` apontando para a sangria/suprimento).

    ⚠️ Só o balcão sabe se imprimiu — quem manda ao agente é o navegador. Sem
    este registro, papel que faltou pareceria papel que alguém escondeu, e a
    sangria voltaria a não ter testemunha.

    Nunca volta atrás de `printed`: se já imprimiu uma vez, imprimiu — um
    resultado posterior não apaga o anterior (livro é livro), e a leitura
    considera o último; por isso, depois de `printed`, não se grava outro.

    ⚠️ **Decisão consciente: aqui a guarda é leitura-e-grava, sem constraint.**
    Entre o `receipt_result_for` e o `_record` cabe um segundo toque, e dois
    resultados podem entrar. Diferente da venda (onde a unicidade é
    `UniqueConstraint` no pacote, porque uma linha a mais dobra o dinheiro
    esperado do turno), aqui o efeito no saldo é ZERO por construção: o pior caso
    é uma linha a mais na trilha do papel, e a leitura já é "o último filho
    vence". Constraint por tipo+pai só para isso seria índice pago para prevenir
    uma anotação repetida. Se um dia o resultado do papel virar decisão de
    dinheiro, esta escolha muda junto.
    """
    if status not in _receipt_result_statuses():
        raise POSError("Resultado de impressão inválido.")

    entry = _movement_entry(operator, entry_id, terminal_ref)
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


def _movement_entry(operator, entry_id: int, terminal_ref: str = ""):
    """A sangria/suprimento pedida, presa aos turnos DAQUELA GAVETA.

    A regra continua sendo "ninguém tira comprovante de caixa alheio"; o que
    mudou é o que *alheio* quer dizer. Era ``shift__operator=operator`` — o
    turno da pessoa. Num balcão que se reveza dentro de um turno só, isso
    recusaria a segunda via de uma sangria que a colega lançou meia hora antes,
    na MESMA gaveta. Alheio agora é outra gaveta: o balcão não imprime o
    comprovante do totem.

    ``operator`` fica na assinatura porque quem chama já o tem e o gate de
    permissão é dele; a busca, essa, é pela gaveta.

    Não exige turno aberto: o navegador pode confirmar a impressão (ou pedir a
    segunda via) depois de o turno fechar, e o pacote aceita ``receipt_result``
    em turno fechado exatamente por isso.
    """
    from shopman.cashman.models import Entry

    entry = (
        Entry.objects.filter(
            pk=_int_or_none(entry_id),
            shift__terminal=_terminal(terminal_ref),
            kind__in=list(MOVEMENT_KIND_BY_API.values()),
        )
        .select_related("shift", "shift__terminal", "operator", "approved_by")
        .first()
    )
    if entry is None:
        raise POSError("Movimento não encontrado nesta gaveta.")
    return entry


def _open_shift_or_raise(operator):
    shift = current_shift()
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


def _int_or_none(value) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
