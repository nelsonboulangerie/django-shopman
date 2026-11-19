"""Cortesia: saudação, agradecimento, e o "entendi" que fecha uma pergunta respondida."""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, Template

from ..acts import ANSWER_ACTS, COURTESY_ACTS

MOVE = "acknowledge"
TEMPLATES = (
    Template("acknowledge.thanks", "1", MOVE, "Thank you for your message."),
    Template("acknowledge.got_it", "1", MOVE, "Got it, thank you."),
)


def propose(state, need):
    if need.act not in COURTESY_ACTS | ANSWER_ACTS:
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                    situation=state.situation(need, reply_only_courtesy=True))


def reply(state, need):
    template = "acknowledge.got_it" if need.answers_question else "acknowledge.thanks"
    return PartSpec(MOVE, template)
