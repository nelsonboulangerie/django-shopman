"""O que não se pode fazer aqui: dizer a limitação e oferecer encaminhar (K39).

Proposto para todo pedido de mudança que nenhum movimento do turno executa,
para reclamação (até que os movimentos de efeito, F8, e de caso, F9, existam) e
para a consulta cujo fato está desconhecido: desconhecido não vira frase (J1).
"""

from __future__ import annotations

from conversational_commerce.policy import Proposal
from conversational_commerce.reply import PartSpec, Template

from ..acts import CHANGE_ACTS

MOVE = "inform_limitation"
TEMPLATES = (
    Template("inform_limitation.offer_team", "1", MOVE, "I can't do that here. I can hand you to the team."),
)
LIMITED_ACTS = CHANGE_ACTS | {"complain"}


def _fact_missing(state, need) -> bool:
    """Consulta cujo fato não se tem: a resposta pedida não pode ser dada (desconhecido não vira frase)."""
    from conversational_commerce.contracts import Known

    keys = state.fact_keys_for(need)
    return need.is_query and bool(keys) and any(not isinstance(state.facts.get(key), Known) for key in keys)


def propose(state, need):
    if need.act not in LIMITED_ACTS and not _fact_missing(state, need):
        return None
    if need.request_kind == "change" and len(need.readings) >= 2:
        return None  # pedido ambíguo: pergunta antes; não se sabe ainda o que foi pedido
    return Proposal(candidate_ref=f"{need.need_id}:{MOVE}", need_id=need.need_id, move=MOVE, content={},
                    situation=state.situation(need, requested_move_ineligible=True))


def reply(state, need):
    return PartSpec(MOVE, "inform_limitation.offer_team")
