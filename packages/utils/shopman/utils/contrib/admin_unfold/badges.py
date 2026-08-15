"""Badges do Admin — fachada fina sobre o helper canônico do Unfold.

Estas funções reconstruíam o markup do badge à mão, com a tabela de cores copiada
do Unfold. Copiar classes é o anti-padrão que a política do projeto nomeia: a
cópia não acompanha upgrade do pacote, perde o que o helper oficial oferece
(ícone, link, tamanho, `title`) e faz o Admin envelhecer em pedaços — um badge
igual ao Unfold de 2025 e o resto do Admin no Unfold de hoje.

Agora quem desenha é `unfold/helpers/label.html`. O que sobra aqui é a tradução
do vocabulário de cor usado nos admins (verde, vermelho, azul) para o vocabulário
semântico do Unfold (success, danger, info) — e é bom que essa tradução exista num
lugar só, porque é ela que mantém "cor por significado" consistente entre telas.
"""

from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import mark_safe

# Cor concreta → intenção do Unfold. O Unfold pensa em significado, não em tinta.
_VARIANT_BY_COLOR = {
    "base": "",
    "red": "danger",
    "green": "success",
    "yellow": "warning",
    "orange": "warning",
    "blue": "info",
    "primary": "primary",
}


def _render(text, color: str) -> str:
    """⚠️ Sem Unfold instalado, badge vira texto simples e escapado.

    O Unfold é sugerido, não obrigatório: num Django Admin puro o template não
    existe, e um badge que explode seria pior que um badge sem cor.
    """
    try:
        return mark_safe(
            render_to_string(
                "unfold/helpers/label.html",
                {"text": text, "variant": _VARIANT_BY_COLOR.get(color, "")},
            ).strip()
        )
    except TemplateDoesNotExist:
        return format_html("<span>{}</span>", text)


def unfold_badge(text, color="base"):
    """Badge de status."""
    return _render(text, color)


def unfold_badge_numeric(text, color="base"):
    """Badge de valor numérico.

    Era uma variante só para tirar a caixa alta — distinção que nunca existiu na
    tela, porque caixa alta em dígito e em sinal não muda pixel nenhum. Segue
    existindo como nome, porque ele diz ao leitor do admin que ali vai número, e
    porque trocar as chamadas nos pacotes não compraria nada.
    """
    return _render(text, color)
