"""J3 · Fato que o sistema não tem: verificar com a equipe e devolver (v2 10).

Prova: compromisso com dono e prazo, espera com retomada e a resposta da equipe
devolvida como fato com autoria. O item ``ITEM-Z`` não está no catálogo
(``not_found``): a casa não inventa nem desiste, pergunta à equipe e diz até
quando responde. A equipe responde (passo que não é mensagem do cliente) e a
resposta volta ao cliente, com o compromisso cumprido.

O escalonamento por prazo vencido (K22) e a fila que recusa (K20) estão nos
testes de ``tests/commitments/``.
"""

from __future__ import annotations

from conversational_commerce.ports import TrustedContext

from .runner import JourneyStep

CTX = TrustedContext(tenant="tenant-a", environment="test", subject=None)
# O que a pessoa da equipe responde: o item, com nome e preço.
ANSWER = {"ref": "ITEM-Z", "name": "Item Z", "unit": "unit", "price_minor": 800, "currency": "XTS"}


def message(mid: str, text: str):
    return {"id": mid, "from": "addr-j3", "conversation": "conv-j3", "content_ref": f"text:{text}"}


def staff_answers(engine, ctx: TrustedContext):
    """A pessoa da equipe responde a pergunta aberta, e o núcleo devolve a resposta ao cliente."""
    (entry,) = engine.commitments.open_entries(ctx.tenant, ctx.environment)
    engine.ports.staff.answer(entry.ticket_id, ANSWER)
    return engine.staff_answered(ctx, entry.commitment_id)


ASK = JourneyStep(
    message=message("j3-m1", "how much is item z?"),
    understanding={"acts": [{"act": "ask_price", "fields": {"item": "ITEM-Z"}}]},
    expect_moves=("verify_with_staff",),
    # O prazo é o da fila a partir de agora; o instante exato é conferido nos testes do F9.
    expect_text=("I'll check with the team and answer by ",),
    expect_state="active",
)
ANSWERED = JourneyStep(
    message=None,
    act=staff_answers,
    expect_moves=("inform",),
    expect_text=("Item Z costs XTS 8.00.",),
    expect_state="active",
    advance_seconds=10 * 60,
)

STEPS = (ASK, ANSWERED)
