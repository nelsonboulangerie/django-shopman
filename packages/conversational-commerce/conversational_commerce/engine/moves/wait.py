"""Dar notícia de uma espera: o compromisso aberto, o prazo e o dono (J3, K22).

Não responde a pedido nenhum do cliente: o núcleo o usa quando um prazo vence
(``Engine.tick``), sobre o compromisso aberto da necessidade (``state.waiting``).
A espera tem condição de retomada, responsável e prazo, ou não se diz.
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import SlotSpec, Template

from ._commitments import commitment_part

MOVE = "wait"
ANY = ("commitment:promise", "commitment:case")
TEMPLATES = (
    Template("wait.overdue", "1", MOVE, "Sorry for the wait. You'll hear back from our {owner} by {deadline}.",
             {"owner": SlotSpec(ANY, "owner"), "deadline": SlotSpec(ANY, "at")}),
    Template("wait.overdue_no_deadline", "1", MOVE,
             "Sorry for the wait. Our {owner} will get back to you as soon as they can.",
             {"owner": SlotSpec(ANY, "owner")}),
)


def propose(state, need):
    ref = state.waiting.get(need.need_id)
    if ref is None:
        return None
    commitment = state.commitments.get(ref)
    defined = commitment is not None and bool(commitment.owner)
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"commitment": ref},
                    situation=state.situation(need, wait_has_condition_owner_deadline=defined))


def reply(state, need):
    return commitment_part(state, need, MOVE, with_deadline=("wait.overdue", ("owner", "deadline")),
                           without_deadline=("wait.overdue_no_deadline", ("owner",)))
