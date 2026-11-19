"""J5 · Reclamação e dúvida na mesma mensagem (v2 10, K19).

Prova: a agenda de necessidades (duas, uma por ato), a prioridade (o caso vence
a família de resolver, e cada necessidade tem a sua resposta), o caso com dono e
prazo, e nenhuma oferta: com problema aberto, a política suspende toda
iniciativa comercial no episódio. A reclamação não apaga a dúvida: o horário é
respondido na mesma mensagem.
"""

from __future__ import annotations

from conversational_commerce.ports import TrustedContext

from .runner import JourneyStep

CTX = TrustedContext(tenant="tenant-a", environment="test", subject=None)


def message(mid: str, text: str):
    return {"id": mid, "from": "addr-j5", "conversation": "conv-j5", "content_ref": f"text:{text}"}


COMPLAINT_AND_QUESTION = JourneyStep(
    message=message("j5-m1", "my last order was the wrong order, and what are your hours?"),
    understanding={"acts": [{"act": "complain", "fields": {"problem": "wrong_order", "resolution": "replacement"}},
                            {"act": "ask_hours"}]},
    expect_moves=("open_case", "inform"),
    expect_text=("I'm sorry about this. Our attendant will look into it and get back to you by "
                 "2026-01-05T09:30:00.000000Z.",
                 "We are open from 08:00 to 18:00."),
    expect_state="active",
)

STEPS = (COMPLAINT_AND_QUESTION,)
