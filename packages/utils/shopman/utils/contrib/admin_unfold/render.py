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

from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe


def unfold_component(
    template: str, *, children: str = "", fallback: str = "", **context
) -> str:
    """Renderiza um componente do Unfold com o mesmo contexto que a tag passaria.

    ⚠️ O Unfold é sugerido, não obrigatório: estes pacotes precisam rodar num
    Django Admin puro. Quando o template não existe, o componente não pode
    explodir — devolve o `fallback`, que é HTML simples e correto, sem classe
    nenhuma do Unfold (classe de um tema ausente seria pior que estilo nenhum).
    """
    try:
        return mark_safe(
            render_to_string(template, {"children": mark_safe(children), **context}).strip()
        )
    except TemplateDoesNotExist:
        return mark_safe(fallback or children)


def unfold_link(href: str, text: str, *, icon: str = "", new_tab: bool = False, **context) -> str:
    """Um link do Admin, desenhado pelo `link.html` do Unfold.

    Existia como `<a class="font-medium underline underline-offset-4">` repetido
    em sete lugares, cada um com a sua combinação de classes: dois sublinhados
    diferentes, duas cores de primário. Link é a coisa mais comum de um Admin, e
    era a menos consistente.
    """
    target = ' target="_blank" rel="noopener"' if new_tab else ""
    return unfold_component(
        "unfold/components/link.html",
        children=text,
        href=href,
        icon=icon,
        external=new_tab,
        fallback=format_html("<a href=\"{}\"{}>{}</a>", href, mark_safe(target), text),
        **context,
    )
