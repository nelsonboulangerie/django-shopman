"""Apresentar os termos: cotar pela porta e mostrar o total, com lastro (A1).

Proposto para o pedido de fechar (``place_order``) e para a confirmação que não
valeu mais (termos que mudaram ou venceram, concessão vencida, confirmação
anterior aos termos): termos novos, confirmação nova (K07). Só com termos
cotados neste turno; o total entra por espaço travado, vindo da cotação.
Escolhido, o episódio vai a ``waiting_authorization`` e a pergunta que pede a
confirmação fica no ar, presa ao hash dos termos (``authority.Offer``).
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, SlotSpec, Template

MOVE = "present_terms"
TEMPLATES = (
    Template("present_terms.confirm", "1", MOVE, "Your total is {total}. Shall I place the order?",
             {"total": SlotSpec(("fact",), "total")}),
    Template("present_terms.changed", "1", MOVE,
             "The terms changed before I could place the order. The new total is {total}. Shall I place it?",
             {"total": SlotSpec(("fact",), "total")}),
)


def propose(state, need):
    target = state.subject.cart_ref
    if target is None or target not in state.terms or not state.wants_terms(need):
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"terms": state.terms[target].hash}, situation=state.situation(need))


def reply(state, need):
    # "Os termos mudaram" só quando o ponto de efeito recusou; termos vencidos ou "sim" fora de ordem: termos de novo.
    template = "present_terms.changed" if need.need_id in state.refused else "present_terms.confirm"
    return PartSpec(MOVE, template, {"total": ("fact", state.terms_key(state.subject.cart_ref))})
