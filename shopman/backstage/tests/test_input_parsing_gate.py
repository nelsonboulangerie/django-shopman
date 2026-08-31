"""Gate: entrada de API de operador não é interpretada por `bool()` cru.

``bool("false")`` é ``True``. Um cliente que mande ``{"checked": "false"}`` no KDS
marcava o item em vez de desmarcar, e nada avisava. O mesmo `bool()` cru aparecia em
nove arquivos, com a mesma consequência em cada um.

Nenhum desses é explorável pelo operador com a UI de hoje, que manda JSON de verdade.
Todos são explotáveis por quem fala com a API direto, e todos viram bug real no dia em
que alguém trocar um ``fetch`` por ``URLSearchParams`` ou plugar uma integração.

``shopman/backstage/parsing.py`` é o parser canônico. Este teste é o que impede a
volta: a camada de API está em ZERO, e o que sobra está nomeado abaixo, com dono e
prazo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]  # shopman/backstage/

# `bool(request.…)`, `bool(payload.…)`, `bool(data.get(…))` e parentes.
BOOL_CRU = re.compile(r"\bbool\(\s*(request|payload|data|body|params)\b")
# Os dois `_as_int` duplicados morreram no mesmo PR — que não voltem por cópia.
HELPER_DUPLICADO = re.compile(r"^def _as_(bool|int)\b", re.MULTILINE)

#: Dívida NOMEADA, com o WP que a resolve. Esta lista só pode ENCOLHER.
#:
#: A camada de SERVIÇO fica de fora por desenho, não por preguiça: ela já tem
#: dialeto de entrada próprio (`_as_nullable_int`, `_as_str_list`) que levanta
#: `CatalogError`, e `services/exceptions.py` documenta que a camada HTTP mapeia
#: por TIPO. Enfiar um parser que levanta `ValidationError` do DRF lá dentro
#: quebraria essa camada para consertar um `bool()`. Cai junto com o WP de cada
#: serviço.
DIVIDA = {
    # ✅ `api/operations.py` saiu da lista na Onda 2: o `force` de produção — o que
    # CONTORNA a checagem de insumos — e o `close_source_when_empty` passaram a usar
    # `parsing.as_bool`. A camada de API está em ZERO.
    # ✅ `services/catalog.py` chegou a ZERO: a camada ganhou `_as_flag`, no dialeto
    # dela (levanta `CatalogError`, como `_as_nullable_int` e `_as_str_list` ao lado).
    # O teto fica em 0 para a catraca continuar valendo — acrescentar reprova.
    "services/catalog.py": (0, "zerado; mantido em 0 para a catraca não afrouxar"),
    "services/purchase.py": (1, "WP-06 Compras — mesma razão do catálogo"),
}


def _ocorrencias() -> dict[str, int]:
    achados: dict[str, int] = {}
    for path in sorted(_ROOT.rglob("*.py")):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        n = len(BOOL_CRU.findall(path.read_text(encoding="utf-8")))
        if n:
            achados[str(path.relative_to(_ROOT))] = n
    return achados


def test_a_camada_de_api_nao_tem_mais_bool_cru() -> None:
    """Fora do `operations.py` (Onda 2), a API não interpreta entrada com `bool()`."""
    sobrando = {
        arquivo: n
        for arquivo, n in _ocorrencias().items()
        if arquivo.startswith("api/") and arquivo not in DIVIDA
    }
    assert not sobrando, (
        "`bool()` cru em entrada de API: "
        + "; ".join(f"{a} ({n}x)" for a, n in sorted(sobrando.items()))
        + ". Use `as_bool`/`as_int` de `shopman/backstage/parsing.py` — eles falham "
        "com 400 e `field` em vez de adivinhar."
    )


@pytest.mark.parametrize("arquivo", sorted(DIVIDA))
def test_a_divida_nomeada_nao_cresce(arquivo: str) -> None:
    """Cada arquivo da lista tem um teto. Passar do teto reprova; abaixar é bem-vindo."""
    teto, dono = DIVIDA[arquivo]
    atual = _ocorrencias().get(arquivo, 0)
    assert atual <= teto, (
        f"{arquivo}: {atual} ocorrências de `bool()` cru, acima do teto {teto} "
        f"({dono}). Não acrescente — migre para `parsing.as_bool`."
    )


def test_a_lista_de_divida_nao_guarda_entrada_morta() -> None:
    """Teto que ninguém mais atinge vira folclore — e esconde o progresso real."""
    achados = _ocorrencias()
    resolvidos = {a: teto for a, (teto, _) in DIVIDA.items() if achados.get(a, 0) < teto}
    assert not resolvidos, (
        "estes arquivos ficaram ABAIXO do teto — ótimo: baixe o teto em DIVIDA para a "
        f"lista não mentir sobre o tamanho do que falta: { {a: (achados.get(a, 0), t) for a, t in resolvidos.items()} }"
    )


def test_o_parser_mora_num_lugar_so() -> None:
    """Os dois `_as_int` duplicados morreram. Que não voltem por cópia."""
    copias = [
        str(path.relative_to(_ROOT))
        for path in sorted(_ROOT.rglob("*.py"))
        if "tests" not in path.parts
        and path.name != "parsing.py"
        and HELPER_DUPLICADO.search(path.read_text(encoding="utf-8"))
    ]
    assert not copias, (
        f"parser de entrada copiado em {copias}. O canônico é "
        "`shopman/backstage/parsing.py` — importe de lá."
    )
