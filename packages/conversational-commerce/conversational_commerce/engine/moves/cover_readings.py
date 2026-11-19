"""Duas leituras numa consulta: responde as duas mais prováveis (v2 4.2)."""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, SlotSpec, Template

MOVE = "cover_readings"
TEMPLATES = (
    Template("cover_readings.prices", "1", MOVE, "{name_a} costs {price_a}; {name_b} costs {price_b}.",
             {"name_a": SlotSpec(("fact",), "name"), "price_a": SlotSpec(("fact",)),
              "name_b": SlotSpec(("fact",), "name"), "price_b": SlotSpec(("fact",))}),
)


def propose(state, need):
    if not need.is_query or len(need.readings) < 2:
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"facts": list(state.fact_keys_for(need))[:2]}, situation=state.situation(need))


def reply(state, need):
    first, second = state.fact_keys_for(need)[:2]
    return PartSpec(MOVE, "cover_readings.prices", {"name_a": ("fact", first), "price_a": ("fact", first),
                                                    "name_b": ("fact", second), "price_b": ("fact", second)})
