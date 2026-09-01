"""Defesa contra injeção de fórmula em planilha (CSV/XLSX).

Uma célula de texto que começa com ``=``, ``@`` ou caractere de controle — ou
com ``+``/``-`` sem formar um número puro — vira fórmula ATIVA quando o gestor
abre o arquivo no Excel/Google Sheets: o clique dispara o que o dado disser.
O prefixo ``'`` força a planilha a tratar o conteúdo como texto.

O par ``escape_cell``/``unescape_cell`` é uma bijeção: exportar → editar na
planilha → importar devolve exatamente o texto original, inclusive quando o
dado já começava com ``'``. Exportações só-escrita (relatórios) usam apenas
``escape_cell``; o cofre de backup usa o par completo no round-trip.
"""

from __future__ import annotations

import re
from decimal import Decimal

#: Primeiro caractere que faz Excel/Sheets tratar o texto como fórmula ativa.
_FORMULA_CHARS = ("=", "@", "\t", "\r", "\n")

#: Forma simples de número, com decimal por ponto ou vírgula (pt-BR).
_PLAIN_NUMBER_RE = re.compile(r"^[+-]?\d+([.,]\d+)?$")


def is_plain_number(text: str) -> bool:
    """``-10``/``+3``/``-1,5`` são NÚMERO na planilha, não fórmula.

    Aceita a forma simples com decimal por ponto ou vírgula (pt-BR) e qualquer
    literal que o ``Decimal`` reconheça como finito (``-1e5``, ``-.5``).
    """
    if _PLAIN_NUMBER_RE.match(text):
        return True
    try:
        return Decimal(text).is_finite()
    except (ArithmeticError, ValueError):
        return False


def needs_escape(text: str) -> bool:
    """Texto que uma planilha interpretaria como fórmula, não como dado.

    ``+``/``-`` só são perigosos quando NÃO formam um número puro: "-10" é o
    número -10 em qualquer planilha; "-2+cmd()" é fórmula. Escapar o número
    sujaria a célula sem ganhar nada.
    """
    if not text:
        return False
    if text[0] in _FORMULA_CHARS:
        return True
    return text[0] in "+-" and not is_plain_number(text)


def _dangerous_after_quotes(text: str) -> bool:
    """Removidas TODAS as aspas iniciais, o resto viraria fórmula?

    É a pergunta que os dois lados da bijeção fazem: quantas aspas há na
    frente não importa — ``'=x``, ``''=x``, ``'''=x`` são todos "aspas +
    perigo" e precisam do mesmo tratamento, senão o par escape/unescape
    deixa de ser inverso a partir do segundo nível.
    """
    return needs_escape(text.lstrip("'"))


def escape_cell(text: str) -> str:
    """Prefixa ``'`` no que viraria fórmula ao abrir no Sheets/Excel.

    Sem isto, um texto começando com ``=`` executa ao abrir a planilha E —
    pior, num ciclo de import — volta como o VALOR COMPUTADO, corrompendo o
    dado. Também escapa qualquer quantidade de ``'`` seguida de texto
    perigoso: escapar sempre que ``unescape_cell`` removeria uma aspa é o
    que mantém o par bijetivo em todos os níveis.
    """
    if _dangerous_after_quotes(text):
        return "'" + text
    return text


def unescape_cell(text: str) -> str:
    if text.startswith("'") and _dangerous_after_quotes(text):
        return text[1:]
    return text
