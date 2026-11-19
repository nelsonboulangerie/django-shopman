"""Fechar o pedido: concessão presa ao hash vigente, confirmação posterior, época vigente (A3).

Proposto só para o "sim" que responde à pergunta dos termos, na mesma época de
posse. As precondições leem o que o núcleo conferiu da confirmação
(``authority.confirmation_problem``); a conferência que vale é a da guarda, no
ponto de efeito. Recusado lá, este movimento não é proposto de novo no turno:
termos novos pedem confirmação nova.
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import TEMPLATES_BY_ID

from ..state import EffectPlan
from ._effects import SHARED, receipt_part

MOVE = "commit_order"
EFFECT = True
TEMPLATES = (TEMPLATES_BY_ID["commit_order.done"], *SHARED)


def propose(state, need):
    if not state.answers_offer(need) or need.need_id in state.refused:
        return None
    offer = state.offer
    problem = state.confirmation_problems.get(need.need_id)
    situation = state.situation(
        need,
        identity="anonymous" if problem == "identity_insufficient" else state.identity,
        event_assurance="none" if problem == "event_identity_unstable" else state.event_assurance,
        current_terms_hash=offer.terms_hash,
        grant_terms_hash=None if problem == "terms_expired" else offer.terms_hash,
        confirmation_after_terms=problem != "confirmation_before_terms",
        confirmation_same_subject=problem not in ("confirmation_from_other_subject", "object_forbidden"),
        ownership_epoch_current=problem != "authority_revoked",
    )
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"terms": offer.terms_hash}, situation=situation)


def effect(state, need) -> EffectPlan:
    offer = state.offer
    return EffectPlan(action=MOVE, target=offer.target, parameters={},
                      expected_versions={offer.target: offer.terms_version}, basis="confirmation")


def reply(state, need):
    return receipt_part(state, need, MOVE, "commit_order.done", "order")
