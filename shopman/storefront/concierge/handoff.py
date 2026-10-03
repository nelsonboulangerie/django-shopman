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
        r"\b(?:avise|avisa|chame|chama|chamar|falar\s+com)\s+(?:o\s+|a\s+|os\s+|as\s+|seu\s+|seus\s+|sua\s+|suas\s+)?"
        r"(?:superior\w*|gerente|responsavel|dono|dona)\b",
    )),
    ("complaint", (
        r"\b(?:reclamacao|reclamar)\b",
        r"\b(?:meu|o|um)\s+(?:pedido|produto|item|pao|doce|croissant)\b.{0,40}"
        r"\b(?:atrasad|cobrad|errad|estragad|faltando|frio|quebrad|queimad|ruim)\w*\b",
        r"\b(?:cobraram|faltou|nao veio|veio errado|chegou atrasado)\b",
        # Pix ou link de pagamento que não funcionou (dono, 03/10/2026, regra R4):
        # quem resolve pagamento é a equipe.
        r"\b(?:pix|link|qr\s*code|codigo|pagamento|pagto|cartao)\b.{0,30}"
        r"\bnao\s+(?:funciona|funcionou|abre|abriu|carrega|carregou|foi|passou|caiu|aparece|apareceu|deu\s+certo)\b",
        r"\bnao\s+(?:consegui|consigo|deu\s+para|deu\s+pra)\s+pagar\b",
        r"\bpagamento\s+(?:recusado|negado|deu\s+erro|com\s+erro)\b",
        # Desistência pela taxa de entrega (dono, 03/10/2026, regra R4).
        r"\b(?:desist\w*|outro\s+lugar|nao\s+compensa|deixa\s+(?:pra|para)\s+la|esquece)\b.{0,60}"
        r"\b(?:taxa|frete)\b",
        r"\b(?:taxa|frete)\b.{0,60}\b(?:desist\w*|outro\s+lugar|nao\s+compensa|absurd\w*|"
        r"(?:muito|mt|mto|bem)\s+(?:cara|caro|alta|alto|salgad\w*))\b",
        # Reação alérgica, alguém passando mal: equipe, sempre (dono, 03/10/2026).
        # Vence a resposta automática de alergia (``allergens.py``).
        r"\b(?:reac(?:ao|oes)|reagiu|reagi|anafila\w*|urticaria|empolou|empolad\w*|inchou|inchad\w*)\b",
        r"\b(?:passou|passei|passando|passaram|esta passando|ficou|fiquei)\s+mal\b",
        r"\b(?:tive|teve|tiveram|deu|deram|me\s+deu|causou|deu\s+uma)\s+(?:uma\s+)?(?:alergia|crise)\b",
        r"\b(?:hospital|pronto\s+socorro|emergencia|falta\s+de\s+ar|vomit\w*)\b",
    )),
    ("special_order", (
        r"\b(?:encomenda|pedido)\s+(?:especial|personalizad)\w*\b",
        r"\b(?:evento|casamento|festa|aniversario)\b",
        r"\b(?:[2-9]\d|[1-9]\d{2,})\s+(?:pessoas|unidades)\b",
    )),
    # A pergunta de alergia que as fontes da casa respondem sai daqui na triagem
    # (dono, 03/10/2026, ``allergens.py``): ela continua reconhecida como
    # alergia, e a triagem decide quem responde.
    ("allergy_review", (
        r"\b(?:alergia|alergic|intolerancia|intolerante|celiac)\w*\b",
        r"\b(?:tem|leva|contem)\s+(?:gluten|lactose)\b",
        # "Tem castanha no panetone?", "leva amendoim?": ingrediente que é alérgeno.
        rf"\b(?:leva|levam|contem)\s+(?:{_ALLERGENS})\b",
        rf"\btem\s+(?:{_ALLERGENS})\s+(?:no|na|nos|nas|em|nesse|nessa|neste|nesta|dentro)\b",
    )),
    # Cancelar um pedido (regra R4): a equipe cancela, o bot não. "Cancela" solto
    # depende do que a casa disse antes e fica com a conversa.
    ("order_cancel", (
        r"\bcancel\w*\b.{0,40}\b(?:pedido|encomenda|compra|reserva)\b",
        r"\b(?:pedido|encomenda|compra|reserva)\b.{0,40}\bcancel\w*\b",
    )),
)


#: As causas que a regra da casa R4 manda para a equipe (``house_rules.py``).
TEAM_CATEGORIES = frozenset({"customer_request", "complaint", "order_cancel"})


def classify_handoff_request(text: str) -> str:
    """Retorna uma causa canônica somente quando ela aparece na fala humana."""
    normalized = _fold(text)
    for category, patterns in _PATTERNS:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return category
    return ""
