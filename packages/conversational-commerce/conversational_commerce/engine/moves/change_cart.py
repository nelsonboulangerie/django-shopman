"""Mudar o carrinho: quantidade absoluta, evento com identidade estável, reversível (A2).

Concessão pela linha do perfil (sem termos: a mudança é reversível e não fecha
nada). A quantidade relativa ("mais um") não é absoluta e fica inelegível: o
que se pede tem de dizer o resultado, para que repetir não some duas vezes.
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import TEMPLATES_BY_ID

from ..state import EffectPlan
from ._effects import SHARED, known_with, receipt_part

MOVE = "change_cart"
EFFECT = True
TEMPLATES = (TEMPLATES_BY_ID["change_cart.done"], TEMPLATES_BY_ID["change_cart.done_receipt"], *SHARED)


def propose(state, need):
    if need.act != "change_quantity" or len(need.readings) != 1 or state.subject.cart_ref is None \
            or need.need_id in state.refused:
        return None
    fields = need.readings[0]
    if not fields.get("item"):
        return None
    absolute = "quantity" in fields and not fields.get("relative", False)
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"item": fields["item"], "quantity": fields.get("quantity")},
                    situation=state.situation(need, quantity_is_absolute=absolute, change_reversible=True))


def effect(state, need) -> EffectPlan:
    fields = need.readings[0]
    return EffectPlan(action=MOVE, target=state.subject.cart_ref,
                      parameters={"item": fields["item"], "quantity": str(fields["quantity"])},
                      expected_versions={}, basis="line")


def reply(state, need):
    # A sacola depois da mudança: os termos cotados de novo depois do recibo de sucesso (``Engine._after_effects``).
    key = state.terms_key(state.subject.cart_ref) if state.subject.cart_ref else "terms.none"
    receipt = state.receipts.get(need.need_id)
    if receipt is not None and receipt.status == "success" and not known_with(state, key, "items", "total"):
        # O efeito aconteceu e os termos novos não vieram: o degrau de baixo diz só o efeito.
        return receipt_part(state, need, MOVE, "change_cart.done_receipt", "done")
    return receipt_part(state, need, MOVE, "change_cart.done", "done",
                        also=lambda receipt: {"items": ("fact", key), "total": ("fact", key)})
