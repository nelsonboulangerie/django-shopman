"""Escolher a forma de pagamento: uma condição dos termos, como efeito reversível no carrinho (A2).

Proposto para o ato ``choose_payment`` com uma leitura só (``{"method": ...}``) e o carrinho do sujeito.
A forma tem de ser uma das que o canal oferece (``commerce_read.requirements``, precondição
``payment_method_offered``): o valor nunca sai do texto. O efeito SOBE a versão do carrinho, como toda
mudança do alvo, e por isso mudar a forma depois do resumo invalida o "sim" aos termos de antes (a guarda
confere a versão, N07).
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import TEMPLATES_BY_ID, PartSpec, SlotSpec, Template

from ..state import EffectPlan
from ._effects import SHARED, receipt_part

MOVE = "set_payment"
ACT = "choose_payment"
EFFECT = True
#: A forma que o canal não oferece tem frase própria: diz que não e pergunta de novo, com as opções do canal.
#: É limitação (nada mudou), por isso do movimento ``inform_limitation``, que responde ao bloqueio.
NOT_OFFERED = Template("set_payment.not_offered", "1", "inform_limitation",
                       "We don't take that payment method here. How would you like to pay? {payment_method}",
                       {"payment_method": SlotSpec(("fact",), "payment_method")})
TEMPLATES = (TEMPLATES_BY_ID["set_payment.done"], NOT_OFFERED, *SHARED)


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
                    situation=state.situation(need, conditions_known=state.conditions_known(),
                                              payment_method_offered=offered, change_reversible=True))


def effect(state, need) -> EffectPlan:
    return EffectPlan(action=MOVE, target=state.subject.cart_ref, parameters={"method": _method(need)},
                      expected_versions={}, basis="line")


def limitation_part(state, need) -> PartSpec | None:
    """A forma pedida que o canal não oferece (com as opções conhecidas): a frase própria, com as opções."""
    method = _method(need)
    target = state.subject.cart_ref
    if need.act != ACT or not method or target is None or not state.conditions_known() \
            or method in state.offered(target, "payment_method"):
        return None
    return PartSpec("inform_limitation", NOT_OFFERED.template_id,
                    {"payment_method": ("fact", state.requirements_key(target))})


def reply(state, need):
    return receipt_part(state, need, MOVE, "set_payment.done", "method")
