"""Perguntar: campo obrigatório ausente, ou duas leituras numa mudança (v2 4.2)."""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, SlotSpec, Template

MOVE = "ask_clarification"
TEMPLATES = (
    Template("ask_clarification.which", "1", MOVE, "Did you mean {option_a} or {option_b}?",
             {"option_a": SlotSpec(("fact",), "name"), "option_b": SlotSpec(("fact",), "name")}),
    Template("ask_clarification.more", "1", MOVE, "Could you tell me a bit more about what you need?"),
    # A dúvida do verificador (ADR-051): a leitura que responde à pergunta no ar, repetida para o "sim" ou o
    # "não" do cliente. O lastro é a leitura (o que ele disse), não um fato da casa.
    Template("ask_clarification.confirm_reading", "1", MOVE, "Just to confirm: {reading}?",
             {"reading": SlotSpec(("reading",))}),
)
#: O lastro da leitura a confirmar, por necessidade (``Evidence.readings``).
READING_REF = "reading.{need_id}"


def propose(state, need):
    if need.confirm is not None:
        return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                        situation=state.situation(need, missing_required_field=True))
    two_readings_change = need.request_kind == "change" and len(need.readings) >= 2
    if not (two_readings_change or state.situation(need).missing_required_field):
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                    situation=state.situation(need))


def reply(state, need):
    if need.confirm is not None:
        return PartSpec(MOVE, "ask_clarification.confirm_reading",
                        {"reading": ("reading", READING_REF.format(need_id=need.need_id))})
    keys = state.fact_keys_for(need)
    if len(keys) >= 2 and all(key in state.facts for key in keys[:2]):
        return PartSpec(MOVE, "ask_clarification.which", {"option_a": ("fact", keys[0]),
                                                          "option_b": ("fact", keys[1])})
    return PartSpec(MOVE, "ask_clarification.more")
