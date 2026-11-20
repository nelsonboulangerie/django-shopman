"""A porta do "vou verificar" da Concierge para quem opera (WP-05).

A equipe responde, ou assume a conversa, no cartão ``concierge_verify`` do sino do
Gestor. Quem faz é a Concierge (``shopman/storefront/concierge/verification.py``), que
fala com o cliente; quem recebe o clique é o backstage. Pela regra de dependência,
nenhum dos dois importa o outro: o storefront registra as duas funções aqui na
subida (``StorefrontConfig.ready``), e o backstage chama por aqui.
"""

from __future__ import annotations

import re
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


#: O tipo do cartão no sino (``OperatorAlert.type``).
ALERT_TYPE = "concierge_verify"


def card_subject(name: str) -> str:
    """O título do cartão: quem espera, e o quê ("Ana espera a resposta da equipe").

    Só o primeiro nome; sem nome, "Cliente". Lido pela projeção do sino e pela Concierge.
    """
    first = (name or "").strip().split(" ")[0]
    return f"{first or 'Cliente'} espera a resposta da equipe"


def card_subjects(alert_pks) -> dict[int, str]:
    """O título de cada cartão de verificação, pelo nome da conversa dele."""
    from shopman.shop.models import Conversation

    pks = [int(pk) for pk in alert_pks]
    if not pks:
        return {}
    names = {
        int((flags or {}).get("verification", {}).get("alert_pk") or 0): name
        for name, flags in Conversation.objects.filter(flags__verification__alert_pk__in=pks).values_list(
            "customer_name", "flags"
        )
    }
    return {pk: card_subject(names.get(pk, "")) for pk in pks}


Answer = Callable[..., DeskResult]
TakeOver = Callable[..., DeskResult]

_handlers: dict[str, Callable[..., DeskResult]] = {}


def register(*, answer: Answer, take_over: TakeOver, promote_faq: Callable[..., DeskResult] | None = None) -> None:
    _handlers["answer"] = answer
    _handlers["take_over"] = take_over
    if promote_faq is not None:
        _handlers["promote_faq"] = promote_faq


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


def promote_faq(alert_pk: int, *, actor: str) -> DeskResult:
    """A verificação respondida vira rascunho de pergunta frequente, não publicado (WP-15).

    ``detail`` é a referência do rascunho; ``sent_text``, o aviso de data quando há.
    """
    handler = _handlers.get("promote_faq")
    if handler is None:
        return DeskResult(False, "unavailable")
    return handler(alert_pk, actor=actor)


# ── Pergunta frequente promovida (WP-15): de onde veio, e o aviso de data ─────

#: Prefixo da referência do rascunho (``FAQEntry.ref``): diz de onde ele veio.
FAQ_REF_PREFIX = "concierge-"


#: Resposta "do dia" não vira pergunta frequente sem conferência: o rascunho avisa.
_DATED = re.compile(
    r"\b(hoje|amanh[ãa]|ontem|depois de amanh[ãa]|esta semana|essa semana|semana que vem|"
    r"segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo|"
    r"janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)\b"
    r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
    re.IGNORECASE,
)
DATED_WARNING = "A resposta cita um dia ou uma data: confira se ela vale sempre antes de publicar."


def faq_ref(conversation_pk: int, record_id: str) -> str:
    return f"{FAQ_REF_PREFIX}{int(conversation_pk)}-{record_id}"[:96]


def origin_of(ref: str) -> tuple[int, str] | None:
    """(conversa, verificação) de um rascunho promovido, ou ``None``."""
    match = re.fullmatch(rf"{re.escape(FAQ_REF_PREFIX)}(\d+)-([0-9a-f]+)", str(ref or ""))
    return (int(match.group(1)), match.group(2)) if match else None


def cites_a_date(text: str) -> bool:
    return bool(_DATED.search(str(text or "")))
