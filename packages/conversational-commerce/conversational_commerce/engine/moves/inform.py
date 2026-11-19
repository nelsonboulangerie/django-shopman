"""Informar um fato, com o fato como lastro de cada afirmação."""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, SlotSpec, Template

MOVE = "inform"
TEMPLATES = (
    Template("inform.hours", "1", MOVE, "We are open from {opens} to {closes}.",
             {"opens": SlotSpec(("fact",), "opens"), "closes": SlotSpec(("fact",), "closes")}),
    Template("inform.price", "1", MOVE, "{name} costs {price}.",
             {"name": SlotSpec(("fact",), "name"), "price": SlotSpec(("fact",))}),
)


def propose(state, need):
    if not need.is_query or len(need.readings) != 1:
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"facts": list(state.fact_keys_for(need))}, situation=state.situation(need))


def reply(state, need):
    if need.act == "ask_hours":
        return PartSpec(MOVE, "inform.hours", {"opens": ("fact", "hours"), "closes": ("fact", "hours")})
    key = state.fact_keys_for(need)[0]
    return PartSpec(MOVE, "inform.price", {"name": ("fact", key), "price": ("fact", key)})
