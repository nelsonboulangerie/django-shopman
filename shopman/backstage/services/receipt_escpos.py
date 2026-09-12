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


def _print_text(text: str) -> str:
    return "".join(ch if ord(ch) >= 32 and ord(ch) != 127 else " " for ch in str(text)).translate(_TRANSLITERACAO)


def _line(text: str) -> bytes:
    return _print_text(text).encode(ENCODING, "replace") + b"\n"


def _double(text: str, columns: int = COLUMNS) -> bytes:
    """Uma linha em corpo duplo (largura e altura), centrada.

    `GS ! n`: o nibble alto é a largura, o baixo a altura — `0x11` dobra as
    duas. Volta a `0x00` na mesma função, senão o resto do papel sai gigante:
    o modo é de estado, não de escopo.
    """
    lines = _wrap(text, columns // 2)
    return (
        bytes([GS, ord("!"), 0x11])
        + b"".join(_line(part.center(columns // 2)) for part in lines)
        + bytes([GS, ord("!"), 0x00])
    )


def _emphasis(text: str, *, tall: bool = False) -> bytes:
    """Negrito; corpo duplo com quebra completa para identificador e cobrança."""
    return (
        bytes([ESC, ord("E"), 1, GS, ord("!"), 0x11 if tall else 0])
        + b"".join(_line(part) for part in _wrap(text, COLUMNS // 2 if tall else COLUMNS))
        + bytes([GS, ord("!"), 0, ESC, ord("E"), 0])
    )


def _centered(text: str, columns: int = COLUMNS) -> bytes:
    recorte = _print_text(text)[:columns]
    margem = max(0, (columns - len(recorte)) // 2)
    return _line(" " * margem + recorte)


def _rule(columns: int = COLUMNS) -> bytes:
    return _line("-" * columns)


def _pair(left: str, right: str, columns: int = COLUMNS) -> bytes:
    left, right = _print_text(left), _print_text(right)
    if len(left) + len(right) + 1 > columns:
        return b"".join(_line(part) for part in _wrap(left, columns)) + b"".join(
            _line(part.rjust(columns)) for part in _wrap(right, columns)
        )
    return _line(f"{left}{' ' * (columns - len(left) - len(right))}{right}")


def _wrap(text: str, width: int) -> list[str]:
    """Quebra por palavra; palavra maior que a linha é cortada, não sumida."""
    linhas: list[str] = []
    atual = ""
    for palavra in _print_text(text).split():
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


def order_ticket(order, *, shop_name: str = "", tracking_url: str = "", reprint: bool = False) -> bytes:
    """Ficha operacional: compromisso, destino, cobrança e conferência em 80 mm.

    Lê o estado canônico de pagamento. Retirada combinada hoje continua uma
    encomenda; somente ``pos.sales_mode=counter`` identifica balcão imediato.
    """
    from shopman.utils.monetary import format_money

    from shopman.backstage.presentation.status import payment_method_label
    from shopman.backstage.services.print_branding import logo_bytes
    from shopman.shop.services import payment as payment_svc
    from shopman.shop.services.order_helpers import get_fulfillment_type

    data = order.data or {}
    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    method = str(payment.get("method") or "")
    status = payment_svc.get_payment_status(order) or ""
    paid = status in {"captured", "paid"}
    is_delivery = get_fulfillment_type(order) == "delivery"
    is_counter = (data.get("pos") or {}).get("sales_mode") == "counter"
    collect = (
        is_delivery
        and payment.get("collection") == "on_delivery"
        and status in {"", "pending", "created"}
        and not payment.get("cod_settled_at")
    )

    def money(value):
        return f"R$ {format_money(int(value or 0))}"

    def method_label(value):
        return "Canal externo" if value == "external" and not paid else payment_method_label(value)

    from shopman.backstage.services.print_layout import bindings

    layout, (_line, _pair, _emphasis, _centered, _rule, _wrap, _qr) = bindings(fiscal=False)
    out = bytearray([ESC, ord("@"), ESC, ord("t"), CODE_PAGE])
    day, window = _commitment_headline(order)
    fulfillment = "BALCÃO IMEDIATO" if is_counter else "ENTREGA" if is_delivery else "RETIRADA"
    commitment = fulfillment if is_counter else " | ".join(part for part in (fulfillment, day, window) if part)
    name = str(customer.get("name") or "").strip()
    phone = str(customer.get("phone") or data.get("customer_phone") or "").strip()
    if layout:
        layout.header(str(order.ref), commitment, name, phone, shop_name, reprint)
    else:
        out += logo_bytes() or _centered((shop_name or "NELSON BOULANGERIE").upper())
        out += _emphasis(f"PEDIDO {order.ref}", tall=True)
        if reprint:
            out += _emphasis("*** 2a VIA ***")
        out += _emphasis(commitment)
        if name and phone:
            out += _pair(name, phone)
        elif name or phone:
            out += _emphasis(name or f"Telefone: {phone}")
    out += _rule()
    if is_delivery:
        if layout:
            layout.delivery_address(data)
        else:
            address, instructions = _delivery_lines(data)
            for part in _wrap(f"ENTREGAR EM: {address or 'confirmar endereço'}", COLUMNS):
                out += _line(part)
            if instructions:
                for part in _wrap(f"Referência: {instructions}", COLUMNS):
                    out += _line(part)
            out += _rule()

    if layout:
        layout.begin_box()
    if paid:
        out += _emphasis("PAGO - NÃO COBRAR")
        out += _pair(method_label(method), money(order.total_q))
    elif collect:
        if not layout:
            out += _emphasis("PAGAMENTO PENDENTE | COBRAR NA ENTREGA")
        tenders = payment.get("tenders") or [{"method": method, "amount_q": order.total_q}]
        pending = [
            t
            for t in tenders
            if isinstance(t, dict)
            and t.get("status") not in {"received", "captured", "paid"}
            and t.get("collection", "on_delivery") == "on_delivery"
        ]
        if layout:
            label = method_label(str(pending[0].get("method") or "")) if len(pending) == 1 else "Pagamento misto"
            out += _emphasis(f"{label.upper()} · COBRAR NA ENTREGA")
        due_q = sum(int(t.get("amount_q") or 0) for t in pending)
        if due_q != int(order.total_q or 0):
            out += _pair("Total do pedido", money(order.total_q))
        cash_only = bool(pending) and all(t.get("method") == "cash" for t in pending)
        if not (layout and cash_only):
            out += _emphasis(f"A COBRAR {money(due_q)}", tall=not cash_only)
        # Um método só divide a linha com o aviso; o valor já está no destaque.
        if len(pending) == 1:
            if not layout:
                out += _line(method_label(str(pending[0].get("method") or "")))
        else:
            for tender in pending:
                tender_label = method_label(str(tender.get("method") or ""))
                if layout and tender.get("method") in {"card", "credit", "debit"}:
                    out += _emphasis(f"{tender_label}: {money(tender.get('amount_q'))}", tall=True)
                else:
                    out += _pair(tender_label, money(tender.get("amount_q")))
        if any(t.get("method") in {"card", "credit", "debit"} for t in pending):
            out += _emphasis("LEVAR MAQUININHA")
        cash_due = sum(int(t.get("amount_q") or 0) for t in pending if t.get("method") == "cash")
        cash_metrics_rendered = False
        if cash_due:
            from shopman.shop.services.operator_orders import _change_for_q

            change_for = _change_for_q(order)
            if change_for:
                out += _emphasis(f"TROCO PARA {money(change_for)}", tall=True)
                if layout and cash_only:
                    layout.cash_metrics(money(max(0, change_for - cash_due)), money(due_q))
                    cash_metrics_rendered = True
                else:
                    out += _pair("Levar de troco", money(max(0, change_for - cash_due)))
            else:
                if layout:
                    out += _emphasis("CONFIRMAR TROCO", tall=True)
                out += _line("Troco: não informado; confirmar com cliente")
        if layout and cash_only and not cash_metrics_rendered:
            out += _pair("Valor a cobrar", money(due_q))
    else:
        out += _emphasis("*** PAGAMENTO PENDENTE ***")
        out += _pair(method_label(method) if method else "Total do pedido", money(order.total_q))
        if status == "unknown":
            out += _emphasis("CONFIRMAR PAGAMENTO ANTES DE COBRAR")
    if layout:
        layout.end_box()
    else:
        out += _rule()
    notes = [("Observação do cliente:", data.get("order_notes")), ("Nota da cozinha:", data.get("kitchen_note"))]
    if layout and any(str(note or "").strip() for _, note in notes):
        layout.begin_box()
    for label, note in notes:
        if str(note or "").strip():
            out += _emphasis(label)
            for part in _wrap(str(note), COLUMNS):
                out += _line(part)
    if any(str(note or "").strip() for _, note in notes):
        if layout:
            layout.end_box()
        else:
            out += _rule()
    items = list(order.items.all())
    out += _emphasis(f"ITENS ({len(items)})")
    for item in items:
        qty = item.qty.normalize() if hasattr(item.qty, "normalize") else item.qty
        parts = _wrap(f"{qty} x {item.name}", COLUMNS - 14)
        out += _pair(parts[0], money(item.line_total_q))
        for part in parts[1:]:
            out += _line(f"    {part}")
    out += _rule()
    out += _line(f"Pedido registrado em {_local(order.created_at)}")
    out += _centered("Este papel não é documento fiscal")
    out += _centered("e não comprova pagamento.")
    if tracking_url:
        out += _centered("Acompanhe o pedido pelo QR" if paid or collect else "Pague e acompanhe pelo QR")
        out += _qr(tracking_url)
    out += bytes([ESC, ord("d"), 4, GS, ord("V"), 1])
    return layout.finish() if layout else bytes(out)


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
    """DANFE NFC-e de 80 mm, exclusivamente a partir do XML autorizado."""
    if not doc.emitted or not doc.source_verified:
        raise ValueError("DANFE exige XML autorizado validado.")
    texts = [
        doc.shop_legal_name,
        doc.shop_name,
        doc.shop_cnpj,
        doc.shop_ie,
        doc.shop_address,
        doc.customer_name,
        doc.customer_address,
        doc.customer_tax_id_display,
        doc.query_url,
    ]
    texts.extend(
        text
        for item in doc.items
        for text in (item.sku, item.name, item.qty, item.unit, item.unit_price_display, item.total_display)
    )
    texts.extend(label for label, _ in doc.payments)
    texts.extend(doc.additional_info)
    try:
        for text in texts:
            text.translate(_TRANSLITERACAO).encode(ENCODING)
    except UnicodeEncodeError as exc:
        raise ValueError(
            "A fonte residente não representa todos os caracteres fiscais. Use o DANFE do provedor."
        ) from exc
    from shopman.backstage.services.print_layout import bindings

    layout, (_line, _pair, _emphasis, _centered, _rule, _wrap, _qr) = bindings(fiscal=True)
    out = bytearray([ESC, ord("@"), ESC, ord("t"), CODE_PAGE])
    from shopman.backstage.services.print_branding import logo_bytes

    emit_id = "CPF" if len(doc.shop_cnpj) == 14 else "CNPJ"
    if layout:
        details = [
            doc.shop_name if doc.shop_name != doc.shop_legal_name else "",
            f"{emit_id} {doc.shop_cnpj}",
            f"IE {doc.shop_ie}" if doc.shop_ie else "",
            doc.shop_address,
        ]
        layout.brand_header(doc.shop_legal_name, details)
    else:
        logo = layout.logo if layout else logo_bytes
        out += logo(centered=False)
        out += _emphasis(doc.shop_legal_name)
        if doc.shop_name and doc.shop_name != doc.shop_legal_name:
            out += _line(doc.shop_name)
        emit_id = "CPF" if len(doc.shop_cnpj) == 14 else "CNPJ"
        out += _line(f"{emit_id} {doc.shop_cnpj}")
        if doc.shop_ie:
            out += _line(f"IE {doc.shop_ie}")
        for part in _wrap(doc.shop_address, COLUMNS):
            out += _line(part)
    out += _centered("DANFE NFC-e")
    out += _centered("Documento Auxiliar da Nota Fiscal")
    out += _centered("de Consumidor Eletrônica")
    if reprint:
        out += _emphasis("*** 2a VIA ***")
    if doc.contingency:
        out += _emphasis("EMITIDA EM CONTINGÊNCIA")
    out += _line("")
    if layout:
        out += _rule()
    out += _emphasis("CÓDIGO / DESCRIÇÃO")
    out += _pair("QTD UN x VALOR UNITÁRIO", "VALOR TOTAL")
    for item in doc.items:
        for part in _wrap(f"{item.sku} {item.name}", COLUMNS):
            out += _line(part)
        out += _pair(f"{item.qty} {item.unit} x {item.unit_price_display}", item.total_display)
    out += _line("")
    if layout:
        out += _rule()
    if layout:
        layout.begin_box()
    out += _pair("QTD. TOTAL DE ITENS", str(doc.item_count))
    for label, amount in doc.totals:
        out += _pair(label, amount)
    out += _emphasis(f"VALOR A PAGAR {doc.total_display}", tall=True)
    out += _pair("FORMA DE PAGAMENTO", "VALOR PAGO")
    for label, amount in doc.payments:
        out += _pair(label, amount)
    if layout:
        layout.end_box()
    out += _line("")
    if layout:
        out += _rule()
    out += _line("Consulte pela Chave de Acesso em")
    for part in _wrap(doc.query_url, COLUMNS):
        out += _line(part)
    for part in _wrap(doc.chave_grouped, COLUMNS):
        out += _line(part)
    if layout:
        out += _rule()
    if doc.customer_tax_id_display:
        for part in _wrap(f"CONSUMIDOR {doc.customer_tax_id_label} {doc.customer_tax_id_display}", COLUMNS):
            out += _line(part)
        for text in (doc.customer_name, doc.customer_address):
            if text:
                for part in _wrap(text, COLUMNS):
                    out += _line(part)
    else:
        out += _line("CONSUMIDOR NÃO IDENTIFICADO")
    out += _pair(f"NFC-e n. {doc.number}", f"Série {doc.series}")
    out += _line(f"Emissão {doc.issued_at}")
    out += _line(f"Protocolo de autorização {doc.protocol}")
    out += _line(doc.authorized_at)
    # Um módulo inteiro por ponto do cabeçote: preserva QR sem interpolação.
    # Matriz >=25 mm (200 dots a 203 dpi), além da zona livre.
    import math

    import qrcode

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(doc.consult_url)
    qr.make(fit=True)
    module = max(4, math.ceil(200 / qr.modules_count))
    if (qr.modules_count + 8) * module > 576:
        raise ValueError("QR fiscal excede a área imprimível de 72 mm.")
    out += _line("")
    out += _qr(doc.consult_url, module=module)
    out += _line("")
    if doc.is_homolog:
        out += _centered("EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO")
        out += _centered("SEM VALOR FISCAL")
    for text in doc.additional_info:
        for part in _wrap(text, COLUMNS):
            out += _line(part)
    out += bytes([ESC, ord("d"), 4, GS, ord("V"), 1])
    return layout.finish() if layout else bytes(out)
