"""Cortesia: saudação, agradecimento, e o "entendi" que fecha uma pergunta respondida."""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, Template

from ..acts import ANSWER_ACTS, COURTESY_ACTS, DECLARATION_ACTS

MOVE = "acknowledge"
TEMPLATES = (
    Template("acknowledge.thanks", "1", MOVE, "Thank you for your message."),
    Template("acknowledge.got_it", "1", MOVE, "Got it, thank you."),
    Template("acknowledge.declined_offers", "1", MOVE, "Understood. I won't make suggestions."),
    Template("acknowledge.accepted_offers", "1", MOVE, "Understood. I'll suggest things again when it helps."),
)


def propose(state, need):
    if need.act not in COURTESY_ACTS | ANSWER_ACTS | DECLARATION_ACTS or state.answers_offer(need):
        return None  # o "sim" aos termos é confirmação: quem responde é o fechamento do pedido
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                    situation=state.situation(need, reply_only_courtesy=True))


def reply(state, need):
    if need.act in DECLARATION_ACTS:
        return PartSpec(MOVE, {"decline_offers": "acknowledge.declined_offers",
                               "accept_offers": "acknowledge.accepted_offers"}[need.act])
    template = "acknowledge.got_it" if need.answers_question else "acknowledge.thanks"
    return PartSpec(MOVE, template)
