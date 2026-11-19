"""Abrir o caso da reclamação, com dono e prazo, e suspender o comércio no episódio (J5, K19).

O caso é um compromisso do tipo ``case``: o código do problema, a solução pedida
(se o cliente a disse) e o dono na equipe. A família ``protect_and_fulfill``
vence as outras, e a política suspende toda iniciativa comercial no episódio
enquanto ele vence (``suspended_by_open_problem``). A dúvida que veio na mesma
mensagem é outra necessidade, e segue respondida.
"""

from __future__ import annotations

from conversational_commerce.ledger import staff_owner
from conversational_commerce.policy import Proposal
from conversational_commerce.reply import SlotSpec, Template

from ..state import CommitmentPlan
from ._commitments import commitment_part

MOVE = "open_case"
COMMITS = True
TEMPLATES = (
    Template("open_case.opened", "1", MOVE,
             "I'm sorry about this. Our {owner} will look into it and get back to you by {deadline}.",
             {"owner": SlotSpec(("commitment:case",), "owner"), "deadline": SlotSpec(("commitment:case",), "at")}),
    Template("open_case.no_deadline", "1", MOVE,
             "I'm sorry about this. Our {owner} will look into it as soon as they can.",
             {"owner": SlotSpec(("commitment:case",), "owner")}),
)


def propose(state, need):
    if need.act != "complain" or need.need_id in state.refused:
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                    situation=state.situation(need, complaint=True,
                                              staff_owner_possible=staff_owner(state.profile, "open_or_update")
                                              is not None))


def commitment(state, need) -> CommitmentPlan:
    fields = need.readings[0]
    return CommitmentPlan(type="case", obligation="look into the customer's complaint and answer",
                          criterion="the team's resolution delivered to the customer", operation="open_or_update",
                          window="respond", problem_code=fields.get("problem") or "complaint",
                          requested_resolution=fields.get("resolution"))


def reply(state, need):
    return commitment_part(state, need, MOVE, with_deadline=("open_case.opened", ("owner", "deadline")),
                           without_deadline=("open_case.no_deadline", ("owner",)))
