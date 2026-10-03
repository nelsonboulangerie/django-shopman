"""Alergia e alérgenos: as perguntas que a concierge responde sozinha.

Decisões do dono: glúten em 03/10/2026 (OBS0310-H) e, no mesmo dia, TODAS as
perguntas de alergia e alérgeno (OBS0310-I), pela mesma fonte única.

**Uma fonte só.** A concierge não tem texto próprio sobre alérgeno: ela responde
com o aviso de produção compartilhada da casa (``Shop.food_safety_notice``,
decisão do dono de 08/09), o MESMO que a página de cada produto mostra em
Ingredientes e restrições (``public_information.food_safety_notice``), e, quando
a pergunta cita um produto do cardápio, com os alérgenos declarados dele (os
mesmos do cartão e da página do produto). O gestor edita o aviso no Admin e a
concierge muda junto. O aviso de hoje cobre glúten e traços de leite, ovos,
castanha-do-brasil, castanha de caju, gergelim e pimenta-do-reino. A copy que é
só da concierge (a oferta da equipe, a pergunta "a quê?" e as linhas de produto)
vive em Copy Omotenashi, editável no Admin.

**As regras de segurança**, todas a favor de quem tem alergia:

- Nunca afirma ausência ("não tem castanha", "sem leite"): a resposta é o aviso e
  os alérgenos declarados, e só.
- Produto citado sem alérgeno declarado não vira "seguro": a linha dele diz que
  não há lista cadastrada e que vale o aviso (pode conter traços).
- Nada é listado como "pode comer": "sou alérgico a ovo, o que posso comer?"
  recebe o aviso, não um cardápio.
- Alergia sem dizer a quê ("tenho alergia") recebe a pergunta "a quê?". Se a
  resposta seguinte ainda não disser, vai para a equipe.
- Alérgeno de que nenhuma das duas fontes fala (o aviso não cita soja nem
  amendoim, e o produto citado não os declara) vai para a equipe: responder só
  com o aviso deixaria o cliente deduzir uma ausência que ninguém afirmou. O
  mesmo para restrição que não é alérgeno (vegano, diabetes, kosher).
- Reação alérgica, pessoa passando mal: equipe, sempre (``handoff.py`` classifica
  como reclamação, antes de chegar aqui).
- Sem aviso cadastrado, nada é respondido: a triagem manda para a equipe.
- Toda resposta termina oferecendo a equipe para alergia grave; "sim" logo depois
  chama a equipe.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: Quantos produtos citados a resposta detalha, no máximo.
MAX_PRODUCTS = 3

#: O que a triagem grava em ``answered_by`` (``data-schemas.md``).
NOTICE = "allergy_notice"
NOTICE_AFTER_ASK = "allergy_notice_after_ask"
ASK_WHICH = "allergy_ask_which"
ANSWERED_BY = frozenset({NOTICE, NOTICE_AFTER_ASK, ASK_WHICH})

#: A resposta do cliente que aceita a oferta da equipe vira ``escalated_by``.
OFFER_ACCEPTED = "allergy_offer_accepted"

#: Copy da casa (registro ``OmotenashiCopy``, editável no Admin).
TEAM_OFFER_COPY_KEY = "CONCIERGE_ALLERGY_TEAM_OFFER"
ASK_WHICH_COPY_KEY = "CONCIERGE_ALLERGY_ASK_WHICH"
PRODUCT_DECLARED_COPY_KEY = "CONCIERGE_ALLERGY_PRODUCT_DECLARED"
PRODUCT_UNDECLARED_COPY_KEY = "CONCIERGE_ALLERGY_PRODUCT_UNDECLARED"

# Classificação de uma fala.
ANSWER = "answer"  # responde com o aviso e os alérgenos declarados
ASK = "ask_which"  # pergunta a que é a alergia
TEAM = "team"  # a equipe responde (alérgeno fora das fontes, restrição)


def _words(text: str) -> str:
    folded = "".join(
        char for char in unicodedata.normalize("NFKD", str(text or "").casefold())
        if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded).split())


#: (alérgeno, como o cliente fala, como as fontes escrevem). A ordem importa: o
#: específico ("castanha de caju") sai da fala antes do genérico ("castanha").
#: "Como as fontes escrevem" casa no aviso da casa e nos alérgenos declarados
#: do produto citado (o vocabulário de ``attribute_defaults.ALERGENOS_CANONICOS``).
_ALLERGENS: tuple[tuple[str, str, str], ...] = (
    ("glúten", r"gluten\w*|celiac\w*|trigo|farinha", r"gluten|trigo"),
    ("centeio", r"centeio", r"centeio"),
    ("cevada", r"cevada|malte", r"cevada"),
    ("aveia", r"aveia", r"aveia"),
    ("leite", r"leites?|lactose|laticini\w*|lacte\w*|aplv|caseina", r"leite|lactose"),
    ("ovos", r"ovos?", r"ovo"),
    ("castanha-do-brasil", r"castanhas?\s+do\s+(?:brasil|para)", r"castanha\s+do\s+(?:brasil|para)"),
    ("castanha de caju", r"(?:castanhas?\s+de\s+)?caju", r"caju"),
    ("amendoim", r"amendoi\w*", r"amendoim"),
    ("amêndoa", r"amendoas?", r"amendoa"),
    ("avelã", r"avelas?", r"avela"),
    ("nozes", r"noz|nozes", r"noz"),
    ("pistache", r"pistaches?", r"pistache"),
    ("macadâmia", r"macadamias?", r"macadamia"),
    ("pecã", r"nozes?\s+peca|pecan", r"peca|pecan"),
    ("pinoli", r"pinoli|pinhao|pinhoes", r"pinoli"),
    ("castanhas", r"castanh\w*|oleaginos\w*", r"castanh"),
    ("gergelim", r"gergelim|sesamo|tahine|tahini", r"gergelim|sesamo"),
    ("soja", r"soja", r"soja"),
    ("peixes", r"peixes?", r"peixe"),
    ("crustáceos", r"crustace\w*|camar\w*|frutos?\s+do\s+mar|marisco\w*", r"crustace|camarao|frutos do mar"),
    ("mostarda", r"mostarda", r"mostarda"),
    ("sulfitos", r"sulfit\w*", r"sulfit"),
    ("pimenta-do-reino", r"pimenta(?:\s+do\s+reino)?", r"pimenta"),
    ("látex", r"latex", r"latex"),
)

#: Nome de produto que contém a palavra de um alérgeno sem perguntar dele:
#: "tem ovos de Páscoa?" é pergunta de produto. Sai da fala antes da leitura.
_PRODUCT_NAMES_RE = (
    r"\bovos?\s+de\s+pascoa\b|\bpao\s+de\s+leite\b|\bdoce\s+de\s+leite\b|"
    r"\bleite\s+condensado\b|\bcafe\s+com\s+leite\b|\bsuco\s+de\s+caju\b"
)

#: Restrição que não é alérgeno: nenhuma das duas fontes responde, vai para a equipe.
_OTHER_RESTRICTION_RE = (
    r"\b(?:vegan\w*|vegetarian\w*|diabet\w*|fodmap|kosher|halal|corante\w*|conservante\w*)\b"
)

#: A alergia da PESSOA ("tenho alergia", "sou intolerante"): sem dizer a quê,
#: a concierge pergunta.
_PERSONAL_ALLERGY_RE = r"\b(?:alergi\w*|alergic\w*|intoleran\w*|restric\w*)\b"

#: Pergunta sobre alérgenos do produto, sem alergia pessoal: "quais os
#: alérgenos do croissant?", "tem traços de quê?".
_ALLERGEN_TOPIC_RE = r"\b(?:alergeno\w*|tracos?|contaminac\w*)\b"


def _asks_about(pattern: str) -> str:
    """A pergunta sobre o alérgeno, nos formatos em que ela vem."""
    return (
        rf"\b(?:sem|tem|leva|levam|contem|usa|usam|vai|vem|feito\s+com|feita\s+com|tracos?\s+de)\s+"
        rf"(?:(?:a|o|um|uma|algum|alguma)\s+)?(?:{pattern})\b"
    )


@dataclass(frozen=True)
class Reading:
    """O que a fala pergunta sobre alergia."""

    kind: str
    allergens: tuple[str, ...] = field(default_factory=tuple)


def _named_allergens(words: str) -> tuple[list[tuple[str, str]], str]:
    """Os alérgenos citados ((nome, como as fontes escrevem)) e a fala que sobrou."""
    found = []
    rest = f" {words} "
    for name, spoken, written in _ALLERGENS:
        rest, count = re.subn(rf"\b(?:{spoken})\b", " ", rest)
        if count:
            found.append((name, written))
    return found, rest


def read(text: str) -> Reading | None:
    """A fala é sobre alergia? Então como a concierge a trata; senão, None.

    Não decide sobre reação alérgica nem pedido de pessoa: a triagem já os
    mandou para a equipe pela regra (``handoff.py``). Também não confere as
    fontes: ``covered`` faz isso, com o aviso e o produto citado em mãos.
    """
    words = re.sub(_PRODUCT_NAMES_RE, " ", _words(text))
    if not words.strip():
        return None
    personal = bool(re.search(_PERSONAL_ALLERGY_RE, words))
    topic = bool(re.search(_ALLERGEN_TOPIC_RE, words))
    # "Glúten" e "celíaco" só aparecem numa padaria como restrição. Os outros
    # alérgenos contam quando perguntados ("tem castanha", "sem leite"):
    # "tem pão de trigo integral?" e "quero um café com leite" são pedido.
    gluten = bool(re.search(r"\b(?:gluten\w*|celiac\w*)\b", words))
    asked = any(re.search(_asks_about(spoken), words) for _name, spoken, _written in _ALLERGENS)
    if not (personal or topic or gluten or asked):
        return None
    named, _rest = _named_allergens(words)
    names = tuple(name for name, _written in named)
    if re.search(_OTHER_RESTRICTION_RE, words):
        return Reading(TEAM, names)
    if personal and not named:
        return Reading(ASK)
    return Reading(ANSWER, names)


def covered(text: str, *, notice: str, products=()) -> bool:
    """Cada alérgeno citado aparece no aviso ou nos alérgenos declarados citados."""
    named, _rest = _named_allergens(re.sub(_PRODUCT_NAMES_RE, " ", _words(text)))
    sources = " ".join(
        [_words(notice), *(_words(allergen) for item in products for allergen in item.allergens)]
    )
    return all(re.search(rf"\b(?:{written})", sources) for _name, written in named)


def house_notice() -> str:
    """O aviso da casa, da fonte viva; vazio quando não há ou o banco falha."""
    try:
        from shopman.storefront.presentation.public_information import food_safety_notice

        return food_safety_notice()
    except Exception:  # sem aviso legível, a triagem manda para a equipe
        logger.warning("concierge.allergens.notice_failed", exc_info=True)
        return ""


def cited_products(text: str, *, channel_ref: str) -> list:
    """Os itens do cardápio cujo nome aparece inteiro na fala."""
    from shopman.storefront.presentation.catalog import build_catalog

    try:
        catalog = build_catalog(channel_ref=channel_ref)
    except Exception:
        logger.warning("concierge.allergens.catalog_failed", exc_info=True)
        return []
    words = f" {_words(text)} "
    found = [item for item in catalog.items if _words(item.name) and f" {_words(item.name)} " in words]
    # "Croissant de amêndoas" citado não traz também o "Croissant".
    longest = [
        item for item in found
        if not any(other is not item and f" {_words(item.name)} " in f" {_words(other.name)} " for other in found)
    ]
    return longest[:MAX_PRODUCTS]


def decision(text: str, *, channel_ref: str) -> str:
    """Para a triagem: ``answered_by`` quando a concierge responde, ``team`` ou vazio.

    Vazio quando a fala não é sobre alergia (a triagem segue como sempre).
    ``team`` quando é, e a concierge não pode responder: sem aviso cadastrado,
    restrição que não é alérgeno ou alérgeno de que as fontes não falam.
    """
    reading = read(text)
    if reading is None:
        return ""
    notice = house_notice()
    if not notice or reading.kind == TEAM:
        return TEAM
    if reading.kind == ASK:
        return ASK_WHICH
    products = cited_products(text, channel_ref=channel_ref)
    return NOTICE if covered(text, notice=notice, products=products) else TEAM


def decision_after_ask(text: str, *, earlier: str, channel_ref: str) -> str:
    """A resposta à pergunta "a quê?": responde se agora disse; senão, equipe."""
    combined = f"{earlier}\n{text}"
    if not _named_allergens(_words(text))[0]:
        return TEAM
    found = decision(combined, channel_ref=channel_ref)
    return NOTICE_AFTER_ASK if found == NOTICE else TEAM


_ACCEPT_RE = (
    r"(?:sim|s|quero|pode|claro|por\s+favor|pf|pfv|grave|e\s+grave|muito\s+grave|"
    r"preciso|chama|chame)"
)


def accepts_team_offer(text: str) -> bool:
    """"Sim", "quero", "pode chamar", "é grave": a resposta à oferta da equipe."""
    words = _words(text)
    return bool(words) and bool(
        re.fullmatch(rf"(?:{_ACCEPT_RE})(?:\s+(?:{_ACCEPT_RE}|sim|chamar|alguem|equipe|obrigad\w*))*", words)
    )


def _join(values) -> str:
    values = [str(value).strip() for value in values if str(value).strip()]
    return values[0] if len(values) == 1 else ", ".join(values[:-1]) + " e " + values[-1]


def reply_for(text: str, *, channel_ref: str, notice: str | None = None, copy=None) -> str:
    """Os alérgenos declarados do produto citado, o aviso da casa e a oferta da equipe.

    Vazio quando não há aviso cadastrado: quem chama não responde sozinho.
    """
    from .small_talk import opening_salutation

    if copy is None:
        from .service import copy_message as copy
    notice = house_notice() if notice is None else notice.strip()
    if not notice:
        return ""
    lines = []
    for item in cited_products(text, channel_ref=channel_ref):
        if item.allergens:
            line = (copy(PRODUCT_DECLARED_COPY_KEY) or "").replace("{allergens}", _join(item.allergens))
        else:
            line = copy(PRODUCT_UNDECLARED_COPY_KEY) or ""
        line = line.replace("{product}", item.name).strip()
        if line:
            lines.append(line)
    lines.append(notice)
    offer = (copy(TEAM_OFFER_COPY_KEY) or "").strip()
    if offer:
        lines.append(offer)
    salutation = opening_salutation(text)
    reply = "\n\n".join(lines)
    return f"{salutation}!\n{reply}" if salutation else reply


def ask_which(text: str, *, copy=None) -> str:
    """A pergunta "a que é a alergia?", com o mesmo bom dia do cliente."""
    from .small_talk import opening_salutation

    if copy is None:
        from .service import copy_message as copy
    question = (copy(ASK_WHICH_COPY_KEY) or "").strip()
    salutation = opening_salutation(text)
    return f"{salutation}! {question}" if salutation and question else question
