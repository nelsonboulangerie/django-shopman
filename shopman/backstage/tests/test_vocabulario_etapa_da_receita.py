"""A unidade do modo de fazer de uma receita se chama **etapa**. "Passo" não é o nome dela.

Decisão do dono em 01/10/2026. A colisão estava viva: o modelo e o Admin diziam
"Etapas" (``Recipe.steps``, ``RecipeVersion.steps``, o campo do Admin do Craftsman) e
as telas de receita do app de Produção diziam "Passos" ("Passos", "Passos lidos",
"Passos (um por linha)"), e o evento de fornada ``step_advanced`` aparecia no Admin
como "Passo avançado". Mesma coisa, dois nomes, a depender da porta por onde se
entrava. Ver ``docs/reference/suite-vocabulary.md``, Produção.

## O que a trava recusa, e o que ela deixa passar

"Passo" é palavra legítima do português, e a casa a usa para outra coisa: o passo do
login, o "próximo passo" de uma instrução, o passo a passo da instalação do agente do
balcão. Nada disso é etapa de receita, e uma trava que recusasse a palavra no
repositório inteiro obrigaria a reescrever frases certas.

Por isso o escopo é duplo, e estreito de propósito:

  * **por ARQUIVO** — só onde mora o conceito de etapa de receita ou de produção: o
    pacote ``craftsman`` (fora migração, que é história, e teste) e os arquivos do
    backstage cujo nome diz ``recipe`` ou ``production``;
  * **por CANAL** — só literal de string que não é docstring. É o que chega a alguém:
    rótulo de choice, mensagem de validação, texto do prompt da leitura automática.
    Comentário e docstring ficam livres, porque "o passo seguinte é o sistema aprender
    a perda" (``conf.py``) diz a verdade e não fala de etapa.

A irmã dela nas telas Nuxt é a terceira regra de
``surfaces/operator-kit/tests/guardrails.vocabulary.test.ts``, sobre o
``production-nuxt`` inteiro.

A trava recusa; não escreve a substituição. "passo" é masculino e "etapa" é feminina:
"o passo de mesmo nome" vira "a etapa de mesmo nome", e "um por linha" vira "uma por
linha". Quem troca lê a linha.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

#: A palavra, nas duas caixas e no plural; "passou", "passagem" e "compasso" não casam.
BANNED = re.compile(r"\bpassos?\b", re.IGNORECASE)

CRAFTSMAN = REPO / "packages" / "craftsman" / "shopman" / "craftsman"
BACKSTAGE = REPO / "shopman" / "backstage"


def _sources() -> list[Path]:
    files = [
        path for path in sorted(CRAFTSMAN.rglob("*.py")) if "migrations" not in path.parts and "tests" not in path.parts
    ]
    files += [
        path
        for path in sorted(BACKSTAGE.rglob("*.py"))
        if "migrations" not in path.parts
        and "tests" not in path.parts
        and ("recipe" in path.name or "production" in path.name)
    ]
    return files


SOURCES = _sources()


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def offenders(source: str) -> list[str]:
    """Literais de string (fora docstring) que dizem "passo" ou "passos"."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    return [
        f"linha {node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and BANNED.search(node.value)
    ]


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.relative_to(REPO).as_posix())
def test_a_etapa_da_receita_se_chama_etapa(path: Path) -> None:
    found = offenders(path.read_text(encoding="utf-8"))
    assert found == [], (
        f"{path.relative_to(REPO)}: a unidade do modo de fazer é 'etapa' (decisão do dono, "
        f"01/10/2026), não 'passo'. Leia a linha e acerte o gênero: {found}"
    )


def test_a_trava_le_o_que_diz_ler() -> None:
    """Varredura que não varre nada passa sempre; esta tem de ver o Craftsman e as telas."""
    names = {path.name for path in SOURCES}
    assert {"work_order_event.py", "recipe_steps.py", "recipe_capture.py"} <= names
    assert len(SOURCES) > 40, f"a varredura achou só {len(SOURCES)} arquivos"


def test_a_trava_reprova_o_rotulo_e_deixa_a_prosa() -> None:
    """A régua da própria trava: rótulo reprova; docstring, comentário e 'passou' passam."""
    reprova = 'class K:\n    STEP = "step", _("Passo avançado")\n'
    passa = '"""O passo seguinte é aprender a perda."""\n# o passo a passo do agente\nx = "já passou da hora"\n'
    assert offenders(reprova) != []
    assert offenders(passa) == []
