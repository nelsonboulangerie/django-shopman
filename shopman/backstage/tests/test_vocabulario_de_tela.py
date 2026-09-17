"""A palavra da casa para o objeto que o operador segura é "dispositivo".

O dono já tinha padronizado, mas a regra não estava escrita em lugar nenhum — nem no
glossário, nem no CLAUDE.md. Por isso derivou: 104 arquivos Python diziam "aparelho",
e o convite de instalação dos oito apps, escrito em 17/09/2026, nasceu dizendo "deste
aparelho" porque quem o escreveu leu os vizinhos.

Regra sem trava é lembrete. Esta é a trava, e ela varre STRING — o texto que chega a
alguém —, não prosa: comentário e docstring seguem livres, porque a regra é sobre a
palavra na tela.

Três recortes deliberados:

  * **Storefront fica de fora**, por concessão explícita do dono (05/2026, e de novo
    em 17/09/2026): é superfície de cliente final, com voz própria. Inclui o
    `omotenashi/copy.py`, que é a copy da loja.
  * **"maquininha" não é "dispositivo".** O que o entregador leva tem nome, e o código
    já o usava na frase ao lado ("Maquininha inválida. Atualize os aparelhos
    disponíveis." dizia as duas coisas na mesma linha). A varredura recusa "aparelho"
    e não força "dispositivo" no lugar: quem escreve escolhe a palavra certa.
  * **Teste e migração ficam de fora.** Migração aplicada é história; reescrevê-la não
    muda nada no banco e quebra o hash do grafo.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

# A palavra proibida em texto de tela, nas duas caixas e no plural.
BANNED = "aparelh"

ROOTS = ("shopman/shop", "shopman/backstage", "packages")

# Superfície de cliente final: voz própria, por concessão do dono.
EXEMPT = (
    "shopman/storefront/",
    "shopman/shop/omotenashi/",
)


def _sources() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        for path in sorted((REPO / root).rglob("*.py")):
            parts = path.parts
            if "tests" in parts or "migrations" in parts or "build" in parts:
                continue
            relative = path.relative_to(REPO).as_posix()
            if any(relative.startswith(prefix) for prefix in EXEMPT):
                continue
            files.append(path)
    return files


def _screen_strings(path: Path) -> list[tuple[int, str]]:
    """Literais de string do arquivo, sem docstring — docstring é prosa, não tela."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


SOURCES = _sources()


@pytest.mark.parametrize(
    "path", SOURCES, ids=lambda p: p.relative_to(REPO).as_posix()
)
def test_screen_text_says_dispositivo(path: Path) -> None:
    offenders = [
        f"linha {lineno}: {value!r}"
        for lineno, value in _screen_strings(path)
        if BANNED in value.lower()
    ]
    assert offenders == [], (
        f"{path.relative_to(REPO)}: a palavra da casa é 'dispositivo' (ou 'maquininha', "
        f"quando é a maquininha de cartão): {offenders}"
    )


def test_the_sweep_actually_reads_something() -> None:
    """Varredura que não varre nada passa sempre; esta tem de ver o repositório."""
    assert len(SOURCES) > 200, f"a varredura achou só {len(SOURCES)} arquivos"
