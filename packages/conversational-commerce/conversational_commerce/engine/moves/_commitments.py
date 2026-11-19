"""O que os movimentos de compromisso compartilham: a resposta pelo compromisso registrado.

Não é movimento (o nome começa com ``_``, e o registro o pula). A promessa só é
dita com o compromisso como lastro: com prazo, o molde que diz o prazo; sem
prazo (fora do expediente, ou sem saber o expediente), o molde que não afirma
prazo nenhum. Sem compromisso registrado (a equipe não foi chamada, por
exemplo em ``shadow``), o espaço aponta um compromisso que não existe, e a
verificação segura a mensagem.
"""

from __future__ import annotations

from conversational_commerce.reply import PartSpec


def commitment_ref(state, need) -> str | None:
    return state.commitment_of.get(need.need_id) or state.waiting.get(need.need_id)


def commitment_part(state, need, move: str, *, with_deadline: tuple[str, tuple[str, ...]],
                    without_deadline: tuple[str, tuple[str, ...]]) -> PartSpec:
    """A parte da resposta. ``with_deadline`` e ``without_deadline``: (molde, espaços que o compromisso preenche)."""
    ref = commitment_ref(state, need)
    template_id, slots = with_deadline
    if ref is None or ref not in state.commitments:
        return PartSpec(move, template_id, dict.fromkeys(slots, ("commitment", f"none.{need.need_id}")))
    if state.commitments[ref].deadline.status != "set":
        template_id, slots = without_deadline
    return PartSpec(move, template_id, dict.fromkeys(slots, ("commitment", ref)))
