"""O que não se pode fazer aqui: dizer a limitação e oferecer encaminhar (K39).

Proposto quando o que se pede não tem movimento elegível que o faça: o pedido
de mudança cujo movimento de efeito está inelegível (ou não existe), a
reclamação sem caso possível, o pedido de pessoa sem fila declarada, o "sim"
aos termos que não autoriza nem pede termos novos, e a consulta cujo fato está
desconhecido sem verificação possível com a equipe (desconhecido não vira
frase, J1). Quando o movimento que faz o pedido é
elegível, este não é proposto: ele vem antes no catálogo e venceria o empate.
"""

from __future__ import annotations

from conversational_commerce.catalog import evaluate_move
from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, Template

from ..acts import CHANGE_ACTS

MOVE = "inform_limitation"
TEMPLATES = (
    Template("inform_limitation.offer_team", "1", MOVE, "I can't do that here. I can hand you to the team."),
)
LIMITED_ACTS = CHANGE_ACTS | {"complain", "request_human"}
# O movimento que faz cada pedido de mudança.
HANDLED_BY = {"change_quantity": ("change_cart",), "place_order": ("present_terms",),
              "cancel_order": ("cancel_order",), "complain": ("open_case",), "request_human": ("handoff",)}


def _fact_missing(state, need) -> bool:
    """Consulta cujo fato não se tem: a resposta pedida não pode ser dada (desconhecido não vira frase)."""
    from conversational_commerce.contracts import Known

    keys = state.fact_keys_for(need)
    return need.is_query and bool(keys) and any(not isinstance(state.facts.get(key), Known) for key in keys)


def _handled(state, need) -> bool:
    """Algum movimento elegível faz o que foi pedido."""
    from . import registry

    moves = registry()
    if state.answers_offer(need):
        names = ("commit_order", "present_terms")
    elif _fact_missing(state, need):
        names = ("verify_with_staff",)
    else:
        names = HANDLED_BY.get(need.act, ())
    for name in names:
        module = moves.get(name)
        proposal = module.propose(state, need) if module is not None else None
        if proposal is not None and evaluate_move(name, proposal.situation, state.profile).eligible:
            return True
    return False


def propose(state, need):
    if need.act not in LIMITED_ACTS and not _fact_missing(state, need) and not state.answers_offer(need):
        return None
    if need.request_kind == "change" and len(need.readings) >= 2:
        return None  # pedido ambíguo: pergunta antes; não se sabe ainda o que foi pedido
    if _handled(state, need):
        return None
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                    situation=state.situation(need, requested_move_ineligible=True))


def reply(state, need):
    return PartSpec(MOVE, "inform_limitation.offer_team")
