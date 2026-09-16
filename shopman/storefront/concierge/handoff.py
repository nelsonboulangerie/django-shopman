"""A única política que decide quando uma fala pede a equipe humana."""

from __future__ import annotations

import re
import unicodedata


def _fold(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(text or "").casefold())
        if not unicodedata.combining(char)
    )


_PATTERNS = (
    ("customer_request", (
        r"\b(?:atendente|atendimento humano)\b",
        r"\b(?:falar|conversar)\s+com\s+(?:um(?:a)?\s+)?"
        r"(?:atendente|alguem|humano|pessoa de verdade|equipe)\b",
        r"\b(?:quero|preciso|prefiro|gostaria|pode|chame|chamar|passar)\b.{0,30}"
        r"\b(?:atendente|atendimento humano|humano|pessoa de verdade|equipe)\b",
    )),
    ("complaint", (
        r"\b(?:reclamacao|reclamar)\b",
        r"\b(?:meu|o|um)\s+(?:pedido|produto|item|pao|doce|croissant)\b.{0,40}"
        r"\b(?:atrasad|cobrad|errad|estragad|faltando|frio|quebrad|queimad|ruim)\w*\b",
        r"\b(?:cobraram|faltou|nao veio|veio errado|chegou atrasado)\b",
    )),
    ("special_order", (
        r"\b(?:encomenda|pedido)\s+(?:especial|personalizad)\w*\b",
        r"\b(?:evento|casamento|festa|aniversario)\b",
        r"\b(?:[2-9]\d|[1-9]\d{2,})\s+(?:pessoas|unidades)\b",
    )),
    ("allergy_review", (
        r"\b(?:alergia|alergic|intolerancia|intolerante|celiac)\w*\b",
        r"\b(?:tem|leva|contem)\s+(?:gluten|lactose)\b",
    )),
)


def classify_handoff_request(text: str) -> str:
    """Retorna uma causa canônica somente quando ela aparece na fala humana."""
    normalized = _fold(text)
    for category, patterns in _PATTERNS:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return category
    return ""
