"""Verificar com a equipe o fato que o sistema não tem, e devolver a resposta depois (J3).

Proposto para a consulta cujo fato a fonte não tem (``not_found``,
``not_supported``). A fonte fora do ar (``source_failed``) não é fato que falta:
é limitação, e a casa não incomoda a equipe com o que volta sozinho (J1).

Cria uma promessa com dono (a fila do perfil) e prazo (o de responder da fila),
ou sem prazo com motivo e contingência. Sem dono possível, a promessa não é
feita, e a limitação é dita no lugar (N04).
"""

from __future__ import annotations

from conversational_commerce.contracts import Unknown
from conversational_commerce.ledger import staff_owner
from conversational_commerce.policy import Proposal
from conversational_commerce.reply import TEMPLATES_BY_ID, SlotSpec, Template

from ..state import CommitmentPlan
from ._commitments import commitment_part

MOVE = "verify_with_staff"
COMMITS = True
# O fato que a fonte não tem. ``source_failed`` e ``stale`` voltam sozinhos: não são pergunta para a equipe.
VERIFIABLE = frozenset({"not_found", "not_supported"})
TEMPLATES = (
    TEMPLATES_BY_ID["verify_with_staff.promise"],
    Template("verify_with_staff.no_deadline", "1", MOVE, "I'll check with our {owner} and answer as soon as they can.",
             {"owner": SlotSpec(("commitment:promise",), "owner")}),
)


def missing_fact(state, need) -> bool:
    keys = state.fact_keys_for(need)
    return bool(keys) and any(isinstance(state.facts.get(key), Unknown) and state.facts[key].reason in VERIFIABLE
                              for key in keys)


def propose(state, need):
    if not need.is_query or len(need.readings) != 1 or need.need_id in state.refused or not missing_fact(state, need):
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"facts": list(state.fact_keys_for(need))},
                    situation=state.situation(need, staff_owner_possible=staff_owner(state.profile, "ask") is not None))


def commitment(state, need) -> CommitmentPlan:
    keys = ", ".join(state.fact_keys_for(need))
    return CommitmentPlan(type="promise", obligation=f"answer the customer's question ({need.act}: {keys})",
                          criterion="the team's answer delivered to the customer", operation="ask",
                          window="respond", question=f"{need.act}: {keys}")


def reply(state, need):
    return commitment_part(state, need, MOVE, with_deadline=("verify_with_staff.promise", ("deadline",)),
                           without_deadline=("verify_with_staff.no_deadline", ("owner",)))
