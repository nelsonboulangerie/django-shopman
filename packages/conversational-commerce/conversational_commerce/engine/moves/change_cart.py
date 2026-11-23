"""Mudar o carrinho: quantidade absoluta, evento com identidade estável, reversível (A2).

Concessão pela linha do perfil (sem termos: a mudança é reversível e não fecha
nada). A quantidade relativa ("mais um") não é absoluta e fica inelegível: o
que se pede tem de dizer o resultado, para que repetir não some duas vezes.

Várias linhas num turno ("2 croissants e 1 baguete") são UMA mudança material do
carrinho: um comando só, com todas as linhas, atômico e com um recibo (spec 08 §5,
[DECIDIDO]). A primeira necessidade de mudança do turno leva o comando; as outras
são levadas por ela (``carried_by``) e recebem o mesmo recibo.
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import TEMPLATES_BY_ID

from ..state import EffectPlan
from ._effects import SHARED, known_with, receipt_part

MOVE = "change_cart"
EFFECT = True
TEMPLATES = (TEMPLATES_BY_ID["change_cart.done"], TEMPLATES_BY_ID["change_cart.done_receipt"], *SHARED)


def _line(need):
    """Os campos da linha que a necessidade pede, ou ``None`` (não é mudança, é ambígua ou não diz o item)."""
    if need.act != "change_quantity" or len(need.readings) != 1:
        return None
    fields = need.readings[0]
    return fields if fields.get("item") else None


def _absolute(fields) -> bool:
    return "quantity" in fields and not fields.get("relative", False)


def lines(state) -> list:
    """As necessidades de mudança do turno que viram linhas do mesmo comando, na ordem em que vieram."""
    return [need for need in state.needs if _line(need) is not None and need.need_id not in state.refused]


def eligible_change(state) -> bool:
    """Há uma mudança material do carrinho que pode virar comando neste turno.

    A sacola (linhas absolutas, sem item repetido), o recebimento ou a forma de pagamento, ditos com
    uma leitura só. É ela que segura o "sim" aos termos de antes (v2 4.7, propriedade 2).
    """
    group = lines(state)
    items = [_line(other)["item"] for other in group]
    cart = bool(group) and len(set(items)) == len(items) and all(_absolute(_line(other)) for other in group)
    other_change = any(need.act in ("choose_fulfillment", "choose_payment", "give_address") and len(need.readings) == 1
                       and need.need_id not in state.refused for need in state.needs)
    return cart or other_change


def propose(state, need):
    fields = _line(need)
    if fields is None or state.subject.cart_ref is None or need.need_id in state.refused:
        return None
    if state.changed_under_offer(need):
        return None  # já mudou neste turno, com termos no ar: a decisão refeita apresenta os termos novos
    group = lines(state)
    items = [_line(other)["item"] for other in group]
    if len(set(items)) != len(items):
        # O mesmo item em duas linhas ("2 croissants… e 1 croissant"): qual vale não se sabe. Nenhuma
        # linha vira comando (a última venceria em silêncio); a casa diz a limitação.
        return None
    lead = group[0]
    # O comando é tudo ou nada: uma linha relativa torna a mudança inteira inelegível, para a líder e
    # para as levadas (a levada herda a elegibilidade do grupo e nunca é escolhida sozinha).
    absolute = all(_absolute(_line(other)) for other in group)
    if need.need_id != lead.need_id:
        # Levada pela primeira: a mesma mudança, no mesmo comando (nunca um segundo efeito).
        return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                        content={"carried_by": lead.need_id},
                        situation=state.situation(need, quantity_is_absolute=absolute, change_reversible=True))
    content = {"lines": [{"item": _line(other)["item"], "quantity": _line(other).get("quantity")} for other in group]}
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content=content,
                    situation=state.situation(need, quantity_is_absolute=absolute, change_reversible=True))


def effect(state, need) -> EffectPlan:
    return EffectPlan(action=MOVE, target=state.subject.cart_ref,
                      parameters={"lines": [{"item": _line(other)["item"], "quantity": str(_line(other)["quantity"])}
                                            for other in lines(state)]},
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
