"""Redação local e determinística antes de persistir captura passiva."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass

from shopman.shop.telemetry_redaction import REDACTED, redact_text


@dataclass(frozen=True)
class RedactedObservation:
    text: str
    categories: tuple[str, ...]


#: O que o dono lê no lugar do contato. O boundary de telemetria (logs, Sentry) segue com
#: ``[email]`` e ``[phone]``; na fala de cliente que aparece em tela, tudo em português.
PHONE_PLACEHOLDER = "[telefone omitido]"
EMAIL_PLACEHOLDER = "[e-mail omitido]"

# O boundary canônico remove contatos e segredos comuns. Aqui ficam somente
# formas próprias de fala comercial que precisam ser omitidas do corpus.
_DOMAIN_PATTERNS = (
    (
        "cpf",
        re.compile(r"(?<!\d)\d{3}[.\s-]?\d{3}[.\s-]?\d{3}[-.\s]?\d{2}(?!\d)"),
        "[documento omitido]",
    ),
    (
        # Telefone com o DDD entre parênteses ("(11) 98765-4321", "+55 (43) 3025-1234"): o
        # boundary de telemetria começa no primeiro dígito e deixava o "(" para trás.
        "phone",
        re.compile(r"(?:\+?\d{2}\s*)?\(\s*\d{2}\s*\)\s*\d{4,5}[\s.-]?\d{4}(?!\d)"),
        PHONE_PLACEHOLDER,
    ),
    (
        "numeric_identifier",
        re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
        "[número identificador omitido]",
    ),
    (
        "financial",
        re.compile(
            r"\b(?:pix|cart[aã]o|senha|password)\s*(?:é|e|:|=)?\s*[^,;.!?\n]+",
            re.IGNORECASE,
        ),
        "[dado financeiro ou segredo omitido]",
    ),
    (
        "address",
        re.compile(
            r"\b(?:rua|r\.|avenida|av\.|alameda|travessa|rodovia)\s+[^,;.!?\n]+(?:,\s*\d+[\w/-]*)?",
            re.IGNORECASE,
        ),
        "[endereço omitido]",
    ),
    (
        "order_reference",
        re.compile(r"\b(?:pedido|order)\s*(?:n[ºo°.]*)?\s*[:#-]?\s*[A-Z0-9-]{4,}\b", re.IGNORECASE),
        "[pedido omitido]",
    ),
    (
        "health",
        re.compile(
            r"\b(?:tenho|estou com|diagn[oó]stico de)\s+(?:diabetes|c[aâ]ncer|hiv|aids|depress[aã]o|ansiedade|doen[cç]a\s+[^,;.!?\n]+)",
            re.IGNORECASE,
        ),
        "[condição de saúde omitida]",
    ),
    (
        "health",
        re.compile(r"\b(?:al[eé]rgic[oa]s?|alergia)\s+(?:a|de)?\s*[^,;.!?\n]+", re.IGNORECASE),
        "[alergia: detalhe omitido]",
    ),
    (
        "sensitive_belief",
        re.compile(
            r"\b(?:minha religi[aã]o|sou (?:cat[oó]lic[oa]|evang[eé]lic[oa]|judeu|judia|mu[cç]ulman[oa])|meu voto|sou filiad[oa])\b[^,;.!?\n]*",
            re.IGNORECASE,
        ),
        "[dado sensível omitido]",
    ),
    (
        "minor",
        re.compile(r"\b(?:meu|minha)\s+(?:filh[oa]|crian[cç]a)\s+(?:de\s+)?\d{1,2}\s+anos\b", re.IGNORECASE),
        "[referência a menor omitida]",
    ),
)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

# ── Nome ──────────────────────────────────────────────────────────────
#
# Duas redes (WP-03 do plano da Concierge). A primeira é o padrão de quem se
# apresenta ("aqui é a Maria Souza", "meu nome é", "sou a", assinatura no fim).
# A segunda são os nomes que a casa já conhece da conversa (``customer_name``):
# pegam "Maria aqui" e o nome solto, que padrão nenhum pega sem apagar produto.
# A categoria ``name`` fica FORA do ``_DOMAIN_PATTERNS``: o cartão da equipe
# (``triage._redacted``) continua lendo o nome.

NAME_PLACEHOLDER = "[nome omitido]"
_UPPER = "A-ZÀ-ÖØ-Þ"
_LOWER = "a-zß-öø-ÿ"
_CAPITALIZED = rf"[{_UPPER}][{_LOWER}]+"
_ANY_WORD = rf"[{_UPPER}{_LOWER}]{{2,}}"
#: Sobrenomes: palavra com maiúscula, com "da/de/do/dos/das" no meio.
_SURNAMES = rf"(?:\s+(?:(?:d[aeo]s?)\s+)?{_CAPITALIZED}){{0,3}}"
_NAME_PATTERNS = (
    # "meu nome é maria", "me chamo Maria": gatilho forte, aceita minúscula.
    re.compile(
        rf"(?i:\b(?:meu\s+nome\s+(?:é|e)|me\s+chamo))\s+(?:(?i:[ao])\s+)?{_ANY_WORD}{_SURNAMES}"
    ),
    # "aqui é a Maria", "sou a Maria Souza", "fala o João": gatilho fraco, só com maiúscula,
    # para "sou alérgica", "aqui é a padaria?" e "sou cliente" não perderem o sentido.
    re.compile(
        rf"(?i:\b(?:aqui\s+(?:é|e)|sou|fala|quem\s+fala\s+(?:é|e)))\s+(?:(?i:[ao])\s+)?{_CAPITALIZED}{_SURNAMES}"
    ),
    # Assinatura no fim: "obrigada, Maria Souza", "att. Maria", "- Maria".
    re.compile(
        rf"(?:(?i:\b(?:obrigad[ao]|grat[ao]|att|atenciosamente|abs|abra[cç]os|bjs|beijos))[.,!]?\s*,?|\s[-–]\s*)"
        rf"\s*{_CAPITALIZED}{_SURNAMES}\s*[.!]*\s*$"
    ),
)
_NAME_LEAD = re.compile(
    r"^(?i:(?:meu\s+nome\s+(?:é|e)|me\s+chamo|aqui\s+(?:é|e)|quem\s+fala\s+(?:é|e)|sou|fala"
    r"|obrigad[ao]|grat[ao]|att|atenciosamente|abs|abra[cç]os|bjs|beijos)[.,!]?\s*,?\s*(?:[ao]\s+)?|\s[-–]\s*)"
)
#: Palavra de produto da casa antes do nome conhecido: "pão Maria", "bolo Helena"
#: são produto, e o nome do cliente não apaga o catálogo.
_PRODUCT_NOUNS = frozenset({
    "pão", "pao", "pães", "paes", "bolo", "bolos", "torta", "tortas", "broa", "broas", "biscoito",
    "biscoitos", "rosca", "roscas", "sonho", "sonhos", "doce", "doces", "café", "cafe", "croissant",
    "brioche", "baguete", "sanduíche", "sanduiche", "salada", "quiche", "cookie", "cookies", "geleia",
    "queijo", "chá", "cha", "suco", "pudim", "mousse", "tartelete", "panetone", "focaccia", "ciabatta",
})
_NAME_CONNECTORS = frozenset({"da", "de", "do", "das", "dos", "e"})

_known_names: ContextVar[tuple[str, ...]] = ContextVar("concierge_known_names", default=())


def bind_known_names(*names: str) -> Token:
    """Os nomes que a casa conhece desta conversa passam a sair de todo texto redigido.

    ``service.run_turn`` liga com o ``customer_name`` da conversa no começo do turno e
    solta no fim (``release_known_names``): o Jev (``triage.jev_scores``) e a leitura de
    partes recebem a fala sem o nome, sem que a triagem precise saber dele.
    """
    return _known_names.set(tuple(name for name in names if str(name or "").strip()))


def release_known_names(token: Token) -> None:
    _known_names.reset(token)


@contextmanager
def known_names(*names: str) -> Iterator[None]:
    """``bind_known_names`` num bloco ``with``."""
    token = bind_known_names(*names)
    try:
        yield
    finally:
        release_known_names(token)


def _name_tokens(names: Iterable[str]) -> list[str]:
    """O nome inteiro primeiro, depois cada palavra de três letras ou mais."""
    full: list[str] = []
    words: list[str] = []
    for name in names:
        clean = " ".join(str(name or "").split())
        if not clean:
            continue
        if " " in clean:
            full.append(clean)
        for word in clean.split(" "):
            if len(word) >= 3 and word.casefold() not in _NAME_CONNECTORS and not any(c.isdigit() for c in word):
                words.append(word)
    unique = list(dict.fromkeys([*sorted(full, key=len, reverse=True), *sorted(words, key=len, reverse=True)]))
    return unique


def _redact_known_names(text: str, names: Iterable[str]) -> tuple[str, int]:
    total = 0
    for token in _name_tokens(names):
        source = text
        pattern = re.compile(rf"(?<![\w])({re.escape(token)})(?![\w])", re.IGNORECASE)

        def _replace(match: re.Match, source: str = source) -> str:
            before = source[: match.start()].rstrip().rsplit(" ", 1)[-1].casefold()
            if before in _PRODUCT_NOUNS:
                return match.group(0)
            return NAME_PLACEHOLDER

        text = pattern.sub(_replace, source)
        if text != source:
            total += 1
    return text, total


def _redact_name_patterns(text: str) -> tuple[str, int]:
    total = 0
    for pattern in _NAME_PATTERNS:
        def _replace(match: re.Match) -> str:
            lead = _NAME_LEAD.match(match.group(0))
            kept = match.group(0)[: lead.end()] if lead else ""
            return f"{kept}{NAME_PLACEHOLDER}"

        text, count = pattern.subn(_replace, text)
        total += count
    return text, total


def redact_observation_text(value: str, *, names: Iterable[str] = ()) -> RedactedObservation:
    """Remove identificadores e categorias sensíveis sem rede ou IA.

    ``names``: nomes conhecidos da conversa (o ``customer_name``), somados aos do
    bloco ``known_names`` em curso.
    """
    text = value
    found: list[str] = []
    text, patterned = _redact_name_patterns(text)
    text, named = _redact_known_names(text, [*names, *_known_names.get()])
    if named or patterned:
        found.append("name")
    for category, pattern, replacement in _DOMAIN_PATTERNS:
        text, count = pattern.subn(replacement, text)
        if count and category not in found:
            found.append(category)

    text = redact_text(text)
    for marker, category in (("[email]", "email"), ("[phone]", "phone"), (REDACTED, "secret")):
        if marker in text and category not in found:
            found.append(category)
    text = text.replace("[email]", EMAIL_PLACEHOLDER).replace("[phone]", PHONE_PLACEHOLDER)
    text, url_count = _URL_RE.subn("[link omitido]", text)
    if url_count and "url" not in found:
        found.append("url")
    return RedactedObservation(text=" ".join(text.split()), categories=tuple(found))
