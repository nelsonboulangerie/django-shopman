"""O que os movimentos de efeito compartilham: a resposta pelo recibo.

Não é movimento (o nome começa com ``_``, e o registro o pula). A resposta de um
movimento de efeito sai do recibo do ponto de efeito, nunca da intenção:

- ``success``: o molde do movimento, com o recibo de sucesso no espaço;
- ``pending`` ou ``unknown``: uma espera, com o prazo da reconciliação (o
  compromisso que o núcleo registra), nunca a confirmação do efeito;
- ``failure``: a limitação, dita sem afirmar efeito nenhum;
- sem recibo (o efeito não aconteceu neste turno, por exemplo em ``shadow``): o
  espaço aponta um recibo que não existe, e a verificação segura a mensagem (K24).
"""

from __future__ import annotations

from conversational_commerce.reply import PartSpec, SlotSpec, Template

PENDING = Template("effect.pending", "1", "wait", "This is still in progress; I'll confirm the outcome by {deadline}.",
                   {"deadline": SlotSpec(("commitment:promise",), "at")})
FAILED = Template("effect.failed", "1", "inform_limitation",
                  "That didn't go through, and nothing was changed. I can hand you to the team.")
SHARED = (PENDING, FAILED)


def commitment_id(command_id: str) -> str:
    return f"reconcile.{command_id}"


def receipt_part(state, need, move: str, template_id: str, slot: str) -> PartSpec:
    receipt = state.receipts.get(need.need_id)
    if receipt is None:
        return PartSpec(move, template_id, {slot: ("receipt", f"none.{need.need_id}")})
    if receipt.status == "success":
        return PartSpec(move, template_id, {slot: ("receipt", receipt.command_id)})
    if receipt.status == "failure":
        return PartSpec("inform_limitation", FAILED.template_id)
    return PartSpec("wait", PENDING.template_id, {"deadline": ("commitment", commitment_id(receipt.command_id))})
