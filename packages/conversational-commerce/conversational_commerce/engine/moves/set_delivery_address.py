"""O endereço da entrega: uma condição dos termos, como efeito reversível no carrinho (A2).

Proposto para o ato ``give_address``, que NÃO tem campo: quem lê só marca que a fala traz um endereço.
O endereço é dado pessoal (P17): não vai ao modelo, não entra em contrato, não fica em registro. Por isso o
comando leva só a referência protegida do conteúdo do evento (``source``, a ``content_ref`` da spec 01), e
é o executor da casa que lê o texto original, monta o endereço e o grava, dentro do efeito. O recibo traz
só uma referência opaca (``address_ref``); quem a diz em texto é o formatador de referência da casa
(spec 06), e só no envio.

Leitura com campo (``{"street": ...}``) é recusada (``address_not_by_reference``): um leitor que extraísse
o endereço poria dado pessoal no contrato.

Separado do ``set_fulfillment`` (spec 08 §6): o recebimento diz quando e como, com valores fechados que
o motor confere; o endereço diz onde, e só a casa sabe ler.
"""

from __future__ import annotations

from conversational_commerce.contracts.errors import ErrorCode
from conversational_commerce.policy import Proposal
from conversational_commerce.reply import TEMPLATES_BY_ID, PartSpec, Template

from ..state import EffectPlan
from ._effects import SHARED, receipt_part

MOVE = "set_delivery_address"
ACT = "give_address"
EFFECT = True
#: A recusa do endereço tem frase própria: o cliente precisa saber o que fazer (outro endereço, a localização).
#: É limitação (nada mudou), por isso do movimento ``inform_limitation``.
NOT_DELIVERED = Template("set_delivery_address.not_delivered", "1", "inform_limitation",
                         "We don't deliver to that address. What is the delivery address?")
NOT_LOCATED = Template("set_delivery_address.not_located", "1", "inform_limitation",
                       "I couldn't locate that address. Check the street, number and district, or send your location.")
#: O endereço sem entrega combinada (a sacola é de retirada, ou o modo não foi escolhido): o sistema de
#: registro diz ``fact_unavailable``, e a pergunta é o modo, não a limitação.
ASK_MODE = Template("set_delivery_address.ask_mode", "1", "inform_limitation",
                    "Will you pick it up at the store, or should we deliver?")
REFUSALS = {ErrorCode.FULFILLMENT_UNAVAILABLE.value: NOT_DELIVERED, ErrorCode.INVALID_CONTENT.value: NOT_LOCATED,
            ErrorCode.FACT_UNAVAILABLE.value: ASK_MODE}
TEMPLATES = (TEMPLATES_BY_ID["set_delivery_address.done"], NOT_DELIVERED, NOT_LOCATED, ASK_MODE, *SHARED)


def _by_reference(state, need) -> bool:
    """Uma leitura só, sem campo nenhum, e a fala com referência protegida."""
    return len(need.readings) == 1 and not dict(need.readings[0]) and bool(state.content_ref)


def propose(state, need):
    if need.act != ACT or len(need.readings) != 1 or state.subject.cart_ref is None \
            or need.need_id in state.refused:
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE,
                    content={"source": state.content_ref or ""},
                    situation=state.situation(need, address_by_reference=_by_reference(state, need),
                                              change_reversible=True))


def effect(state, need) -> EffectPlan:
    return EffectPlan(action=MOVE, target=state.subject.cart_ref, parameters={"source": state.content_ref or ""},
                      expected_versions={}, basis="line")


def refusal_part(state, need) -> PartSpec | None:
    """A recusa do endereço com frase própria (dita pelo ``inform_limitation``, que responde à recusa)."""
    template = REFUSALS.get(str(state.refused.get(need.need_id) or ""))
    return PartSpec("inform_limitation", template.template_id) if template is not None else None


def reply(state, need):
    return receipt_part(state, need, MOVE, "set_delivery_address.done", "address")
