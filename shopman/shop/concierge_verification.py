"""A porta do "vou verificar" da Concierge para quem opera (WP-05).

A equipe responde, ou assume a conversa, no cartão ``concierge_verify`` do sino do
Gestor. Quem faz é a Concierge (``shopman/storefront/concierge/verification.py``), que
fala com o cliente; quem recebe o clique é o backstage. Pela regra de dependência,
nenhum dos dois importa o outro: o storefront registra as duas funções aqui na
subida (``StorefrontConfig.ready``), e o backstage chama por aqui.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DeskResult:
    """O desfecho do gesto, para o cartão dizer o que houve.

    ``code`` vazio é sucesso. Os outros: ``not_found`` (cartão sem verificação),
    ``not_open`` (já respondida ou assumida), ``with_team`` (a conversa já está com a
    equipe), ``empty_answer``, ``answer_too_long``, ``house_rule_held`` (a resposta
    quebra uma regra da casa; ``detail`` diz qual), ``not_sent`` (o envio não foi
    aceito; ``detail`` traz o código do transporte, ex. ``window_closed``) e
    ``unavailable`` (a Concierge não está nesta instalação).
    """

    ok: bool
    code: str = ""
    detail: str = ""
    #: O texto que saiu (ou sairia) ao cliente, depois das regras de forma.
    sent_text: str = ""


Answer = Callable[..., DeskResult]
TakeOver = Callable[..., DeskResult]

_handlers: dict[str, Callable[..., DeskResult]] = {}


def register(*, answer: Answer, take_over: TakeOver) -> None:
    _handlers["answer"] = answer
    _handlers["take_over"] = take_over


def answer(alert_pk: int, text: str, *, actor: str) -> DeskResult:
    """A resposta da equipe volta ao cliente pela Concierge."""
    handler = _handlers.get("answer")
    if handler is None:
        return DeskResult(False, "unavailable")
    return handler(alert_pk, text, actor=actor)


def take_over(alert_pk: int, *, actor: str) -> DeskResult:
    """Alguém da equipe assume a conversa: ela sai da Concierge."""
    handler = _handlers.get("take_over")
    if handler is None:
        return DeskResult(False, "unavailable")
    return handler(alert_pk, actor=actor)
