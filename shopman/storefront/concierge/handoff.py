"""A única política que decide quando uma fala pede a equipe humana."""

from __future__ import annotations

import re
import unicodedata


def _fold(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(text or "").casefold())
        if not unicodedata.combining(char)
    )


#: Alérgenos que, citados como ingrediente, pedem a equipe (D32).
_ALLERGENS = (
    r"castanh\w*|nozes|noz|amendoim|amendoas?|avelas?|pistaches?|macadamias?|"
    r"leite|lactose|ovos?|soja|gergelim|sesamo|peixes?|camarao|frutos\s+do\s+mar|mostarda"
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
    # A pergunta só de glúten sai daqui na triagem (dono, 03/10/2026, ``gluten.py``):
    # ela continua reconhecida como alergia, e a triagem decide quem responde.
    ("allergy_review", (
        r"\b(?:alergia|alergic|intolerancia|intolerante|celiac)\w*\b",
        r"\b(?:tem|leva|contem)\s+(?:gluten|lactose)\b",
        # "Tem castanha no panetone?", "leva amendoim?": ingrediente que é alérgeno.
        rf"\b(?:leva|levam|contem)\s+(?:{_ALLERGENS})\b",
        rf"\btem\s+(?:{_ALLERGENS})\s+(?:no|na|nos|nas|em|nesse|nessa|neste|nesta|dentro)\b",
    )),
)


def classify_handoff_request(text: str) -> str:
    """Retorna uma causa canônica somente quando ela aparece na fala humana."""
    normalized = _fold(text)
    for category, patterns in _PATTERNS:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return category
    return ""
