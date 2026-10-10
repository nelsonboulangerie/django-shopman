"""Cumprimento, agradecimento e despedida: a conversa que não é pergunta.

Observação do dono em 03/10/2026: ele deu "bom dia" e a concierge respondeu com
três produtos, a explicação do levain e o aviso de alérgenos. A causa medida no
alpha (mensagem 672, conversa 2): a resposta da concierge é sempre fato de
ferramenta, e o servidor roda a busca pública sobre a fala inteira quando o
modelo não consulta. "Bom dia, tudo bem?" virou busca por "bom", "dia", "tudo" e
"bem", e "bom" casou com "bom para cachorro quente" na descrição de um pão.

Este módulo decide duas coisas, sem rede e sem modelo:

1. **A fala é só cortesia?** (``small_talk_kind``). Então a resposta é curta, na
   voz da casa, e nem o modelo nem a busca são chamados.
2. **O que sobra da fala para buscar** (``strip_small_talk``). "Bom dia, tem
   croissant hoje?" busca "tem croissant hoje", e a resposta abre com o mesmo
   "Bom dia" que o cliente usou (``opening_salutation``).
"""

from __future__ import annotations

import re
import unicodedata

from django.utils import timezone

GREETING, THANKS, FAREWELL = "greeting", "thanks", "farewell"

#: Copy da casa (registro ``OmotenashiCopy``, editável no Admin).
OFFER_COPY_KEY = "CONCIERGE_SMALL_TALK_OFFER"
INTRO_COPY_KEY = "CONCIERGE_SMALL_TALK_INTRO"
THANKS_COPY_KEY = "CONCIERGE_SMALL_TALK_THANKS"
FAREWELL_COPY_KEY = "CONCIERGE_SMALL_TALK_FAREWELL"
HOW_ARE_YOU_COPY_KEY = "CONCIERGE_SMALL_TALK_HOW_ARE_YOU"


def _fold(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", str(text or "").casefold())
        if not unicodedata.combining(char)
    )


_SALUTATIONS = {"bom dia": "Bom dia", "boa tarde": "Boa tarde", "boa noite": "Boa noite"}

_GREETING_RE = r"(?:bom\s+dia|boa\s+tarde|boa\s+noite|oi+|ola+|opa+|hey|eai|e\s+ai|alo)"
#: "Tudo bem?": a pergunta que pede resposta ("tudo ótimo por aqui").
_ASK_RE = (
    r"(?:tudo\s+(?:bem|bom|certo|joia|tranquilo|ok|em\s+ordem)|td\s+(?:bem|bom)|tdb|"
    r"como\s+(?:vai|vao|esta|estao|voce\s+esta|vc\s+esta|voces\s+estao|vcs\s+estao))"
)
_HOW_RE = rf"(?:{_ASK_RE}|(?:e\s+)?(?:com\s+)?(?:voce|vc|voces|vcs)(?:\s+tambem)?)"
_THANKS_RE = (
    r"(?:(?:muito|mt|mto)\s+)?(?:obrigad[oa]s?|obg|brigad[oa]s?|valeu+|vlw|grat[oa]|agradeco)"
    r"(?:\s+(?:mesmo|demais|pela\s+ajuda|pelo\s+atendimento|por\s+tudo))?"
)
_FAREWELL_RE = (
    r"(?:tchau+|ate\s+(?:logo|mais|amanha|breve|a\s+proxima|depois)|"
    r"(?:bom|otimo)\s+(?:fim\s+de\s+semana|domingo|sabado|descanso)|boa\s+semana|"
    r"abracos?|abs|bjs?|beijos?)"
)
#: Palavras de apoio que só existem em volta da cortesia.
_FILLER_RE = r"(?:pessoal|gente|amig[oa]s?|querid[oa]s?|a\s+todos|para\s+voces|pra\s+voces|e|ai|tambem|sim|aqui)"

_KINDS = ((GREETING, _GREETING_RE), (GREETING, _HOW_RE), (THANKS, _THANKS_RE), (FAREWELL, _FAREWELL_RE))


def _words(text: str) -> str:
    """Só letras, números e espaço: pontuação e emoji não mudam a intenção."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _fold(text)).split())


def _sub(pattern: str, text: str) -> tuple[str, bool]:
    out, count = re.subn(rf"\b{pattern}\b", " ", text)
    return " ".join(out.split()), bool(count)


def small_talk_kind(text: str) -> str:
    """``greeting``, ``thanks`` ou ``farewell`` quando a fala é SÓ cortesia; senão vazio.

    Qualquer palavra que sobre ("bom dia, tem pão?") tira a fala daqui: aí ela é
    pergunta e segue para a triagem e as ferramentas.
    """
    rest = _words(text)
    if not rest:
        return ""
    found: set[str] = set()
    for kind, pattern in _KINDS:
        rest, hit = _sub(pattern, rest)
        if hit:
            found.add(kind)
    rest, _ = _sub(_FILLER_RE, rest)
    if rest or not found:
        return ""
    if FAREWELL in found:
        return FAREWELL
    if THANKS in found:
        return THANKS
    return GREETING


def asks_how_are_you(text: str) -> bool:
    return bool(re.search(rf"\b{_ASK_RE}\b", _words(text)))


def strip_small_talk(text: str) -> str:
    """A fala sem cumprimento, agradecimento e despedida, para a busca pública."""
    rest = _words(text)
    for _kind, pattern in _KINDS:
        rest, _ = _sub(pattern, rest)
    return rest


def opening_salutation(text: str) -> str:
    """O "Bom dia"/"Boa tarde"/"Boa noite" que o cliente usou, para devolver igual."""
    words = _words(text)
    for phrase, label in _SALUTATIONS.items():
        if re.search(rf"\b{phrase}\b", words):
            return label
    return ""


def salutation_for_now(now=None) -> str:
    hour = timezone.localtime(now).hour if now is not None else timezone.localtime().hour
    if 5 <= hour < 12:
        return "Bom dia"
    if 12 <= hour < 18:
        return "Boa tarde"
    return "Boa noite"


def reply_for(text: str, *, kind: str, shop_name: str = "", is_first_turn: bool = False, copy=None) -> str:
    """A resposta curta, em uma ou duas frases, na voz da concierge."""
    if copy is None:
        from .service import copy_message as copy

    def fill(key: str) -> str:
        return (copy(key) or "").replace("{shop_name}", shop_name or "a casa").strip()

    if kind == THANKS:
        return fill(THANKS_COPY_KEY)
    if kind == FAREWELL:
        return fill(FAREWELL_COPY_KEY)
    salutation = opening_salutation(text) or salutation_for_now()
    parts = [f"{salutation}!"]
    if asks_how_are_you(text):
        parts.append(fill(HOW_ARE_YOU_COPY_KEY))
    if is_first_turn:
        parts.append(fill(INTRO_COPY_KEY))
    parts.append(fill(OFFER_COPY_KEY))
    return " ".join(part for part in parts if part)
