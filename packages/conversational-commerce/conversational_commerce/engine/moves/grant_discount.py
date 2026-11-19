"""Conceder desconto (A4), com o teto da linha ``commerce.discount_cap_minor``. No D1, só precondição.

Nenhum ato do D1 pede desconto, e a iniciativa comercial não pedida não é
deste WP: o movimento não é proposto pelo turno. ``within_cap`` é a regra do
teto, lida do perfil: linha ausente, nenhum desconto.
"""

from __future__ import annotations

from conversational_commerce.profile import read_line
from conversational_commerce.reply import PartSpec, SlotSpec, Template

MOVE = "grant_discount"
CAP_LINE = "commerce.discount_cap_minor"
TEMPLATES = (
    Template("grant_discount.done", "1", MOVE, "A discount of {amount} is applied.",
             {"amount": SlotSpec(("receipt:success",), "effect")}),
)


def cap_minor(profile) -> int | None:
    reading = read_line(profile, CAP_LINE)
    value = reading.value if reading.usable else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def within_cap(profile, amount_minor: int) -> bool:
    cap = cap_minor(profile)
    return cap is not None and 0 < amount_minor <= cap


def propose(state, need):
    return None


def reply(state, need):
    return PartSpec(MOVE, "grant_discount.done", {"amount": ("receipt", f"none.{need.need_id}")})
