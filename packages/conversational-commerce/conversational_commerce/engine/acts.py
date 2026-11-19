"""A lista fechada de atos, o leitor por regra local e o que cada ato pede.

O leitor (modelo ou regra) só devolve atos desta lista; ato fora dela vira
``unknown`` e a queda é registrada (K05). A regra local de risco SOMA atos, e o
modelo nunca os tira (v2 5.3, passo 3). As palavras das regras são dado da casa
(``LocalRules``); as do pacote são um vocabulário de teste neutro.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

ACTS: tuple[str, ...] = (
    "greet",
    "thank",
    "ask_hours",
    "ask_price",
    "ask_item",
    "change_quantity",
    "place_order",
    "cancel_order",
    "complain",
    "request_human",
    "ask_recommendation",
    "decline_offers",
    "accept_offers",
    "affirm",
    "deny",
    "unknown",
)
COURTESY_ACTS = frozenset({"greet", "thank"})
ANSWER_ACTS = frozenset({"affirm", "deny"})
# O cliente declara o que quer da casa: vira memória declarada (F10), e a resposta é cortesia.
DECLARATION_ACTS = frozenset({"decline_offers", "accept_offers"})
QUERY_ACTS = frozenset({"ask_hours", "ask_price", "ask_item"})
CHANGE_ACTS = frozenset({"change_quantity", "place_order", "cancel_order"})


@dataclass(frozen=True, slots=True)
class LocalRules:
    """Regras locais por palavra, sem modelo: o portão do passo 2 e a queda do passo 3.

    ``acts``: ato → padrões (regex, sem diferenciar maiúsculas).
    ``risk``: padrões que SOMAM um ato de risco (``complain``), qualquer que seja o leitor.
    """

    acts: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    risk: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for act in (*self.acts, *self.risk):
            if act not in ACTS:
                raise ValueError(f"regra local para ato fora da lista: {act!r}")

    def read(self, text: str) -> tuple[str, ...]:
        return tuple(act for act, patterns in self.acts.items()
                     if any(re.search(p, text, re.IGNORECASE) for p in patterns))

    def risk_acts(self, text: str) -> tuple[str, ...]:
        return tuple(act for act, patterns in self.risk.items()
                     if any(re.search(p, text, re.IGNORECASE) for p in patterns))


# Vocabulário neutro de teste. A casa troca pelo dela, na língua dela.
TEST_RULES = LocalRules(
    acts={
        "greet": (r"\bhello\b", r"\bhi\b"),
        "thank": (r"\bthanks?\b", r"\bthank you\b"),
        "ask_hours": (r"\bhours?\b", r"\bopen\b"),
        "ask_price": (r"\bprice\b", r"\bhow much\b", r"\bcost\b"),
        "change_quantity": (r"\bmake it\b", r"\bchange\b"),
        "place_order": (r"\bplace (the |my )?order\b", r"\bcheck ?out\b"),
        "cancel_order": (r"\bcancel\b",),
        "affirm": (r"^\s*(yes|yeah|ok)\b",),
        "deny": (r"^\s*no\b",),
        "request_human": (r"\b(talk|speak) to (a |an )?(person|human|someone)\b",),
        "ask_recommendation": (r"\bcan you (suggest|recommend)\b", r"\bwhat do you recommend\b"),
        "decline_offers": (r"\bno (more )?suggestions\b", r"\bstop suggesting\b"),
        "accept_offers": (r"\byou can suggest\b",),
    },
    risk={"complain": (r"\bcomplain", r"\bwrong order\b", r"\brefund\b")},
)


def only_courtesy(acts: Iterable[str]) -> bool:
    acts = set(acts)
    return bool(acts) and acts <= COURTESY_ACTS


def validate(acts: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(atos válidos, atos recusados por estarem fora da lista)."""
    good, refused = [], []
    for act in acts:
        (good if act in ACTS else refused).append(act)
    return tuple(dict.fromkeys(good)), tuple(refused)
