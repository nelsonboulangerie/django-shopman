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
    # A parte que a sequência de efeitos não tentou (o efeito anterior não teve sucesso): não foi impossível,
    # só fica para depois de acertar o passo anterior (spec 08 §5).
    # O "sim" com uma mudança junto que não se concluiu: o pedido espera a sacola, não foi impossível.
    Template("inform_limitation.confirm_after_change", "1", MOVE,
             "I'll register it once your cart change is settled; then I'll show you the summary again."),
    Template("inform_limitation.not_attempted", "1", MOVE,
             "That part waits until the earlier step is settled; tell me again once it is."),
    # A recusa do cliente segura a oferta até ele mudar de ideia (F10).
    Template("inform_limitation.offers_declined", "1", MOVE,
             "You asked me not to make suggestions. Tell me if you'd like them again."),
)
LIMITED_ACTS = CHANGE_ACTS | {"complain", "request_human", "ask_recommendation"}
# O movimento que faz cada pedido de mudança.
HANDLED_BY = {"change_quantity": ("change_cart",), "choose_fulfillment": ("set_fulfillment",),
              "place_order": ("present_terms",),
              "cancel_order": ("cancel_order",), "complain": ("open_case",), "request_human": ("handoff",),
              "ask_recommendation": ("recommend",)}


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
    elif state.changed_under_offer(need):
        names = ("present_terms",)  # a mudança já feita com termos no ar: quem atende são os termos novos
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
    if state.refused.get(need.need_id) == "sequence_stopped":
        return PartSpec(MOVE, "inform_limitation.not_attempted")
    from .change_cart import eligible_change

    if state.answers_offer(need) and eligible_change(state):
        return PartSpec(MOVE, "inform_limitation.confirm_after_change")
    if need.act == "ask_recommendation" and state.declined_offers:
        return PartSpec(MOVE, "inform_limitation.offers_declined")
    return PartSpec(MOVE, "inform_limitation.offer_team")
