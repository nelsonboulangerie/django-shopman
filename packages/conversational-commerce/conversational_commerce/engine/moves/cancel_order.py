"""Cancelar um pedido (A3, só com a linha do perfil aprovada). No D1, só precondição.

O movimento existe para a política: proposto para o pedido de cancelar, ele é
julgado, e sem a janela de autoatendimento lida da porta de comércio e sem a
confirmação presa ao pedido (campos desconhecidos) fica inelegível. Então se
informa a limitação e se oferece a equipe. Nenhuma jornada do D1 o executa.
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, SlotSpec, Template

MOVE = "cancel_order"
TEMPLATES = (
    Template("cancel_order.done", "1", MOVE, "Your order {order} is cancelled.",
             {"order": SlotSpec(("receipt:success",), "effect")}),
)


def propose(state, need):
    if need.act != "cancel_order":
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                    situation=state.situation(need))


def reply(state, need):
    return PartSpec(MOVE, "cancel_order.done", {"order": ("receipt", f"none.{need.need_id}")})
