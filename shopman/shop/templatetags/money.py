"""Centavos → reais, para as telas Django-renderizadas.

A projection entrega ``price_q`` em centavos de propósito: quem formata é a
superfície. Quando o quadro passou a ser pintado no servidor (para a TV desenhar
sem JavaScript), o Django precisou saber fazer o que o Alpine já fazia no
navegador — e as duas pinturas têm de sair idênticas, senão a troca entre elas
pisca com formatos diferentes.
"""

from __future__ import annotations

from django import template
from shopman.utils.monetary import format_money

register = template.Library()


@register.filter
def brl(value_q) -> str:
    """``1600`` → ``R$ 16,00``. Mesmo formato do ``brl()`` do Alpine."""
    try:
        return f"R$ {format_money(int(value_q or 0))}"
    except (TypeError, ValueError):
        return ""
