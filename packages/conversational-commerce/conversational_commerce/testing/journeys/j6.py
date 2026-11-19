"""J6 · Recomendação por necessidade explícita (v2 10).

Prova: o primeiro movimento comercial, sob a restrição de conselheiro (só o item que
atende a exigência declarada, com nome e preço do fato lido), e a recusa
respeitada: o cliente pede para não receber sugestões, a memória declarada guarda
a recusa, e a casa não sugere de novo até ele mudar de ideia.
"""

from __future__ import annotations

from conversational_commerce.ports import TrustedContext

from .runner import JourneyStep

CTX = TrustedContext(tenant="tenant-a", environment="test", subject=None)
BY_WEIGHT = {"acts": [{"act": "ask_recommendation", "fields": {"need": {"unit": "kg"}}}]}


def message(mid: str, text: str):
    return {"id": mid, "from": "addr-j6", "conversation": "conv-j6", "content_ref": f"text:{text}"}


ASK = JourneyStep(
    message=message("j6-m1", "can you suggest something sold by weight?"),
    understanding=BY_WEIGHT,
    expect_moves=("recommend",),
    expect_text=("For that, I'd suggest Item C (by weight) at XTS 39.90.",),
    expect_state="active",
)
DECLINE = JourneyStep(
    message=message("j6-m2", "no more suggestions, please"),
    understanding={"acts": [{"act": "decline_offers"}]},
    expect_moves=("acknowledge",),
    expect_text=("Understood. I won't make suggestions.",),
)
ASK_AFTER_DECLINE = JourneyStep(
    message=message("j6-m3", "can you suggest something sold by weight?"),
    understanding=BY_WEIGHT,
    expect_moves=("inform_limitation",),
    expect_text=("You asked me not to make suggestions.",),
)
CHANGE_OF_MIND = JourneyStep(
    message=message("j6-m4", "you can suggest things again"),
    understanding={"acts": [{"act": "accept_offers"}]},
    expect_moves=("acknowledge",),
    expect_text=("Understood. I'll suggest things again when it helps.",),
)
ASK_AFTER_CHANGE = JourneyStep(
    message=message("j6-m5", "can you suggest something sold by weight?"),
    understanding=BY_WEIGHT,
    expect_moves=("recommend",),
    expect_text=("For that, I'd suggest Item C (by weight) at XTS 39.90.",),
)

STEPS = (ASK, DECLINE, ASK_AFTER_DECLINE, CHANGE_OF_MIND, ASK_AFTER_CHANGE)
