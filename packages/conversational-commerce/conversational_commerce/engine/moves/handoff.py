"""Encaminhar a uma pessoa: revoga a posse da automação e nunca afirma aceite (J3, J5, K20).

Proposto quando o cliente pede uma pessoa. A fila recebe o pedido (``routed``),
e receber não é aceitar: a resposta diz que se pediu, e o que se fará se
ninguém pegar até o prazo de aceite. Com a fila recusando, o compromisso fica
com a automação, monitorado, com a contingência do perfil, e a resposta não diz
que alguém assumiu. O aceite é nominal e chega depois (``Engine.staff_accepted``).
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import SlotSpec, Template

from ..state import CommitmentPlan
from ._commitments import commitment_ref

MOVE = "handoff"
COMMITS = True
PROMISE = ("commitment:promise",)
TEMPLATES = (
    Template("handoff.routed", "1", MOVE,
             "I've asked our {owner} to take over. If no one picks this up by {deadline}, I'll let you know.",
             {"owner": SlotSpec(PROMISE, "owner"), "deadline": SlotSpec(PROMISE, "at")}),
    Template("handoff.routed_no_deadline", "1", MOVE,
             "I've asked our {owner} to take over. They'll pick this up as soon as they can.",
             {"owner": SlotSpec(PROMISE, "owner")}),
    # A fila recusou: ninguém assumiu, e nada diz que assumiu (K20).
    Template("handoff.not_accepted", "1", MOVE,
             "I've asked the team to take over. Until someone does, I'll keep this open and update you by {deadline}.",
             {"deadline": SlotSpec(PROMISE, "at")}),
)


def propose(state, need):
    if need.act != "request_human" or need.need_id in state.refused:
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                    situation=state.situation(need, handoff_reason="customer_request"))


def commitment(state, need) -> CommitmentPlan:
    return CommitmentPlan(type="promise", obligation="a person takes over the conversation",
                          criterion="a person accepts the conversation, by name", operation="ask", window="accept",
                          question="take over the conversation", handoff=True)


def reply(state, need):
    from conversational_commerce.reply import PartSpec

    ref = commitment_ref(state, need)
    if ref is None or ref not in state.commitments:
        return PartSpec(MOVE, "handoff.routed", {"owner": ("commitment", f"none.{need.need_id}"),
                                                 "deadline": ("commitment", f"none.{need.need_id}")})
    if not state.routed.get(ref, True):
        return PartSpec(MOVE, "handoff.not_accepted", {"deadline": ("commitment", ref)})
    if state.commitments[ref].deadline.status != "set":
        return PartSpec(MOVE, "handoff.routed_no_deadline", {"owner": ("commitment", ref)})
    return PartSpec(MOVE, "handoff.routed", {"owner": ("commitment", ref), "deadline": ("commitment", ref)})
