"""Escolher a forma de pagamento: uma condição dos termos, como efeito reversível no carrinho (A2).

Proposto para o ato ``choose_payment`` com uma leitura só (``{"method": ...}``) e o carrinho do sujeito.
A forma tem de ser uma das que o canal oferece (``commerce_read.requirements``, precondição
``payment_method_offered``): o valor nunca sai do texto. O efeito SOBE a versão do carrinho, como toda
mudança do alvo, e por isso mudar a forma depois do resumo invalida o "sim" aos termos de antes (a guarda
confere a versão, N07).
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import TEMPLATES_BY_ID

from ..state import EffectPlan
from ._effects import SHARED, receipt_part

MOVE = "set_payment"
ACT = "choose_payment"
EFFECT = True
TEMPLATES = (TEMPLATES_BY_ID["set_payment.done"], *SHARED)


def _method(need) -> str:
    return str(need.readings[0].get("method") or "") if len(need.readings) == 1 else ""


def propose(state, need):
    if need.act != ACT or len(need.readings) != 1 or state.subject.cart_ref is None \
            or need.need_id in state.refused:
        return None
    method = _method(need)
    if not method:
        return None
    offered = method in state.offered(state.subject.cart_ref, "payment_method")
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"method": method},
                    situation=state.situation(need, payment_method_offered=offered, change_reversible=True))


def effect(state, need) -> EffectPlan:
    return EffectPlan(action=MOVE, target=state.subject.cart_ref, parameters={"method": _method(need)},
                      expected_versions={}, basis="line")


def reply(state, need):
    return receipt_part(state, need, MOVE, "set_payment.done", "method")
