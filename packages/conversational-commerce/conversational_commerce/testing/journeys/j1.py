"""J1 · Pergunta de produto respondida com fato (v2 10).

Prova: fato com fonte, resposta com prova, e desconhecido que não vira frase.
O passo 3 roda com a fonte do item fora: a resposta não afirma preço nenhum.
"""

from __future__ import annotations

from .runner import JourneyStep

STEPS = (
    JourneyStep(
        message={"id": "j1-m1", "from": "addr-j1", "conversation": "conv-j1", "content_ref": "text:price of item a?"},
        understanding={"acts": [{"act": "ask_price", "fields": {"item": "ITEM-A"}}]},
        expect_moves=("inform",),
        expect_text=("Item A costs XTS 4.50.",),
        expect_state="active",
    ),
    JourneyStep(
        message={"id": "j1-m2", "from": "addr-j1", "conversation": "conv-j1", "content_ref": "text:what are your hours?"},
        understanding={"acts": [{"act": "ask_hours"}]},
        expect_moves=("inform",),
        expect_text=("We are open from 08:00 to 18:00.",),
        expect_state="active",
    ),
)

# Mesmo pedido de preço, com a fonte do catálogo fora: limitação, nunca um preço inventado.
UNKNOWN_STEP = JourneyStep(
    message={"id": "j1-m3", "from": "addr-j1", "conversation": "conv-j1", "content_ref": "text:price of item b?"},
    understanding={"acts": [{"act": "ask_price", "fields": {"item": "ITEM-B"}}]},
    expect_moves=("inform_limitation",),
    expect_text=("I can't do that here.",),
)
