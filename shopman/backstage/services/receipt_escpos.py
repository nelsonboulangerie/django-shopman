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
_TRANSLITERACAO = str.maketrans({
    "—": "-", "–": "-", "―": "-",
    "“": '"', "”": '"', "„": '"',
    "‘": "'", "’": "'", "‚": "'",
    "…": "...", "•": "*", "·": "-",
    "€": "EUR", "™": "TM", "→": "->", "≠": "!=", "≤": "<=", "≥": ">=",
    "\u00a0": " ",  # espaço não separável, comum em texto colado
})


def _line(text: str) -> bytes:
    return text.translate(_TRANSLITERACAO).encode(ENCODING, "replace") + b"\n"


def _double(text: str) -> bytes:
    """Uma linha em corpo duplo (largura e altura), centrada.

    `GS ! n`: o nibble alto é a largura, o baixo a altura — `0x11` dobra as
    duas. Volta a `0x00` na mesma função, senão o resto do papel sai gigante:
    o modo é de estado, não de escopo.
    """
    recorte = text[: COLUMNS // 2]
    margem = max(0, (COLUMNS // 2 - len(recorte)) // 2)
    return (
        bytes([GS, ord("!"), 0x11])
        + _line(" " * margem + recorte)
        + bytes([GS, ord("!"), 0x00])
    )


def _centered(text: str) -> bytes:
    recorte = text[:COLUMNS]
    margem = max(0, (COLUMNS - len(recorte)) // 2)
    return _line(" " * margem + recorte)


def _rule() -> bytes:
    return _line("-" * COLUMNS)


def _pair(left: str, right: str) -> bytes:
    espaco = max(1, COLUMNS - len(left) - len(right))
    return _line(f"{left}{' ' * espaco}{right}"[:COLUMNS])


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
    return bytes([ESC, ord("a"), 1]) + bytes(
        [GS, 0x28, 0x6B, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00]
        + [GS, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x43, module]
        + [GS, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x45, 0x31]
        + [GS, 0x28, 0x6B, tamanho % 256, tamanho // 256, 0x31, 0x50, 0x30]
    ) + payload + bytes([GS, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x51, 0x30]) + bytes([ESC, ord("a"), 0])


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
        tender
        for tender in (payment.get("tenders") or [])
        if isinstance(tender, dict) and tender.get("amount_q")
    ]
    if tenders:
        for tender in tenders:
            out += _pair(
                payment_method_label(str(tender.get("method") or ""))[: COLUMNS // 2],
                f"R$ {format_money(int(tender.get('amount_q') or 0))}",
            )
    elif payment.get("method"):
        out += _pair(
            payment_method_label(str(payment.get("method")))[: COLUMNS // 2],
            f"R$ {format_money(int(payment.get('amount_q') or order.total_q or 0))}",
        )
    tendered_q = payment.get("tendered_q")
    change_q = payment.get("change_q")
    if isinstance(tendered_q, int) and tendered_q > 0:
        out += _pair("Recebido", f"R$ {format_money(tendered_q)}")
    if isinstance(change_q, int) and change_q > 0:
        out += _pair("Troco", f"R$ {format_money(change_q)}")
    out += _rule()

    out += _centered("Obrigado pela preferência!")

    out += bytes([ESC, ord("d"), 4])
    out += bytes([GS, ord("V"), 1])  # corte parcial
    return bytes(out)


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
    """Filipeta do pedido REMOTO — o comprovante que vai para o painel físico.

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
    out += _centered("Comprovante de pedido")
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

    if is_delivery:
        endereco, instrucoes = _delivery_lines(data)
        out += _line("ENTREGAR EM:")
        for pedaco in _wrap(endereco or "-", COLUMNS):
            out += _line(pedaco)
        if instrucoes:
            for pedaco in _wrap(f"Referência: {instrucoes}", COLUMNS):
                out += _line(pedaco)
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
