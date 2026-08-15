"""Renderizar componentes do Unfold a partir de código Python.

Nos templates, um componente se chama com `{% component "unfold/..." %}`. Mas
metade do Admin desenha em Python — `@display`, campos readonly, tabelas de
dashboard — e ali não há template para chamar a tag. A saída fácil era copiar as
classes do componente para dentro de uma f-string, e foi o que aconteceu: um
botão com nove classes decalcadas do `button.html`, badges com a tabela de cores
do Unfold escrita à mão.

O problema da cópia não é feiura, é prazo de validade. Ela congela o Unfold do
dia em que foi escrita: quando o pacote muda um espaçamento ou uma cor, o Admin
passa a exibir duas gerações de design lado a lado, e ninguém sabe dizer qual
está errado.

Este helper fecha a saída fácil: o componente é o mesmo arquivo que o template
usaria, com o mesmo contexto.

    _unfold_component("unfold/components/button.html", children="Salvar",
                      variant="primary", attrs={"x-on:click": "salvar()"})

`children` é o conteúdo entre as tags. `class` é palavra reservada em Python,
então vai por `**{"class": ...}`.
"""

from django.template.loader import render_to_string
from django.utils.safestring import mark_safe


def unfold_component(template: str, *, children: str = "", **context) -> str:
    """Renderiza um componente do Unfold com o mesmo contexto que a tag passaria."""
    return mark_safe(
        render_to_string(template, {"children": mark_safe(children), **context}).strip()
    )
