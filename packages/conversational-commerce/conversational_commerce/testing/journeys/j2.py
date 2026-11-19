"""J2 · Pedido ambíguo esclarecido (v2 10).

Prova: a pergunta no ar, o referente do "sim" e o limiar pelo custo do erro.
Uma mudança com duas leituras pergunta antes (o episódio espera a resposta); o
"sim" seguinte se liga à pergunta da mesma época e o episódio volta a ativo.
Uma consulta com duas leituras cobre as duas, sem perguntar.
"""

from __future__ import annotations

from .runner import JourneyStep

CHANGE_TWO_READINGS = {
    "acts": [{"act": "change_quantity", "fields": {"item": "ITEM-A", "quantity": "2"}}],
    "alternatives": [[{"act": "change_quantity", "fields": {"item": "ITEM-B", "quantity": "2"}}]],
}
QUERY_TWO_READINGS = {
    "acts": [{"act": "ask_price", "fields": {"item": "ITEM-A"}}],
    "alternatives": [[{"act": "ask_price", "fields": {"item": "ITEM-B"}}]],
}

STEPS = (
    JourneyStep(
        message={"id": "j2-m1", "from": "addr-j2", "conversation": "conv-j2", "content_ref": "text:make it two"},
        understanding=CHANGE_TWO_READINGS,
        expect_moves=("ask_clarification",),
        expect_text=("Did you mean Item A or Item B?",),
        expect_state="waiting_input",
    ),
    JourneyStep(
        message={"id": "j2-m2", "from": "addr-j2", "conversation": "conv-j2", "content_ref": "text:yes"},
        understanding={"acts": [{"act": "affirm"}]},
        expect_moves=("acknowledge",),
        expect_text=("Got it, thank you.",),
        expect_state="active",
    ),
    JourneyStep(
        message={"id": "j2-m3", "from": "addr-j2", "conversation": "conv-j2", "content_ref": "text:how much is it?"},
        understanding=QUERY_TWO_READINGS,
        expect_moves=("cover_readings",),
        expect_text=("Item A costs XTS 4.50; Item B costs XTS 12.00.",),
        expect_state="active",
    ),
)
