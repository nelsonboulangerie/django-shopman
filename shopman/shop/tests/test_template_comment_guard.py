"""Trava: comentário `{# #}` do Django vale para UMA linha só.

Um `{#` que só fecha numa linha seguinte não é comentário: o motor de template
imprime o texto literal na tela. Foi assim que a nota do desenvolvedor apareceu no
topo do Dashboard, no crachá impresso e no corpo da DANFE (beta test 05/11/2026,
ADM-03). Comentário de várias linhas é `{% comment %}...{% endcomment %}`.
"""

from __future__ import annotations

from pathlib import Path

from django.template import Context, Template

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOTS = (REPO_ROOT / "shopman", REPO_ROOT / "packages", REPO_ROOT / "config")
TEMPLATE_SUFFIXES = {".html", ".txt", ".xml"}


def _template_files():
    for root in TEMPLATE_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in TEMPLATE_SUFFIXES or not path.is_file():
                continue
            if "templates" not in path.parts or "node_modules" in path.parts:
                continue
            yield path


def test_comentario_de_template_nao_atravessa_linhas():
    offenders = []
    for path in _template_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            # Cada `{#` da linha precisa do seu `#}` na mesma linha.
            rest = line
            while "{#" in rest:
                rest = rest[rest.index("{#") + 2 :]
                if "#}" not in rest:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
                    break
                rest = rest[rest.index("#}") + 2 :]
    assert not offenders, (
        "Comentário {# #} de várias linhas aparece na tela. Use "
        "{% comment %}...{% endcomment %}:\n" + "\n".join(offenders)
    )


def test_a_regra_que_a_trava_protege_e_do_django():
    """Se o Django um dia aceitar `{#` multilinha, esta trava pode ser revista."""
    rendered = Template("antes {# nota\n do dev #} depois").render(Context())
    assert "nota" in rendered
