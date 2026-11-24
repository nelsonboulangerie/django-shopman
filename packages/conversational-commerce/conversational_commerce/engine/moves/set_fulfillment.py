"""Definir o recebimento: dia, retirada ou entrega, e a hora (A2, reversível).

Espelha ``change_cart``. Proposto para o ato ``choose_fulfillment`` com uma
leitura só e o carrinho do sujeito; a concessão vem da linha do perfil (sem
termos: a mudança é reversível e não fecha nada, mas invalida os termos já
cotados, porque o alvo muda de versão).

A leitura traz qualquer subconjunto de ``date`` (``AAAA-MM-DD``), ``mode``
(``pickup`` ou ``delivery``) e ``time`` (``HH:MM``). O que foi dito se aplica; o que não foi dito não se
inventa: o comando leva só os campos presentes, e o executor guarda o resto como
estava. Dia ou hora relativos ("amanhã", "mais tarde") não são absolutos: quem
lê (modelo ou adaptador) resolve contra o relógio confiável antes, ou a ação fica
inelegível (``relative_fulfillment``), como a quantidade relativa no carrinho.

A resposta sai do recibo: o executor devolve em ``domain_refs`` o recebimento
do alvo DEPOIS do efeito (``date``, ``mode``, ``time``, os que estiverem
definidos, e a ``window`` que a casa dá ao dia quando não há hora), e o molde
escolhido é o mais completo que o recibo sustenta. A casa formata os valores pelos formatadores dos espaços (a data na
língua dela, o rótulo da janela a partir da referência).
"""

from __future__ import annotations

import re
from datetime import date as calendar_date

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import TEMPLATES_BY_ID, PartSpec

from ..acts import FULFILLMENT_FIELDS, FULFILLMENT_MODES
from ..state import EffectPlan
from ._effects import FAILED, PENDING, SHARED, commitment_id

MOVE = "set_fulfillment"
ACT = "choose_fulfillment"
#: As condições do fechamento que este movimento cumpre: a resposta a elas é o ato dele (ADR-051).
FULFILLS_CONDITIONS: tuple[str, ...] = ("fulfillment_date", "fulfillment_type", "delivery_time_slot", "delivery_window")
EFFECT = True
# Do mais completo ao mais genérico: o primeiro cujos espaços o recibo preenche todos.
REPLY_TEMPLATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("set_fulfillment.done", ("mode", "date", "window")),
    ("set_fulfillment.done_time", ("mode", "date", "time")),
    ("set_fulfillment.done_day", ("mode", "date")),
    ("set_fulfillment.done_date", ("date",)),
    ("set_fulfillment.done_mode", ("mode",)),
)
FALLBACK_TEMPLATE = "set_fulfillment.updated"
TEMPLATES = (*(TEMPLATES_BY_ID[template_id] for template_id, _ in REPLY_TEMPLATES),
             TEMPLATES_BY_ID[FALLBACK_TEMPLATE], *SHARED)

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CLOCK_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def said(fields) -> dict[str, str]:
    """Os campos de recebimento que a leitura traz, sem os vazios."""
    return {name: fields[name] for name in FULFILLMENT_FIELDS if fields.get(name) not in (None, "")}


def is_absolute(fields) -> bool:
    """Tudo o que foi dito está em forma absoluta: data ISO real, hora HH:MM, modo da lista."""
    if fields.get("relative", False):
        return False
    values = said(fields)
    if not all(isinstance(value, str) for value in values.values()):
        return False
    if "date" in values:
        if not ISO_DATE.match(values["date"]):
            return False
        try:
            calendar_date.fromisoformat(values["date"])
        except ValueError:
            return False
    if "time" in values and not CLOCK_TIME.match(values["time"]):
        return False
    if "mode" in values and values["mode"] not in FULFILLMENT_MODES:
        return False
    return True


def propose(state, need):
    if need.act != ACT or len(need.readings) != 1 or state.subject.cart_ref is None \
            or need.need_id in state.refused:
        return None
    fields = need.readings[0]
    values = said(fields)
    if not values:
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content=values,
                    situation=state.situation(need, fulfillment_is_absolute=is_absolute(fields),
                                              change_reversible=True))


def effect(state, need) -> EffectPlan:
    return EffectPlan(action=MOVE, target=state.subject.cart_ref, parameters=said(need.readings[0]),
                      expected_versions={}, basis="line")


def reply(state, need):
    receipt = state.receipts.get(need.need_id)
    if receipt is None:
        # Sem recibo neste turno (sombra): o espaço aponta um recibo que não existe e a verificação segura.
        return PartSpec(MOVE, FALLBACK_TEMPLATE, {"noted": ("receipt", f"none.{need.need_id}")})
    if receipt.status == "failure":
        return PartSpec("inform_limitation", FAILED.template_id)
    if receipt.status != "success":
        return PartSpec("wait", PENDING.template_id, {"deadline": ("commitment", commitment_id(receipt.command_id))})
    present = set(receipt.domain_refs)
    for template_id, slots in REPLY_TEMPLATES:
        if set(slots) <= present:
            return PartSpec(MOVE, template_id, dict.fromkeys(slots, ("receipt", receipt.command_id)))
    return PartSpec(MOVE, FALLBACK_TEMPLATE, {"noted": ("receipt", receipt.command_id)})
