"""Redação local e determinística antes de persistir captura passiva."""

from __future__ import annotations

import re
from dataclasses import dataclass

from shopman.shop.telemetry_redaction import REDACTED, redact_text


@dataclass(frozen=True)
class RedactedObservation:
    text: str
    categories: tuple[str, ...]


# O boundary canônico remove contatos e segredos comuns. Aqui ficam somente
# formas próprias de fala comercial que precisam ser omitidas do corpus.
_DOMAIN_PATTERNS = (
    (
        "cpf",
        re.compile(r"(?<!\d)\d{3}[.\s-]?\d{3}[.\s-]?\d{3}[-.\s]?\d{2}(?!\d)"),
        "[documento omitido]",
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


def redact_observation_text(value: str) -> RedactedObservation:
    """Remove identificadores e categorias sensíveis sem rede ou IA."""
    text = value
    found: list[str] = []
    for category, pattern, replacement in _DOMAIN_PATTERNS:
        text, count = pattern.subn(replacement, text)
        if count and category not in found:
            found.append(category)

    text = redact_text(text)
    for marker, category in (("[email]", "email"), ("[phone]", "phone"), (REDACTED, "secret")):
        if marker in text and category not in found:
            found.append(category)
    text, url_count = _URL_RE.subn("[link omitido]", text)
    if url_count and "url" not in found:
        found.append("url")
    return RedactedObservation(text=" ".join(text.split()), categories=tuple(found))
