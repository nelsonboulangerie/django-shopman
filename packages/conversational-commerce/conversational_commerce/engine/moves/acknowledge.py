"""Cortesia: saudação, agradecimento, e o "entendi" que fecha uma pergunta respondida."""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, Template

from ..acts import ANSWER_ACTS, CHANGE_ACTS, COURTESY_ACTS, DECLARATION_ACTS

MOVE = "acknowledge"
TEMPLATES = (
    Template("acknowledge.thanks", "1", MOVE, "Thank you for your message."),
    Template("acknowledge.got_it", "1", MOVE, "Got it, thank you."),
    Template("acknowledge.declined_offers", "1", MOVE, "Understood. I won't make suggestions."),
    Template("acknowledge.accepted_offers", "1", MOVE, "Understood. I'll suggest things again when it helps."),
    # O "não" à pergunta dos termos, com NENHUM efeito no turno: nada foi registrado, e o carrinho
    # ficou como estava. Com uma mudança junto ("deixa pra lá, tira o croissant"), esta frase seria falsa.
    Template("acknowledge.terms_declined", "1", MOVE, "Understood, nothing was placed. Your cart stays as it is."),
)


def propose(state, need):
    if need.act not in COURTESY_ACTS | ANSWER_ACTS | DECLARATION_ACTS or state.answers_offer(need):
        return None  # o "sim" aos termos é confirmação: quem responde é o fechamento do pedido
    if state.answers_condition(need) or state.declines_condition(need):
        return None  # o "sim" ou o "não" à condição pendente: quem responde é quem a cumpre, ou o fechamento
    if need.act == "deny" and state.closing and any(
            other.need_id != need.need_id and other.act in CHANGE_ACTS for other in state.needs):
        return None  # "não, o do trabalho": o "não" é a correção, e quem responde é a mudança
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                    situation=state.situation(need, reply_only_courtesy=True))


def reply(state, need):
    if need.act in DECLARATION_ACTS:
        return PartSpec(MOVE, {"decline_offers": "acknowledge.declined_offers",
                               "accept_offers": "acknowledge.accepted_offers"}[need.act])
    if state.declines_terms(need) and not state.effect_chosen:
        return PartSpec(MOVE, "acknowledge.terms_declined")
    template = "acknowledge.got_it" if need.answers_question else "acknowledge.thanks"
    return PartSpec(MOVE, template)
