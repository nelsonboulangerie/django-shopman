"""A janela combinada do pedido — o encontro entre o expediente e a fornada.

Duas perguntas moram aqui, e as duas precisam da MESMA resposta em toda
superfície:

1. *Quais janelas eu posso oferecer para o dia X, com este carrinho?* → ``annotate``
2. *Esta janela que chegou no payload pode ser aceita?* → ``validate``

O expediente vem de ``business_calendar.delivery_slots_for`` (as meias horas que
o dia comporta). A prontidão vem de ``product_readiness`` (a que horas cada SKU
fica pronto). Uma janela só é oferecível quando **começa** depois de tudo estar
pronto: prometer 11:30 para um pão que sai às 12h é quebrar contrato na porta, e
o cliente que chega às 11:30 tem razão.

## Por que anotar em vez de filtrar

A janela impossível **aparece**, desabilitada, com o motivo em português de
balcão: *"A Baguette de Tradition sai às 12:00."* Sumir com ela deixa o operador
sem resposta para a pergunta que o cliente faz ("e às 9h não dá?"), e ele acaba
prometendo por fora do sistema.

## O que fecha a porta, e o que não fecha

``validate`` recusa **só** o eixo da prontidão — o único em que a casa promete
algo que não pode cumprir. A grade do expediente molda o que se OFERECE
(``annotate``), não o que se aceita: transformá-la em recusa faria a dona no
balcão às 18h05 não conseguir agendar a retirada de amanhã, e faria uma loja com
``opening_hours`` em branco recusar toda venda com horário. Ver a docstring de
``validate``.

E o silêncio não vira restrição: SKU sem prontidão conhecida (nem declarada, nem
observada) não segura nada — não há o que prometer errado sobre uma hora que
ninguém sabe. É a declaração (``Product.metadata["ready_from"]``) que existe
justamente para tirar produto desse limbo.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time

logger = logging.getLogger(__name__)


def _window_start(ref: str) -> time | None:
    """Hora de início de um ref ``"14:00-14:30"``.

    O ref é o próprio par de horas (ver ``business_calendar.delivery_slots_for``),
    então ele se lê sozinho — inclusive num pedido antigo, depois de a casa mudar
    o expediente.
    """
    from shopman.shop.services.product_readiness import parse_clock

    return parse_clock(str(ref or "").split("-")[0])


def readiness_for(skus: list[str]) -> tuple[time | None, str, str]:
    """``(hora, sku, nome)`` do item que segura o pedido — ou ``(None, "", "")``.

    O nome vem junto porque o motivo tem que falar do PRODUTO. "BF sai às 12:00"
    manda o operador abrir o Admin com o cliente na frente.
    """
    from shopman.shop.services import product_readiness

    ready_at, sku = product_readiness.bottleneck(skus)
    if ready_at is None:
        return None, "", ""
    name = product_readiness.product_names([sku]).get(sku, sku)
    return ready_at, sku, name


def annotate(
    day: date,
    skus: list[str] | None = None,
    *,
    now: datetime | None = None,
    shop=None,
) -> dict:
    """As janelas de ``day``, anotadas para este carrinho.

    Devolve::

        {
            "windows": [{"ref", "label", "enabled", "reason"}, …],
            "earliest_ref": "12:00-12:30",   # a primeira oferecível, ou ""
            "ready_at": "12:00",             # a prontidão que manda, ou ""
            "bottleneck_sku": "BF",
            "bottleneck_name": "Baguette de Tradition",
        }

    ``windows`` vazio significa "não há expediente neste dia" — fechado, feriado,
    ou (para hoje) o expediente já acabou. Todas as janelas desabilitadas com
    motivo de preparo significa outra coisa bem diferente: **há** expediente, mas
    este carrinho não cabe neste dia. Quem consome precisa saber distinguir os
    dois para dizer a frase certa.
    """
    from shopman.shop.services import business_calendar
    from shopman.shop.services.product_readiness import format_clock

    raw = business_calendar.delivery_slots_for(day, now=now, shop=shop)
    ready_at, sku, name = readiness_for(list(skus or []))

    windows: list[dict] = []
    earliest_ref = ""
    for slot in raw:
        ref = str(slot.get("ref") or "")
        start = _window_start(ref)
        enabled = True
        reason = ""
        if ready_at is not None and start is not None and start < ready_at:
            enabled = False
            reason = f"{name} sai às {format_clock(ready_at)}."
        if enabled and not earliest_ref:
            earliest_ref = ref
        windows.append({**slot, "enabled": enabled, "reason": reason})

    return {
        "windows": windows,
        "earliest_ref": earliest_ref,
        "ready_at": format_clock(ready_at),
        "bottleneck_sku": sku,
        "bottleneck_name": name,
    }


def validate(
    day: date,
    window_ref: str,
    skus: list[str] | None = None,
    *,
    now: datetime | None = None,
    shop=None,
) -> str | None:
    """Erro em português de balcão, ou ``None`` quando a janela pode ser aceita.

    ## Dois eixos, e só um deles fecha a porta

    **Prontidão fecha.** Prometer 09:00 para um pão que sai às 12:00 é quebra de
    contrato com quem aparece às 9h. Não há gesto do operador que conserte isso
    depois, então a recusa é no commit e vale para toda superfície.

    **O expediente NÃO fecha.** A grade de meias horas do ``business_calendar``
    existe para dizer o que a casa OFERECE — a antecedência mínima, o
    fechamento, o dia sem escala. Transformá-la em recusa aqui é outra coisa: a
    dona no balcão às 18h05 combinando a retirada de amanhã, o operador acertando
    uma hora fora da grade com um cliente conhecido, e — pior — uma loja com
    ``opening_hours`` em branco, onde a grade é vazia e TODA venda com horário
    seria recusada. Nenhum desses é promessa quebrada; são a casa exercendo a
    própria agenda no próprio balcão.

    Janela em branco passa: "a combinar" é resposta legítima, e exigir hora aqui
    inventaria uma fricção que a casa não tem. Ref em formato livre ("manhã")
    também passa — sem eixo de hora não há o que conferir.
    """
    ref = str(window_ref or "").strip()
    if not ref:
        return None
    start = _window_start(ref)
    if start is None:
        return None

    ready_at, _sku, name = readiness_for(list(skus or []))
    if ready_at is None or start >= ready_at:
        return None

    from shopman.shop.services.product_readiness import format_clock

    erro = f"{name} sai às {format_clock(ready_at)}."
    context = annotate(day, skus, now=now, shop=shop)
    earliest = context.get("earliest_ref")
    if earliest:
        label = next(
            (w.get("label") for w in context["windows"] if w.get("ref") == earliest), earliest
        )
        return f"{erro} Escolha {label} ou mais tarde."
    return f"{erro} Escolha outra data."
