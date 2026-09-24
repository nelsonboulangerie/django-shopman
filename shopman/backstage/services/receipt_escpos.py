"""Composição ESC/POS dos comprovantes do balcão.

**O servidor compõe, o agente só entrega.** Leiaute, tabela de acento e largura
têm um dono só; o agente do balcão é um cano que recebe bytes prontos. Se cada
máquina compusesse, dois balcões imprimiriam diferente e a DANFE — que tem
leiaute exigido por lei — teria de ser reimplementada em cada um.

Os números aqui não são chute: saíram da página de teste rodada no balcão da
Nelson em 2026-08-15.

- **CP860** é IMPOSTA a cada impressão (`ESC t 3`), não descoberta. O teste
  provou que a impressora obedece ao comando, então não dependemos do que veio
  de fábrica nem de quem mexeu na configuração antes.
- **48 colunas**, medido com régua no papel.
- **QR nativo** (`GS ( k`), confirmado lendo com o celular.
"""

from __future__ import annotations

ESC = 0x1B
GS = 0x1D

#: `ESC t 3` — PC860, a tabela portuguesa. Imposta em toda impressão.
CODE_PAGE = 3
ENCODING = "cp860"
COLUMNS = 48


def cash_movement_receipt(entry, *, verify_code: str, verify_url: str, reprint: bool = False) -> bytes:
    """Comprovante de movimento de gaveta (sangria, suprimento) a partir da linha do livro.

    ``entry`` é um ``cashman.Entry`` de tipo ``cash_out``/``cash_in``: o papel é
    a projeção impressa dessa linha, e nada mais.

    ⚠️ O comprovante NÃO é a verdade — ele **aponta** para ela. O código e o QR
    resolvem para o registro; papel inventado não tem código que resolva, e
    conferir vira apontar o celular. Isso não impede fotocópia de um comprovante
    legítimo; torna a fraude detectável em vez de invisível.
    """
    from shopman.utils.monetary import format_money

    out = bytearray()
    out += bytes([ESC, ord("@")])  # reset: não herda estado do job anterior
    out += bytes([ESC, ord("t"), CODE_PAGE])

    out += _centered("NELSON BOULANGERIE")
    out += _centered(str(entry.get_kind_display()).upper())
    if reprint:
        # Sem esta marca, dois papéis idênticos circulam e a segunda via passa
        # por original.
        out += _centered("*** 2a VIA ***")
    out += _rule()

    # Contexto primeiro, em três linhas: QUANDO, QUEM, POR QUÊ.
    #
    # As duas assinaturas moram na MESMA linha porque são um par — quem lança e
    # quem autoriza. Separá-las fazia a segunda parecer um detalhe do cabeçalho,
    # quando ela é a substância da autorização de uma retirada.
    out += _line(f"Turno #{entry.shift_id} · {_local(entry.at)}")
    quem = entry.operator.get_username() if entry.operator_id else "-"
    if entry.approved_by_id:
        quem = f"{quem} · autorizado por {entry.approved_by.get_username()}"
    out += _line(quem)
    for pedaco in _wrap(f"Motivo: {entry.reason or '-'}", COLUMNS):
        out += _line(pedaco)

    # O VALOR sozinho, emoldurado, no meio do papel. Com o sinal dentro do
    # número (`+`/`−`), quem confere soma o maço sem ler o cabeçalho de cada
    # folha — e é literalmente isso que a conferência faz. Emoldurar em vez de
    # empilhar no topo: cercado de branco, o olho acha antes de procurar.
    # O sinal é o do próprio lançamento: sangria é negativa no livro.
    out += _rule()
    out += _line("")
    sinal = "-" if entry.amount_q < 0 else "+"
    out += _double(f"{sinal} R$ {format_money(abs(int(entry.amount_q)))}")
    out += _line("")
    out += _rule()

    out += _centered(verify_code)
    out += _centered("confira apontando a camera")
    # ⚠️ Centralizado. Sem `ESC a 1` o QR sai encostado à esquerda, com metade do
    # papel vazia ao lado — parece defeito de impressão.
    out += _qr(verify_url)

    out += bytes([ESC, ord("d"), 4])
    out += bytes([GS, ord("V"), 1])  # corte parcial
    return bytes(out)


#: Caracteres que o operador digita (ou que o teclado/celular põem sozinhos) e
#: que a CP860 não tem. Sem esta tradução eles viram "?" no papel — o motivo da
#: sangria sairia corrompido e pareceria defeito da impressora.
_TRANSLITERACAO = str.maketrans(
    {
        "—": "-",
        "–": "-",
        "―": "-",
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "‚": "'",
        "…": "...",
        "•": "*",
        "·": "-",
        "€": "EUR",
        "™": "TM",
        "→": "->",
        "≠": "!=",
        "≤": "<=",
        "≥": ">=",
        "\u00a0": " ",  # espaço não separável, comum em texto colado
    }
)


def _line(text: str) -> bytes:
    return text.translate(_TRANSLITERACAO).encode(ENCODING, "replace") + b"\n"


