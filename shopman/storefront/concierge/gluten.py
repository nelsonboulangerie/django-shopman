"""Glúten: a pergunta de alergia que a concierge responde sozinha.

Decisão do dono em 03/10/2026: a resposta sobre glúten é categórica. A casa usa
farinha de trigo em basicamente tudo o que assa, a produção divide o mesmo
espaço e não há nada sem glúten (nem poderia haver, pela contaminação cruzada).

**Uma fonte só.** A concierge não tem texto próprio para isso: ela responde com o
aviso de produção compartilhada da casa (``Shop.food_safety_notice``, decisão do
dono de 08/09), o MESMO que a página de cada produto mostra em Ingredientes e
restrições (``public_information.food_safety_notice``). Quando a pergunta cita um
produto do cardápio, entram também os alérgenos declarados dele, os mesmos do
cartão e da página do produto. O gestor edita o aviso no Admin e a concierge
muda junto. Sem aviso cadastrado não há o que responder: a triagem manda a
pergunta para a equipe, como antes.

As outras alergias continuam com a equipe (D32): o dono decidiu só sobre glúten.

**A regra de segurança.** A resposta nunca afirma que algo é sem glúten e nunca
lista produto como "seguro": ela é o aviso da casa, e os alérgenos de um produto
só aparecem quando foram declarados (lista vazia não vira "não tem"). E só vale
para a pergunta que é SÓ de glúten. Quando a mesma mensagem fala de outra
alergia ("tem glúten ou castanha?", "sou celíaca e alérgica a ovo"), a mensagem
inteira vai para a equipe, como ia antes: responder metade deixaria o cliente
com a impressão de que a outra metade foi respondida, e a equipe responde as
duas de uma vez. Pelo mesmo motivo, "alergia"/"intolerância" sem dizer a quê,
ou dita sobre outra coisa, continua com a equipe.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

#: Quantos produtos citados a resposta detalha, no máximo.
MAX_PRODUCTS = 3


def _words(text: str) -> str:
    folded = "".join(
        char for char in unicodedata.normalize("NFKD", str(text or "").casefold())
        if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded).split())


#: "Glúten" e "celíaco" só aparecem numa conversa de padaria como restrição.
#: "Trigo" sozinho não: "tem pão de trigo integral?" é pergunta de produto. Ele
#: só conta no formato de restrição ("sem trigo", "leva trigo", "alergia a trigo").
_GLUTEN_RES = (
    r"\b(?:gluten\w*|celiac\w*)\b",
    r"\bsem\s+trigo\b",
    r"\b(?:tem|leva|levam|contem|usa|usam)\s+trigo\b",
)

#: "Alergia a glúten", "alérgico ao trigo", "intolerância ao glúten": a alergia
#: que É de glúten. Qualquer outra menção a alergia tira a pergunta daqui.
_ALLERGY_WORD_RE = r"\b(?:alergi\w*|alergic\w*|intoleran\w*|restric\w*)\b"
_GLUTEN_ALLERGY_RE = (
    r"\b(?:alergi\w*|alergic\w*|intoleran\w*|restric\w*)\s+"
    r"(?:(?:a|ao|de|do|com|por|para)\s+)?(?:o\s+)?(?:gluten\w*|trigo)\b"
)

#: As outras alergias e restrições: com qualquer uma delas, a equipe responde.
_OTHER_ALLERGEN_RE = (
    r"\b(?:castanh\w*|noz|nozes|amendo\w*|amendoa\w*|avela\w*|pistach\w*|macadamia\w*|"
    r"pecan|caju|leite|lactose|laticini\w*|lacteo\w*|aplv|caseina|"
    r"ovos?|clara|gema|soja|gergelim|sesamo|mostarda|"
    r"peixes?|frutos?\s+do\s+mar|camarao|crustace\w*|marisco\w*|sulfit\w*|"
    r"tremoco\w*|aipo|salsao|corante\w*|conservante\w*|"
    r"vegan\w*|vegetarian\w*|diabet\w*|fodmap|kosher|halal)\b"
)


def is_gluten_question(text: str) -> bool:
    """A fala pergunta sobre glúten, e SÓ sobre glúten.

    Falso quando ela também fala de outra alergia ou restrição, ou de alergia
    sem dizer que é de glúten: aí a mensagem inteira segue para a equipe.
    """
    words = _words(text)
    if not words:
        return False
    if not any(re.search(pattern, words) for pattern in (*_GLUTEN_RES, _GLUTEN_ALLERGY_RE)):
        return False
    if re.search(_OTHER_ALLERGEN_RE, words):
        return False
    # Toda menção a alergia/intolerância tem que ser a de glúten.
    return len(re.findall(_ALLERGY_WORD_RE, words)) == len(re.findall(_GLUTEN_ALLERGY_RE, words))


def house_notice() -> str:
    """O aviso da casa, da fonte viva; vazio quando não há ou o banco falha."""
    try:
        from shopman.storefront.presentation.public_information import food_safety_notice

        return food_safety_notice()
    except Exception:  # sem aviso legível, a triagem manda para a equipe
        logger.warning("concierge.gluten.notice_failed", exc_info=True)
        return ""


def _join(values) -> str:
    values = [str(value).strip() for value in values if str(value).strip()]
    return values[0] if len(values) == 1 else ", ".join(values[:-1]) + " e " + values[-1]


def cited_products(text: str, *, channel_ref: str) -> list:
    """Os itens do cardápio cujo nome aparece inteiro na fala."""
    from shopman.storefront.presentation.catalog import build_catalog

    try:
        catalog = build_catalog(channel_ref=channel_ref)
    except Exception:
        logger.warning("concierge.gluten.catalog_failed", exc_info=True)
        return []
    words = f" {_words(text)} "
    found = [item for item in catalog.items if _words(item.name) and f" {_words(item.name)} " in words]
    # "Croissant de amêndoas" citado não traz também o "Croissant".
    longest = [
        item for item in found
        if not any(other is not item and f" {_words(item.name)} " in f" {_words(other.name)} " for other in found)
    ]
    return longest[:MAX_PRODUCTS]


def reply_for(text: str, *, channel_ref: str, notice: str | None = None) -> str:
    """O aviso da casa e, se a fala citou produto, os alérgenos declarados dele.

    Vazio quando não há aviso cadastrado: quem chama não responde sozinho.
    """
    from .small_talk import opening_salutation

    notice = house_notice() if notice is None else notice.strip()
    if not notice:
        return ""
    lines = [notice]
    for item in cited_products(text, channel_ref=channel_ref):
        if item.allergens:
            lines.append(f"{item.name} (alérgenos declarados): {_join(item.allergens)}.")
    salutation = opening_salutation(text)
    reply = "\n\n".join(lines)
    return f"{salutation}!\n{reply}" if salutation else reply
