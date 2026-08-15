"""HTML escrito dentro de métodos ``@display`` também é Admin (WP-ADM-R8).

Três frentes de canonicidade já têm varredura: templates (o gate), widgets de
formulário (`test_admin_widget_canonicity`) e badges (o helper compartilhado). A
quarta era a que ninguém olhava, e é a maior: metade do Admin desenha em Python —
colunas de changelist, campos readonly, tabelas de dashboard — onde não existe a
tag ``{% component %}`` para chamar, e a saída fácil sempre foi escrever HTML na
mão dentro de uma f-string.

O que esta varredura recusa é o que a política já recusa nos templates, só que do
lado do Python:

- **badge reconstruído**: `<span class="rounded-default bg-...">` em vez de
  `unfold_badge`/`unfold/helpers/label.html`;
- **botão e link crus**: em vez de `unfold_component("unfold/components/...")`;
- **classe do Admin legado do Django** (`vTextField`, `button`, `submit-row`),
  que dentro do Unfold aparece com a cara de outro sistema;
- **`style=` fixo**: cor, tamanho ou espaçamento escritos à mão.

E o que ela ACEITA, porque nenhuma primitiva resolve: `style=` cujo valor é dado
que só existe em tempo de execução (a cor de marca que a pessoa escolheu, a fonte
que o navegador vai baixar) e os bindings do Alpine. Esses são declarados um a um
na lista de exceções abaixo, com motivo — exceção sem nome vira porta aberta.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

#: Módulos que desenham Admin fora do registro (páginas custom e dashboard).
_EXTRA_MODULES = (
    "shopman/backstage/admin_console",
    "shopman/backstage/admin/dashboard.py",
    # Desenho compartilhado: um link errado aqui sai errado em toda tela.
    "packages/utils/shopman/utils/contrib/admin_unfold",
)

#: Exceções nomeadas: `arquivo::motivo`. Valor dinâmico que classe não expressa.
_ALLOWED_INLINE_STYLE = {
    "shopman/shop/admin/shop.py": (
        "swatch da paleta pinta o hex de marca escolhido pela pessoa, e a altura "
        "mínima do iframe é min(70vh,640px) — cálculo que classe nenhuma expressa"
    ),
    "shopman/shop/admin/widgets.py": (
        "x-bind:style do Alpine com a fonte escolhida em tempo de execução"
    ),
}

_BADGE_SHELL = re.compile(r"<span[^>]*class=[\"'][^\"']*(?:rounded-default|bg-(?:red|green|blue|orange|base)-\d)")
_RAW_CONTROL = re.compile(r"<(?:button|a)\b[^>]*class=[\"']", re.IGNORECASE)
_LEGACY_DJANGO = re.compile(r"\b(?:vTextField|vLargeTextField|submit-row|default\s+btn|\bbtn\b)")
_STATIC_STYLE = re.compile(r"""\bstyle=["'][^"']""")


def _python_files():
    """Os arquivos que DESENHAM o Admin deste deployment.

    Derivado do registro, não de um glob: `packages/*/shopman/*/admin.py` são os
    admins simples, que existem para quem instala o pacote SEM o Unfold. Ali
    escrever classe do Unfold seria o erro oposto. O que vale auditar é o que o
    `admin.site` realmente usa, mais as páginas custom.
    """
    from django.contrib import admin

    files = set()
    for model_admin in admin.site._registry.values():
        module = type(model_admin).__module__
        spec = pathlib.Path(*module.split("."))
        for base in (_REPO_ROOT, _REPO_ROOT / "packages"):
            for candidate in base.glob(f"*/{spec}.py"):
                files.add(candidate)
            direct = base / f"{spec}.py"
            if direct.exists():
                files.add(direct)

    for extra in _EXTRA_MODULES:
        path = _REPO_ROOT / extra
        if path.is_dir():
            files.update(path.rglob("*.py"))
        elif path.exists():
            files.add(path)

    return sorted(f for f in files if "test" not in f.name)


def _string_literals(path: pathlib.Path):
    """Só as STRINGS do módulo: comentário e docstring não viram HTML.

    Ler o arquivo cru acusaria a própria explicação de por que algo é proibido —
    aconteceu com o gate, que leu a palavra `input` num comentário meu.
    """
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                yield node.lineno, node.value


def _offenders(path: pathlib.Path) -> list[str]:
    rel = str(path.relative_to(_REPO_ROOT))
    found = []
    for lineno, text in _string_literals(path):
        if _BADGE_SHELL.search(text):
            found.append(f"{rel}:{lineno} badge reconstruído (use unfold_badge)")
        if _RAW_CONTROL.search(text):
            found.append(
                f"{rel}:{lineno} botão/link cru "
                "(use unfold_component('unfold/components/button.html'|'link.html'))"
            )
        if _LEGACY_DJANGO.search(text):
            found.append(f"{rel}:{lineno} classe do Admin legado do Django")
        if _STATIC_STYLE.search(text) and rel not in _ALLOWED_INLINE_STYLE:
            found.append(f"{rel}:{lineno} style= fixo (use classe/componente Unfold)")
    return found


_FILES = _python_files()


@pytest.mark.parametrize("path", _FILES, ids=lambda p: str(p.relative_to(_REPO_ROOT)))
def test_admin_python_draws_with_unfold_primitives(path):
    offenders = _offenders(path)

    assert not offenders, "HTML não canônico em @display/campo readonly:\n  " + "\n  ".join(
        offenders
    )


def test_the_scan_actually_reads_admin_code():
    """Guarda da guarda: varredura que não lê nada passa verde e não protege nada."""
    assert len(_FILES) > 15, f"a varredura só achou {len(_FILES)} arquivos de admin"

    planted = _REPO_ROOT / "shopman/shop/admin/shop.py"
    assert planted in _FILES, "o admin da loja precisa estar no alcance da varredura"


def test_every_declared_exception_still_exists():
    """Exceção que aponta para arquivo inexistente é entulho que esconde regra."""
    missing = [rel for rel in _ALLOWED_INLINE_STYLE if not (_REPO_ROOT / rel).exists()]

    assert not missing, f"exceções apontando para arquivo que não existe: {missing}"
