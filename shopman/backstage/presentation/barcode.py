"""Code-128 (subconjunto B) — do texto ao SVG, sem dependência nova.

Por que existe: o crachá do operador é um token que precisa virar código de barras
para o leitor a laser do balcão. Leitor 1D lê linhas, não QR — então QR está fora,
por mais que o `qrcode` já seja dependência do projeto.

Por que à mão em vez de mais um pacote: a tabela do Code-128 é um padrão publicado
(ISO/IEC 15417) e a codificação cabe em algumas dezenas de linhas. Uma dependência
nova custa mais do que isso — e este repositório já apanhou de resolução de deps.

Sempre no subconjunto B, mesmo quando o token é todo numérico (o C seria metade da
largura). É deliberado: largura CONSTANTE por número de caracteres vale mais para um
adesivo de tamanho fixo do que alguns milímetros economizados num token raro.
"""

from __future__ import annotations

# Larguras de barra/espaço por valor do símbolo (0..106), alternando barra→espaço a
# partir da barra. Índices 0..102 são os dados; 103-105 são START A/B/C; 106 é o STOP
# (13 módulos, os outros têm 11). É a tabela do padrão — conferida contra um
# codificador independente no teste, não digitada de memória e aceita no olho.
_PATTERNS: tuple[str, ...] = (
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312",
    "132212", "221213", "221312", "231212", "112232", "122132", "122231", "113222",
    "123122", "123221", "223211", "221132", "221231", "213212", "223112", "312131",
    "311222", "321122", "321221", "312212", "322112", "322211", "212123", "212321",
    "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121",
    "313121", "211331", "231131", "213113", "213311", "213131", "311123", "311321",
    "331121", "312113", "312311", "332111", "314111", "221411", "431111", "111224",
    "111422", "121124", "121421", "141122", "141221", "112214", "112412", "122114",
    "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112",
    "421211", "212141", "214121", "412121", "111143", "111341", "131141", "114113",
    "114311", "411113", "411311", "113141", "114131", "311141", "411131", "211412",
    "211214", "211232", "2331112",
)

_START_B = 104
_STOP = 106

#: Menor e maior caractere que o subconjunto B representa (ASCII imprimível).
_MIN_ORD, _MAX_ORD = 32, 126


class BarcodeError(ValueError):
    """O dado não cabe no Code-128 B."""


def encode_code128_b(data: str) -> str:
    """Sequência de módulos ('1' = barra, '0' = espaço) para ``data``.

    Inclui START B, o dígito verificador (módulo 103) e o STOP — ou seja, é o
    símbolo completo, pronto para virar desenho. Falta só a zona muda, que quem
    desenha adiciona (ver :func:`code128_svg`).
    """
    if not data:
        raise BarcodeError("Código de barras vazio.")
    values: list[int] = []
    for char in data:
        point = ord(char)
        if not (_MIN_ORD <= point <= _MAX_ORD):
            raise BarcodeError(f"Caractere fora do Code-128 B: {char!r}.")
        values.append(point - _MIN_ORD)

    # Verificador: START + soma ponderada pela POSIÇÃO (1-based), módulo 103. É o que
    # deixa o leitor recusar uma leitura suja em vez de devolver o token errado.
    checksum = (_START_B + sum(pos * value for pos, value in enumerate(values, start=1))) % 103

    symbols = [_START_B, *values, checksum, _STOP]
    bits: list[str] = []
    for symbol in symbols:
        # Larguras alternam barra/espaço começando por barra.
        for index, width in enumerate(_PATTERNS[symbol]):
            bits.append(("1" if index % 2 == 0 else "0") * int(width))
    return "".join(bits)


#: Dimensão X padrão (largura da barra mais fina). 0,25mm põe o token de 24 caracteres
#: em ~80mm, que cabe num crachá tamanho cartão (85,6mm) com folga nas bordas. Subir
#: para 0,33mm daria leitura ainda mais fácil, mas passa de 105mm e só cabe em etiqueta
#: grande. O piso do padrão é 0,19mm; abaixo disso leitor a laser começa a errar, e
#: impressora comum não segura o traço.
DEFAULT_MODULE_MM = 0.25


def code128_svg(
    data: str,
    *,
    module_mm: float = DEFAULT_MODULE_MM,
    height_mm: float = 15.0,
    quiet_modules: int = 10,
) -> str:
    """O símbolo como SVG em milímetros, pronto para imprimir.

    ``quiet_modules`` é a zona muda — margem clara obrigatória dos dois lados, e o erro
    de impressão mais comum é comê-la: sem ela o leitor não reconhece onde o código
    começa. 10 módulos é o mínimo do padrão.
    """
    bits = encode_code128_b(data)
    total_modules = len(bits) + 2 * quiet_modules
    width_mm = total_modules * module_mm

    rects: list[str] = []
    index = 0
    while index < len(bits):
        if bits[index] == "0":
            index += 1
            continue
        run = 0
        while index + run < len(bits) and bits[index + run] == "1":
            run += 1
        x = (quiet_modules + index) * module_mm
        rects.append(
            f'<rect x="{x:.4f}" y="0" width="{run * module_mm:.4f}" height="{height_mm:.4f}"/>'
        )
        index += run

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm:.4f}mm" '
        f'height="{height_mm:.4f}mm" viewBox="0 0 {width_mm:.4f} {height_mm:.4f}" '
        f'shape-rendering="crispEdges" role="img" aria-label="Código de barras do crachá">'
        f'<rect x="0" y="0" width="{width_mm:.4f}" height="{height_mm:.4f}" fill="#fff"/>'
        f'<g fill="#000">{"".join(rects)}</g></svg>'
    )


def code128_width_mm(
    data: str, *, module_mm: float = DEFAULT_MODULE_MM, quiet_modules: int = 10
) -> float:
    """Largura total (com zona muda) — para conferir se cabe no adesivo."""
    return (len(encode_code128_b(data)) + 2 * quiet_modules) * module_mm