def _double(text: str, columns: int = COLUMNS) -> bytes:
    """Uma linha em corpo duplo (largura e altura), centrada.

    `GS ! n`: o nibble alto é a largura, o baixo a altura — `0x11` dobra as
    duas. Volta a `0x00` na mesma função, senão o resto do papel sai gigante:
    o modo é de estado, não de escopo.
    """
    recorte = text[: columns // 2]
    margem = max(0, (columns // 2 - len(recorte)) // 2)
    return bytes([GS, ord("!"), 0x11]) + _line(" " * margem + recorte) + bytes([GS, ord("!"), 0x00])


def _centered(text: str, columns: int = COLUMNS) -> bytes:
    recorte = text[:columns]
    margem = max(0, (columns - len(recorte)) // 2)
    return _line(" " * margem + recorte)


def _rule(columns: int = COLUMNS) -> bytes:
    return _line("-" * columns)


def _pair(left: str, right: str, columns: int = COLUMNS) -> bytes:
    espaco = max(1, columns - len(left) - len(right))
    return _line(f"{left}{' ' * espaco}{right}"[:columns])


def _wrap(text: str, width: int) -> list[str]:
    """Quebra por palavra; palavra maior que a linha é cortada, não sumida."""
    linhas: list[str] = []
    atual = ""
    for palavra in str(text).split():
        while len(palavra) > width:
            if atual:
                linhas.append(atual)
                atual = ""
            linhas.append(palavra[:width])
            palavra = palavra[width:]
        if not atual:
            atual = palavra
        elif len(atual) + 1 + len(palavra) <= width:
            atual = f"{atual} {palavra}"
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas or ["-"]


def _local(quando) -> str:
    from django.utils import timezone

    return timezone.localtime(quando).strftime("%d/%m/%Y %H:%M")


def _qr(data: str, *, module: int = 6) -> bytes:
    """QR nativo do ESC/POS, modelo 2.

    ⚠️ O comprimento conta ``cn``, ``fn`` e ``m`` além dos dados — três bytes a
    mais. Errar isso é o defeito clássico deste comando.
    """
    payload = data.encode("utf-8")
    tamanho = len(payload) + 3
    # `ESC a 1` centraliza, `ESC a 0` devolve à esquerda. É modo de ESTADO: sem
    # o retorno, tudo abaixo do QR sairia centralizado também.
    return (
        bytes([ESC, ord("a"), 1])
        + bytes(
            [GS, 0x28, 0x6B, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00]
            + [GS, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x43, module]
            + [GS, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x45, 0x31]
            + [GS, 0x28, 0x6B, tamanho % 256, tamanho // 256, 0x31, 0x50, 0x30]
        )
        + payload
        + bytes([GS, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x51, 0x30])
        + bytes([ESC, ord("a"), 0])
    )


def production_label_run(
    document: dict,
    *,
    copy_number: int = 1,
    columns: int = COLUMNS,
    cut_mode: str = "partial",
) -> bytes:
    """Render one frozen preparation-label document to ESC/POS.

    Blind documents deliberately have no recipe/preparation name, ref, output
    SKU or source-order text.  Ingredient name + SKU are safe and operationally
    necessary: blindness is about the formula being weighed, not about asking
    the operator to identify anonymous ingredient codes.
    """
    if not 24 <= columns <= 72:
        raise ValueError("A etiqueta exige entre 24 e 72 colunas imprimíveis.")
    mode = str(document.get("mode") or "")
    if mode not in {"blind", "explicit"}:
        raise ValueError("Modo de etiqueta inválido.")
    tickets = document.get("tickets")
    if not isinstance(tickets, list) or not tickets:
        raise ValueError("Documento de etiquetas vazio.")

    out = bytearray()
    for index, ticket in enumerate(tickets):
        if index:
            out += _rule(columns)
        out += bytes([ESC, ord("@")])
        out += bytes([ESC, ord("t"), CODE_PAGE])
        out += _centered("PESAGEM INTERNA" if mode == "blind" else "PREPARO INTERNO", columns)
        if copy_number > 1:
            out += _centered(f"*** {copy_number}ª VIA ***", columns)
        if mode == "blind":
            out += _double(str(ticket["blind_code"]), columns)
        else:
            for part in _wrap(str(ticket["name"]), columns):
                out += _centered(part, columns)
            out += _centered(str(ticket["output_sku"]), columns)
            total_weight = str(ticket.get("total_weight_display") or "")
            if total_weight:
                out += _centered(f"Alvo total: {total_weight}", columns)
            output = str(ticket.get("output_quantity_display") or "")
            if output:
                out += _centered(f"Rendimento previsto: {output}", columns)
        if mode == "blind":
            out += _line(f"Data {ticket['made_display']}")
        else:
            out += _pair(
                f"Preparo {ticket['made_display']}",
                f"Validade {ticket['expiry_display']}",
                columns,
            )
        out += _rule(columns)
        for ingredient in ticket.get("ingredients", ()):
            # Identification hierarchy: human name first, SKU second.  Never
            # emit a bare SKU as the only identity on the paper.
            for part in _wrap(str(ingredient["name"]), columns):
                out += _line(part)
            out += _pair(
                f"  {ingredient['sku']}",
                str(ingredient.get("target_display") or ingredient["quantity_display"]),
                columns,
            )
            annotation = str(ingredient.get("annotation") or "")
            if annotation:
                out += _line(f"  {annotation}")
        out += bytes([ESC, ord("d"), 3])
        if cut_mode == "partial":
            out += bytes([GS, ord("V"), 1])
        elif cut_mode != "none":
            raise ValueError("Modo de corte inválido.")
    return bytes(out)


def sale_receipt(order, *, shop_name: str = "", reprint: bool = False) -> bytes:
    """Recibo NÃO fiscal da venda de balcão — a projeção impressa do pedido.

    Compõe do que a venda GRAVOU (``Order`` + ``Order.data``), nunca do estado
    vivo da tela: o recibo é registro do que foi vendido, e por isso reimprime
    igual amanhã. Pagamentos saem por linha de ``payment.tenders``; "Recebido" e
    "Troco" só aparecem quando o operador digitou com quanto o cliente pagou
    (``tendered_q``/``change_q`` são medição — ausência é "não medido", nunca
    "pagou justo").
    """
    from shopman.utils.monetary import format_money

    from shopman.backstage.presentation.status import payment_method_label

    data = order.data or {}
    out = bytearray()
    out += bytes([ESC, ord("@")])  # reset: não herda estado do job anterior
    out += bytes([ESC, ord("t"), CODE_PAGE])

    out += _centered((shop_name or "NELSON BOULANGERIE").upper())
    out += _centered("Recibo não fiscal")
    if reprint:
        # Sem esta marca, dois papéis idênticos circulam e a segunda via passa
        # por original — mesma regra do comprovante de gaveta.
        out += _centered("*** 2a VIA ***")
    out += _rule()

    out += _pair(f"Pedido {order.ref}", _local(order.created_at))
    tab_display = str(data.get("tab_display") or "")
    if tab_display:
        out += _line(f"Comanda #{tab_display}"[:COLUMNS])
    customer_name = str((data.get("customer") or {}).get("name") or "")
    if customer_name:
        out += _line(f"Cliente: {customer_name}"[:COLUMNS])
    out += _rule()

    for item in order.items.all():
        for pedaco in _wrap(item.name, COLUMNS):
            out += _line(pedaco)
        qty = item.qty.normalize() if hasattr(item.qty, "normalize") else item.qty
        out += _pair(
            f"  {qty} x R$ {format_money(int(item.unit_price_q or 0))}",
            f"R$ {format_money(int(item.line_total_q or 0))}",
        )
    out += _rule()

    out += _line("")
    out += _double(f"TOTAL R$ {format_money(int(order.total_q or 0))}")
    out += _line("")

    payment = data.get("payment") or {}
    tenders = [
        tender for tender in (payment.get("tenders") or []) if isinstance(tender, dict) and tender.get("amount_q")
    ]
    # ⚠️ Venda COD: o dinheiro ainda não entrou. A linha do tender saía igual à
    # de uma venda paga, com "Recebido"/"Troco" e "Obrigado pela preferência!"
    # — um recibo dizendo que o cliente pagou o que ele ainda vai pagar na
    # porta. O papel afirma a pendência até o acerto (``cod_settled_at``).
    cod_pending = _cod_pending(payment, tenders)
    if tenders:
        for tender in tenders:
            out += _pair(
                _tender_label(tender, pending=cod_pending)[: COLUMNS // 2],
                f"R$ {format_money(int(tender.get('amount_q') or 0))}",
            )
    elif payment.get("method"):
        out += _pair(
            payment_method_label(str(payment.get("method")))[: COLUMNS // 2],
            f"R$ {format_money(int(payment.get('amount_q') or order.total_q or 0))}",
        )
    tendered_q = payment.get("tendered_q")
    change_q = payment.get("change_q")
    if not cod_pending:
        if isinstance(tendered_q, int) and tendered_q > 0:
            out += _pair("Recebido", f"R$ {format_money(tendered_q)}")
        if isinstance(change_q, int) and change_q > 0:
            out += _pair("Troco", f"R$ {format_money(change_q)}")
    out += _rule()

    if cod_pending:
        from shopman.shop.services.order_helpers import get_fulfillment_type

        out += _centered("*** PAGAMENTO PENDENTE ***")
        out += _centered("COBRAR NA ENTREGA" if get_fulfillment_type(order) == "delivery" else "COBRAR NA RETIRADA")
    else:
        out += _centered("Obrigado pela preferência!")

    out += bytes([ESC, ord("d"), 4])
    out += bytes([GS, ord("V"), 1])  # corte parcial
    return bytes(out)


def _cod_pending(payment: dict, tenders: list[dict]) -> bool:
    """Algum tender é cobrança NA PORTA e o acerto ainda não aconteceu?

    O carimbo do acerto é ``payment.cod_settled_at``
    (``operator_orders.settle_delivery_cash``). Sem tender gravado, vale a
    marca do pagamento inteiro (``payment.collection``).
    """
    if payment.get("cod_settled_at"):
        return False
    if tenders:
        return any(str(t.get("collection") or "").strip().lower() == "on_delivery" for t in tenders)
    return str(payment.get("collection") or "").strip().lower() == "on_delivery"


def _tender_label(tender: dict, *, pending: bool) -> str:
    """A linha do tender; a parcela da porta ganha "(pendente)" enquanto o acerto não vem."""
    from shopman.backstage.presentation.status import payment_method_label

    label = payment_method_label(str(tender.get("method") or ""))
    if pending and str(tender.get("collection") or "").strip().lower() == "on_delivery":
        return f"{label} (pendente)"
    return label


def _commitment_headline(order) -> tuple[str, str]:
    """As duas linhas de longe do painel: ``(dia, janela)``, em caixa alta.

    ⚠️ **Não existe campo ``scheduled_for``.** O compromisso mora em
    ``Order.data["delivery_date"]`` e quem o lê é ``get_commitment_date`` — ler
    a chave crua é como o agendamento se perde numa superfície nova.

    Pedido SEM data combinada não vira "HOJE": a venda anotada há três dias e
    nunca agendada apareceria no topo do painel como trabalho de agora. Ele diz
    o que é — ``SEM AGENDAMENTO`` — e a data de criação sai no corpo.
    """
    from datetime import timedelta

    from django.utils import formats, timezone

    from shopman.shop.services.fulfillment_window import window_label
    from shopman.shop.services.order_helpers import get_commitment_date

    janela = window_label((order.data or {}).get("delivery_time_slot")).upper()

    compromisso = get_commitment_date(order)
    if compromisso is None:
        return "SEM AGENDAMENTO", janela

    hoje = timezone.localdate()
    if compromisso == hoje:
        return "HOJE", janela
    if compromisso == hoje + timedelta(days=1):
        return "AMANHÃ", janela
    dia = f"{formats.date_format(compromisso, 'D')}, {formats.date_format(compromisso, 'd/m')}"
    return dia.upper(), janela


def _headline_name(name: str, width: int) -> str:
    """Nome que ainda se lê a três metros: encurta pelo MEIO, nunca pelo fim.

    O corpo duplo cabe ``width`` caracteres. "Maria Aparecida da Silva Xavier"
    cortado no fim vira "Maria Aparecida da Silv" — que é o nome de ninguém.
    Primeiro-e-último ("Maria Xavier") é como a padaria chama a pessoa.
    """
    label = " ".join(str(name or "").split())
    if len(label) <= width:
        return label
    partes = label.split(" ")
    if len(partes) > 1:
        curto = f"{partes[0]} {partes[-1]}"
        if len(curto) <= width:
            return curto
    return label[:width]


def order_ticket(order, *, shop_name: str = "", tracking_url: str = "", reprint: bool = False) -> bytes:
    """Ficha do pedido REMOTO — o papel que vai para o painel físico.

    Irmã do :func:`sale_receipt`, e o parentesco para aí: o recibo é a projeção
    do que já foi VENDIDO e PAGO; a filipeta sai ANTES do pagamento, para
    entrega, retirada ou encomenda agendada. É o papel que a padaria prega no
    painel para enxergar a semana, e por isso ela é desenhada para ser lida de
    longe: dia, janela, nome e recebimento saem em corpo duplo; o resto é corpo.

    ⚠️ **Ela diz o que NÃO é.** Impressa antes do pagamento, um papel com o
    total impresso passa facilmente por comprovante de pagamento — e o cliente
    que a guarda tem toda razão em achar que quitou. Então o papel afirma as
    duas coisas: não é documento fiscal e não comprova pagamento. Quando o
    pedido está em aberto, ele grita isso mais uma vez, emoldurado.

    ``tracking_url`` é o acompanhamento do pedido na loja — e, no pedido de
    link em aberto, é a MESMA página onde se paga. Vazio quando o deployment
    não configurou a base da loja: o papel sai sem QR em vez de com um QR mudo.
    """
    from shopman.utils.monetary import format_money

    from shopman.backstage.presentation.status import payment_method_label, payment_status_label
    from shopman.shop.services import payment as payment_svc
    from shopman.shop.services.order_helpers import get_fulfillment_type

    data = order.data or {}
    out = bytearray()
    out += bytes([ESC, ord("@")])  # reset: não herda estado do job anterior
    out += bytes([ESC, ord("t"), CODE_PAGE])

    out += _centered((shop_name or "NELSON BOULANGERIE").upper())
    # "Ficha do pedido", nunca "comprovante": o papel que diz no rodapé que não
    # comprova pagamento não pode se apresentar como comprovante no topo.
    out += _centered("Ficha do pedido")
    if reprint:
        # Mesma regra do recibo e da DANFE: sem a marca, dois papéis idênticos
        # circulam e a segunda via passa por original. Num painel de parede isso
        # é o pedido aparecendo duas vezes e alguém preparando dobrado.
        out += _centered("*** 2a VIA ***")
    out += _rule()

    # ── O bloco de longe ──────────────────────────────────────────────
    # Quatro linhas em corpo duplo, e não mais: quando tudo é destaque, nada é.
    dia, janela = _commitment_headline(order)
    out += _line("")
    out += _double(dia)
    if janela:
        out += _double(janela)
    is_delivery = get_fulfillment_type(order) == "delivery"
    out += _double("ENTREGA" if is_delivery else "RETIRADA")
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    nome = str(customer.get("name") or "").strip()
    if nome:
        out += _double(_headline_name(nome, COLUMNS // 2))
    out += _line("")
    out += _rule()

    # ── O corpo ───────────────────────────────────────────────────────
    out += _pair(f"Pedido {order.ref}", f"feito {_local(order.created_at)}")
    if nome:
        for pedaco in _wrap(f"Cliente: {nome}", COLUMNS):
            out += _line(pedaco)
    telefone = str(customer.get("phone") or data.get("customer_phone") or "").strip()
    if telefone:
        out += _line(f"Telefone: {telefone}"[:COLUMNS])
    out += _rule()

    if is_delivery:
        endereco, instrucoes = _delivery_lines(data)
        out += _line("ENTREGAR EM:")
        for pedaco in _wrap(endereco or "-", COLUMNS):
            out += _line(pedaco)
        if instrucoes:
            for pedaco in _wrap(f"Referência: {instrucoes}", COLUMNS):
                out += _line(pedaco)
        out += _rule()

    itens = list(order.items.all())
    out += _line(f"ITENS ({len(itens)})")
    for item in itens:
        qty = item.qty.normalize() if hasattr(item.qty, "normalize") else item.qty
        # Quantidade na FRENTE: quem separa a sacola lê "3 x" antes do nome, e
        # o nome longo quebra sem empurrar o número para a linha de baixo.
        #
        # 14 colunas de goteira para o valor, não 12: "R$ 12.345,67" tem 12, e
        # com o nome ocupando o resto o `_pair` cortaria a linha em 48 comendo o
        # último dígito do PREÇO. Encomenda de festa chega nessa casa.
        pedacos = _wrap(f"{qty} x {item.name}", COLUMNS - 14)
        out += _pair(pedacos[0], f"R$ {format_money(int(item.line_total_q or 0))}")
        for pedaco in pedacos[1:]:
            out += _line(f"    {pedaco}"[:COLUMNS])
    out += _rule()

    # As duas notas são de DONOS diferentes (data-schemas) e por isso saem com
    # nome: ``order_notes`` é a voz do cliente no checkout, ``kitchen_note`` é o
    # recado do operador para dentro. Fundi-las apagaria quem pediu o quê.
    nota_cliente = str(data.get("order_notes") or "").strip()
    nota_cozinha = str(data.get("kitchen_note") or "").strip()
    if nota_cliente or nota_cozinha:
        if nota_cliente:
            out += _line("Observação do cliente:")
            for pedaco in _wrap(nota_cliente, COLUMNS):
                out += _line(pedaco)
        if nota_cozinha:
            out += _line("Nota da cozinha:")
            for pedaco in _wrap(nota_cozinha, COLUMNS):
                out += _line(pedaco)
        out += _rule()

    out += _line("")
    out += _double(f"TOTAL R$ {format_money(int(order.total_q or 0))}")
    out += _line("")

    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    metodo = str(payment.get("method") or "")
    if metodo:
        out += _pair("Pagamento", payment_method_label(metodo)[: COLUMNS // 2])
    status = payment_svc.get_payment_status(order) or ""
    pago = status in {"captured", "paid"}
    if pago:
        out += _pair("Situação", payment_status_label(status)[: COLUMNS // 2])
    else:
        out += _line("")
        out += _centered("*** PAGAMENTO PENDENTE ***")
        out += _line("")
    if _charging_at_the_door(order, payment, paid=pago):
        out += _charge_at_the_door_lines(order, payment)
    out += _rule()

    # ⚠️ O que este papel NÃO é. Ele nasce antes do pagamento e traz um total
    # impresso — sem estas duas linhas, é indistinguível de um comprovante.
    out += _centered("Este papel não é documento fiscal")
    out += _centered("e não comprova pagamento.")

    if tracking_url:
        out += _centered("Pague e acompanhe pelo QR" if not pago else "Acompanhe o pedido pelo QR")
        out += _qr(tracking_url)

    out += bytes([ESC, ord("d"), 4])
    out += bytes([GS, ord("V"), 1])  # corte parcial — a filipeta seguinte começa limpa
    return bytes(out)


def _delivery_lines(data: dict) -> tuple[str, str]:
    """Endereço e referência da entrega, do jeito que o Gestor já os monta.

    Mesma regra de ``backstage.projections.order_queue._delivery_address``: o
    complemento é o que faz achar a porta e nem sempre entra no texto formatado
    do Places, então é anexado quando ainda não está lá.
    """
    estruturado = data.get("delivery_address_structured")
    estruturado = estruturado if isinstance(estruturado, dict) else {}
    endereco = str(data.get("delivery_address") or estruturado.get("formatted_address") or "").strip()
    complemento = str(estruturado.get("complement") or "").strip()
    if complemento and complemento.lower() not in endereco.lower():
        endereco = f"{endereco} - {complemento}" if endereco else complemento
    return endereco, str(estruturado.get("delivery_instructions") or "").strip()


def _charging_at_the_door(order, payment: dict, *, paid: bool) -> bool:
    """Esta entrega ainda tem dinheiro para entrar NA PORTA?

    A marca canônica é ``payment.collection == "on_delivery"``
    (``docs/reference/data-schemas.md``), e o carimbo que a encerra é
    ``payment.cod_settled_at`` (``operator_orders.settle_delivery_cash``).
    """
    from shopman.shop.services.order_helpers import get_fulfillment_type

    if get_fulfillment_type(order) != "delivery":
        return False
    return (
        payment.get("collection") == "on_delivery"
        and not paid
        and not payment.get("cod_settled_at")
    )


def _charge_at_the_door_lines(order, payment: dict) -> bytes:
    """Quanto receber na porta e quanto de troco levar — um dono só para o bloco.

    Dois papéis imprimem estas linhas: a ficha que vai para o painel
    (:func:`order_ticket`) e a via que sai na mão de quem entrega
    (:func:`courier_ticket`). Um valor diferente em cada um é o entregador
    cobrando errado na porta do cliente, então a conta se faz aqui, uma vez.
    """
    from shopman.utils.monetary import format_money

    from shopman.backstage.presentation.status import payment_method_label
    from shopman.shop.services.operator_orders import _change_for_q, change_out_suggested_q

    out = bytearray()
    out += _centered("COBRAR NA ENTREGA")
    tenders = payment.get("tenders") or [{"method": payment.get("method") or "", "amount_q": order.total_q}]
    a_receber = [
        tender for tender in tenders
        if tender.get("status") not in {"received", "captured", "paid"}
        and tender.get("collection", "on_delivery") == "on_delivery"
    ]
    for tender in a_receber:
        out += _pair(
            payment_method_label(str(tender.get("method") or "")),
            f"R$ {format_money(int(tender.get('amount_q') or 0))}",
        )
    change_for_q = _change_for_q(order)
    # Quem decide se há troco é a LINHA em espécie, não o método do topo. No
    # pedido do marketplace o método do topo é `external` (o iFood é que
    # precifica e concilia) e a parcela em dinheiro só aparece na linha —
    # perguntar ao topo deixava a comanda do iFood sem "Troco para".
    if any(str(tender.get("method") or "").lower() in {"cash", "mixed"} for tender in a_receber):
        if change_for_q:
            out += _pair("Troco para", f"R$ {format_money(change_for_q)}")
            out += _pair("Levar de troco", f"R$ {format_money(change_out_suggested_q(order))}")
        else:
            out += _line("Troco: não informado; confirmar com cliente")
    return bytes(out)


def courier_ticket(order, *, shop_name: str = "", reprint: bool = False) -> bytes:
    """A VIA DO ENTREGADOR — o papel que sai da casa na mão de quem leva.

    Terceira do trio, e ela existe porque as outras duas são de outra pessoa: o
    recibo é do cliente, a ficha (:func:`order_ticket`) é do painel de parede e
    da cozinha, e as duas carregam nome, telefone e endereço porque quem as lê
    trabalha aqui dentro. Esta sai PELA PORTA, e por isso obedece a uma regra
    que as outras não têm.

    **São duas vias com NOME, não uma via com um ``if`` escondendo o endereço.**
    O nome sai impresso no alto do papel, porque quem confere precisa saber qual
    dos dois documentos está na mão:

    - **Via do entregador — Identificada.** Endereço completo (com complemento e
      referência), telefone, nome do cliente, a observação dele e, quando há
      cobrança na porta, o valor e o troco. É o papel de quem entrega pela casa:
      a transportadora contratada por ela (Taon Delivery/Taxi Machine) não tem
      app nenhum, e o endereço só existe para ela se estiver aqui.
    - **Via do entregador — Anônima.** Só o que identifica o pedido (``ref``,
      ``display_id`` do iFood, código de retirada) e o que confere a sacola. Sem
      endereço, sem telefone, sem nome. É o papel do marketplace: o iFood
      determina, na seção de Impressão do portal do desenvolvedor, que documento
      destinado a parceiro de entrega não traga CPF nem endereço, e o entregador
      dele já tem tudo na tela do app.

    **Quem escolhe é a configuração do canal**, não um ramo cravado aqui:
    ``ChannelConfig.fulfillment.courier_ticket``. A resolução (e o piso que a
    configuração não fura, quando a entrega é de terceiro) tem um dono só,
    ``order_helpers.courier_ticket_variant`` — esta função pergunta e compõe.

    O desenho não é invenção da casa: o guia de impressão do iFood diz que a
    comanda "é essencial para que o entregador (entrega própria) localize o
    endereço do cliente" e, na frase seguinte, proíbe CPF e endereço em
    documento destinado a PARCEIRO de entrega. A regra é sobre o destinatário do
    papel — que é exatamente o que separa a Identificada da Anônima.

    **CPF não sai em nenhuma das duas.** Não há ramo que o imprima; o documento
    do cliente é assunto da NFC-e (:func:`danfe_nfce`), que é papel dele, não de
    quem entrega.

    ⚠️ **Esta via é documento OPERACIONAL, e não um DANFE estendido — e isso é
    fronteira, não preferência.** O Manual de Especificações Técnicas do DANFE
    NFC-e v6.0 proíbe inserir no DANFE informação que não conste do XML, e
    endereço de entrega, código de retirada e conferência de sacola não constam.
    São dois documentos com destinatários diferentes: o DANFE é do cliente e
    acompanha a mercadoria; a via é de quem leva. Por isso ela também estampa,
    em destaque, que não é documento fiscal (ver o rodapé desta função).

    O dinheiro segue a régua da ficha, pelo mesmo
    :func:`_charge_at_the_door_lines`: quando há cobrança na porta, o valor e o
    troco saem; quando não há, o papel afirma que não há — "não cobre nada" é
    informação, e o silêncio no lugar dela é o entregador pedindo dinheiro de um
    pedido já pago.
    """
    from shopman.shop.services import payment as payment_svc
    from shopman.shop.services.order_helpers import (
        COURIER_TICKET_IDENTIFIED,
        courier_ticket_variant,
        delivery_ownership,
        get_fulfillment_type,
        is_test_order,
    )

    data = order.data or {}
    ifood = data.get("ifood") if isinstance(data.get("ifood"), dict) else {}
    is_delivery = get_fulfillment_type(order) == "delivery"
    ownership = delivery_ownership(order)
    variant = courier_ticket_variant(order)
    identificada = variant == COURIER_TICKET_IDENTIFIED

    out = bytearray()
    out += bytes([ESC, ord("@")])  # reset: não herda estado do job anterior
    out += bytes([ESC, ord("t"), CODE_PAGE])

    out += _centered((shop_name or "NELSON BOULANGERIE").upper())
    # O nome da via no alto, e não só no rodapé de quem programou: duas pessoas
    # segurando papéis diferentes precisam saber qual é qual antes de comparar.
    out += _centered("Via do entregador — Identificada" if identificada else "Via do entregador — Anônima")
    if reprint:
        # Mesma regra do recibo e da ficha: sem a marca, dois papéis idênticos
        # circulam e a segunda via passa por original — aqui, duas pessoas
        # saindo para entregar o mesmo pedido.
        out += _centered("*** 2a VIA ***")
    out += _rule()

    # ⚠️ A homologação do iFood roda contra o ambiente VIVO, e o pedido de teste
    # percorre as mesmas telas e o mesmo papel. Se ele pode sair impresso, ele
    # tem de dizer o que é ANTES de qualquer outra coisa: uma via de entregador
    # sem esta moldura é alguém saindo de moto para entregar nada.
    if is_test_order(order):
        out += _centered("*** PEDIDO DE TESTE DO IFOOD ***")
        out += _centered("Não entregue nada.")
        out += _rule()

    # ── Que pedido é este ─────────────────────────────────────────────
    out += _line("")
    out += _double("ENTREGA" if is_delivery else "RETIRADA")
    display_id = str(ifood.get("display_id") or "").strip()
    if display_id:
        # O número curto do iFood é como o entregador e o atendente chamam o
        # pedido entre si; o ``ref`` da casa não aparece na tela dele.
        out += _double(f"iFood #{display_id}")
    out += _line("")
    out += _pair(f"Pedido {order.ref}", f"feito {_local(order.created_at)}")
    pickup_code = str(ifood.get("pickup_code") or "").strip()
    if pickup_code:
        out += _line("Código de retirada no balcão:")
        out += _double(pickup_code)
    out += _rule()

    # ── Para onde vai, e para quem ────────────────────────────────────
    if is_delivery:
        if identificada:
            endereco, instrucoes = _delivery_lines(data)
            out += _line("ENTREGAR EM:")
            for pedaco in _wrap(endereco or "-", COLUMNS):
                out += _line(pedaco)
            if instrucoes:
                for pedaco in _wrap(f"Referência: {instrucoes}", COLUMNS):
                    out += _line(pedaco)
            customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
            nome = str(customer.get("name") or "").strip()
            if nome:
                for pedaco in _wrap(f"Cliente: {nome}", COLUMNS):
                    out += _line(pedaco)
            telefone = str(customer.get("phone") or data.get("customer_phone") or "").strip()
            if telefone:
                out += _line(f"Telefone: {telefone}"[:COLUMNS])
        else:
            # ⚠️ A ausência é DITA. Espaço em branco onde deveria estar o
            # endereço faz o leitor adivinhar se a impressora falhou — e
            # adivinhar é justamente o que a copy desta casa não admite.
            if ownership == "marketplace":
                out += _line("QUEM ENTREGA É O IFOOD.")
            elif ownership == "unknown":
                # Mesmo vocabulário do Gestor (``projections.ifood``), que já
                # recusa o despacho deste pedido (``AdvanceBlock`` —
                # ``IFOOD_DELIVERY_UNKNOWN``). O papel não contradiz a tela.
                for pedaco in _wrap(
                    "O RESPONSÁVEL PELA ENTREGA NÃO FOI INFORMADO PELO IFOOD. "
                    "Confirme com a loja antes de sair.",
                    COLUMNS,
                ):
                    out += _line(pedaco)
            for pedaco in _wrap(
                "Endereço, telefone e nome do cliente estão no app do entregador. "
                "Por privacidade, não saem neste papel.",
                COLUMNS,
            ):
                out += _line(pedaco)
        out += _rule()

    # ── O que vai na sacola ───────────────────────────────────────────
    itens = list(order.items.all())
    # "produtos", não "itens": a contagem é de LINHAS, e a linha de baixo diz
    # "2 x Pão". "1 item" ao lado de "2 x" faz o entregador conferir errado —
    # rótulo que mente é rótulo pior do que rótulo ausente.
    out += _line(f"CONFIRA A SACOLA - {len(itens)} {'produto' if len(itens) == 1 else 'produtos'}")
    for item in itens:
        qty = item.qty.normalize() if hasattr(item.qty, "normalize") else item.qty
        # Sem preço: quem entrega confere quantidade e produto. O que ele
        # precisa saber de dinheiro é só o que vai COBRAR, e isso sai abaixo.
        for pedaco in _wrap(f"{qty} x {item.name}", COLUMNS):
            out += _line(pedaco)
    out += _rule()

    # A observação do cliente é onde mora "deixar na portaria" e "chamar no
    # interfone 2" — informação de entrega. Ela só sai na Identificada, pela
    # mesma razão que o endereço: na Anônima já está no app do entregador, e é
    # voz do cliente.
    if identificada:
        nota_cliente = str(data.get("order_notes") or "").strip()
        if nota_cliente:
            out += _line("Observação do cliente:")
            for pedaco in _wrap(nota_cliente, COLUMNS):
                out += _line(pedaco)
            out += _rule()

    # ── O dinheiro ────────────────────────────────────────────────────
    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    pago = (payment_svc.get_payment_status(order) or "") in {"captured", "paid"}
    if _charging_at_the_door(order, payment, paid=pago):
        out += _charge_at_the_door_lines(order, payment)
    elif pago or payment.get("cod_settled_at"):
        out += _centered("Pedido pago. Não cobre nada na entrega.")
    else:
        for pedaco in _wrap(
            "Pagamento pendente e sem cobrança combinada na porta. "
            "Confirme com a loja antes de entregar.",
            COLUMNS,
        ):
            out += _line(pedaco)
    out += _rule()

    # ⚠️ Exigência LEGAL, não escolha de leiaute: Ajuste SINIEF 19/16, cláusula
    # décima, § 4º (acrescido pelo Ajuste SINIEF 32/24, efeitos desde
    # 01/02/2025; replicado no RICMS/PR art. 31, § 4º — Decreto 9.904 de
    # 12.5.2025). Documento NÃO fiscal relacionado à NFC-e entregue ao
    # consumidor final tem de trazer "NÃO É DOCUMENTO FISCAL" de forma
    # DESTACADA e legível.
    #
    # As DUAS vias estampam, sempre. A via viaja com a sacola, e não existe
    # jeito de garantir que ela não acabe na mão do cliente — condicionar o
    # carimbo a "se chegar ao consumidor" seria apostar no que não se controla.
    #
    # Destaque é o corpo duplo (`_double`), que é como esta casa destaca desde o
    # comprovante de gaveta; não se inventa inversão de vídeo para isto. A frase
    # sai com os acentos da norma porque a CP860 os imprime — 22 caracteres
    # cabem nas 24 colunas do corpo duplo, então não é preciso recorrer à
    # "expressão similar" que a cláusula admite.
    out += _line("")
    out += _double("NÃO É DOCUMENTO FISCAL")
    out += _line("")
    out += _centered("Este papel também não comprova pagamento.")

    out += bytes([ESC, ord("d"), 4])
    out += bytes([GS, ord("V"), 1])  # corte parcial
    return bytes(out)


def danfe_nfce(doc, *, reprint: bool = False) -> bytes:
    """DANFE NFC-e em bobina — a projeção IMPRESSA de ``DanfeDocument``.

    ``doc`` vem de ``shopman.shop.views.fiscal_danfe.build_danfe`` (a MESMA
    projeção do cupom web): um dado, duas superfícies, zero divergência de
    leiaute entre a tela e o papel. Só compõe nota EMITIDA — quem chama guarda.

    O leiaute segue o DANFE NFC-e simplificado: emitente, aviso de homologação
    quando for o caso, itens, totais, chave de acesso em grupos, consumidor e o
    QR da SEFAZ para conferência.
    """
    assert doc.emitted, "danfe_nfce só compõe nota emitida"

    out = bytearray()
    out += bytes([ESC, ord("@")])
    out += bytes([ESC, ord("t"), CODE_PAGE])

    out += _centered((doc.shop_name or "NELSON BOULANGERIE").upper())
    if doc.shop_legal_name:
        out += _centered(doc.shop_legal_name)
    if doc.shop_cnpj:
        out += _centered(f"CNPJ {doc.shop_cnpj}")
    for pedaco in _wrap(doc.shop_address or "", COLUMNS):
        if pedaco != "-":
            out += _centered(pedaco)
    out += _rule()

    out += _centered("DANFE NFC-e")
    out += _centered("Documento Auxiliar da Nota Fiscal")
    out += _centered("de Consumidor Eletronica")
    if reprint:
        out += _centered("*** 2a VIA ***")
    if doc.is_homolog:
        # Exigência da SEFAZ em homologação: o papel diz que não vale.
        out += _rule()
        out += _centered("*** EMITIDA EM HOMOLOGACAO ***")
        out += _centered("*** SEM VALOR FISCAL ***")
    out += _rule()

    out += _pair(f"NFC-e n. {doc.number}", f"Serie {doc.series}")
    out += _line(f"Pedido {doc.order_ref}")
    out += _rule()

    for item in doc.items:
        for pedaco in _wrap(f"{item.seq:>3} {item.name}", COLUMNS):
            out += _line(pedaco)
        out += _pair(f"    {item.qty} {item.unit} x {item.unit_price_display}", item.total_display)
    out += _rule()

    out += _pair("QTD. TOTAL DE ITENS", str(doc.item_count))
    out += _pair("FORMA DE PAGAMENTO", doc.payment_label[: COLUMNS // 2])
    out += _line("")
    out += _double(f"TOTAL {doc.total_display}")
    out += _line("")
    out += _rule()

    out += _centered("Consulte pela Chave de Acesso em")
    for pedaco in _wrap("www.fazenda.pr.gov.br/nfce/consulta", COLUMNS):
        out += _centered(pedaco)
    for pedaco in _wrap(doc.chave_grouped or doc.key, COLUMNS):
        out += _centered(pedaco)
    out += _rule()

    # Quem identifica o consumidor na nota é o CPF, não o nome — e é ele a
    # resposta para "o meu documento entrou?". Nome entra em seguida, e só
    # quando é nome de gente (o apelido interno "Cliente Doc 6789" fica no CRM).
    if doc.customer_tax_id_display:
        out += _line(f"CONSUMIDOR CPF {doc.customer_tax_id_display}"[:COLUMNS])
        if doc.customer_name:
            out += _line(doc.customer_name[:COLUMNS])
    else:
        out += _line("CONSUMIDOR NAO IDENTIFICADO")
    out += _rule()

    out += _centered("Consulta via leitor de QR Code")
    if doc.consult_url:
        out += _qr(doc.consult_url)
    if doc.protocol:
        out += _centered(f"Protocolo {doc.protocol}")

    out += bytes([ESC, ord("d"), 4])
    out += bytes([GS, ord("V"), 1])
    return bytes(out)
