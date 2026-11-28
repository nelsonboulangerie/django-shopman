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
from ._effects import SHARED, known_with, receipt_part

MOVE = "commit_order"
EFFECT = True
TEMPLATES = (TEMPLATES_BY_ID["commit_order.done"], TEMPLATES_BY_ID["commit_order.done_order"], *SHARED)


def propose(state, need):
    if not state.answers_offer(need) or need.need_id in state.refused:
        return None
    from .change_cart import eligible_change

    if eligible_change(state):
        # "Sim, e põe quatro": a sacola muda no mesmo turno, e os termos confirmados deixam de ser os da
        # sacola (v2 4.7, propriedade 2). O "sim" não grava o pedido, seja qual for a ordem das palavras.
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
    # O total pelo pedido lido depois do efeito (``Engine._after_effects``); onde acompanhar, pelo mesmo recibo.
    receipt = state.receipts.get(need.need_id)
    ref = (receipt.domain_refs.get("effect") if receipt is not None else None) or f"none.{need.need_id}"
    track = {"track": ("receipt", receipt.command_id if receipt is not None else f"none.{need.need_id}")}
    if receipt is not None and receipt.status == "success" and not known_with(state, state.order_key(ref), "total"):
        # O pedido existe (recibo), e a leitura dele falhou ou veio sem o total: o degrau de baixo.
        return receipt_part(state, need, MOVE, "commit_order.done_order", "order", also=lambda _: track)
    return receipt_part(state, need, MOVE, "commit_order.done", "order",
                        also=lambda _: {"total": ("fact", state.order_key(ref)), **track})
