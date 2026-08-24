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

    out += _line(f"CONSUMIDOR: {doc.customer_name or 'NAO IDENTIFICADO'}"[:COLUMNS])
    out += _rule()

    out += _centered("Consulta via leitor de QR Code")
    if doc.consult_url:
        out += _qr(doc.consult_url)
    if doc.protocol:
        out += _centered(f"Protocolo {doc.protocol}")

    out += bytes([ESC, ord("d"), 4])
    out += bytes([GS, ord("V"), 1])
    return bytes(out)
