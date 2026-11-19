"""Recomendar pela necessidade explícita: o primeiro movimento comercial, sob a restrição de conselheiro (J6).

Só quando o cliente pede e diz o que precisa (``need_explicit``), e só o item que
atende cada exigência declarada (``advisor_constraint``, v2 4.3, substituto (i)):
aceite da oferta não é medida, e exigência desconhecida no item é não atendida.
Fica inelegível com problema aberto, atrito alto ou compromisso vencido, e com a
recusa do cliente guardada na memória declarada, até ele mudar de ideia
(``refusal_respected``). A família ``commerce`` cede a todas as outras.

O preço e o nome saem do fato lido do item, nunca do texto do modelo.
"""

from __future__ import annotations

from collections.abc import Mapping

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import SlotSpec, Template

MOVE = "recommend"
TEMPLATES = (
    Template("recommend.item", "1", MOVE, "For that, I'd suggest {name} at {price}.",
             {"name": SlotSpec(("fact",), "name"), "price": SlotSpec(("fact",))}),
)


def declared_need(need) -> dict:
    declared = need.readings[0].get("need") if need.readings else None
    return dict(declared) if isinstance(declared, Mapping) else {}


def propose(state, need):
    if need.act != "ask_recommendation" or need.need_id in state.refused:
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"item": state.recommendations.get(need.need_id)},
                    situation=state.situation(
                        need, need_explicit=bool(declared_need(need)),
                        advisor_constraint_satisfied=need.need_id in state.recommendations,
                        unsolicited_initiatives_in_episode=0, open_problem=state.open_problem,
                        friction_high=state.friction == "high", overdue_commitment=state.overdue_commitment,
                        customer_declined_offers=state.declined_offers))


def reply(state, need):
    from conversational_commerce.reply import PartSpec

    key = f"item.{state.recommendations.get(need.need_id, 'none')}"
    return PartSpec(MOVE, "recommend.item", {"name": ("fact", key), "price": ("fact", key)})
