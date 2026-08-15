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


def cash_movement_receipt(movement, *, verify_code: str, verify_url: str, reprint: bool = False) -> bytes:
    """Comprovante de movimento de gaveta (sangria, suprimento, ajuste).

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
    out += _centered(movement.get_movement_type_display().upper())
    if reprint:
        # Sem esta marca, dois papéis idênticos circulam e a segunda via passa
        # por original.
        out += _centered("*** 2a VIA ***")
    out += _rule()

    out += _pair("Valor", f"R$ {format_money(movement.amount_q)}")
    out += _pair("Turno", f"#{movement.shift_id}")
    out += _pair("Operador", movement.created_by or "-")
    if movement.approved_by:
        # A retirada tem duas assinaturas; o papel mostra as duas.
        out += _pair("Autorizado por", movement.approved_by)
    out += _pair("Quando", _local(movement.created_at))
    out += _line("")
    out += _line("Motivo:")
    for pedaco in _wrap(movement.reason or "-", COLUMNS - 2):
        out += _line(f"  {pedaco}")

    out += _rule()
    out += _centered("CONFIRA ESTE COMPROVANTE")
    out += _centered(verify_code)
    out += _line("")
    out += _qr(verify_url)
    out += _line("")
    out += _centered("Sem o codigo, este papel nao vale nada.")

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
    return bytes(
        [GS, 0x28, 0x6B, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00]
        + [GS, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x43, module]
        + [GS, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x45, 0x31]
        + [GS, 0x28, 0x6B, tamanho % 256, tamanho // 256, 0x31, 0x50, 0x30]
    ) + payload + bytes([GS, 0x28, 0x6B, 0x03, 0x00, 0x31, 0x51, 0x30])
