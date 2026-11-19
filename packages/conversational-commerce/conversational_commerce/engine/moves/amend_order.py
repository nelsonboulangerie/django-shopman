"""Alterar um pedido, só acrescentando (A3, só com a linha do perfil aprovada). No D1, só precondição.

Nenhum ato do D1 pede alteração: o movimento existe para a política e para o
catálogo, e não é proposto pelo turno. Quando um WP trouxer o ato, ele lê se a
alteração só acrescenta e a confirmação presa ao novo total.
"""

from __future__ import annotations

from conversational_commerce.reply import PartSpec, SlotSpec, Template

MOVE = "amend_order"
TEMPLATES = (
    Template("amend_order.done", "1", MOVE, "Your order {order} is updated.",
             {"order": SlotSpec(("receipt:success",), "effect")}),
)


def propose(state, need):
    return None


def reply(state, need):
    return PartSpec(MOVE, "amend_order.done", {"order": ("receipt", f"none.{need.need_id}")})
