"""Single privacy boundary for logs and external error telemetry.

Observability is not a second data store.  This module deliberately prefers
losing diagnostic detail over leaking customer content, contact data or bearer
material.  Technical request/resource references may remain; values carried by
sensitive fields never do.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

REDACTED = "[redacted]"

_SENSITIVE_KEYS = frozenset({
    "authorization",
    "actor_ref",
    "address_id",
    "body",
    "content",
    "cookie",
    "cookies",
    "cpf",
    "cnpj",
    "customer",
    "customer_data",
    "customer_id",
    "customer_ref",
    "data",
    "device_id",
    "email",
    "endereco",
    "endereço",
    "idempotency_key",
    "ip",
    "ip_address",
    "lat",
    "latitude",
    "lng",
    "longitude",
    "members",
    "name",
    "nome",
    "password",
    "phone",
    "prompt",
    "provider_body",
    "provider_response",
    "raw_error",
    "recipient",
    "request_body",
    "secret",
    "session_key",
    "set_cookie",
    "subscriber_id",
    "subscriber_ref",
    "subject_id",
    "target_key",
    "token",
    "user",
    "user_id",
    "username",
})
_SENSITIVE_KEY_SUFFIXES = (
    "_address",
    "_cpf",
    "_cnpj",
    "_email",
    "_ip",
    "_phone",
    "_session_key",
)
_URL_KEYS = frozenset({"url", "request_url", "source_url"})
_SAFE_SENTRY_HEADERS = frozenset({"content-type", "x-request-id"})

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
_BEARER_RE = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|password|secret|api[_-]?key|authorization)\s*[:=]\s*[^\s,;]+"
)
_PERSONAL_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(customer(?:[_-]?(?:ref|id))?|subscriber(?:[_-]?(?:id|ref))?|"
    r"session[_-]?key|user(?:[_-]?id|name)?|subject[_-]?id|device[_-]?id|"
    r"address[_-]?id|actor[_-]?ref|cpf|cnpj|endere[cç]o|address|lat(?:itude)?|"
    r"l(?:o)?ng(?:itude)?)\s*[:=]\s*[^,;]+"
)
_DOCUMENT_RE = re.compile(
    r"(?<!\d)(?:\d{3}\.?\d{3}\.?\d{3}-?\d{2}|"
    r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)"
)
_URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+")
# Referência de recusa do edge do Akamai (ex.: `Reference #18.1f9ab259.1758275496.3d4e5f6a`).
# Um dos segmentos é um timestamp Unix — dez dígitos seguidos, que o regex de
# telefone captura e substitui por `[phone]`. É referência técnica, não dado de
# pessoa, e é exatamente o que o suporte do iFood usa para achar a regra que
# bloqueou: mutilada, ela não serve para nada. Fica protegida durante a redação
# e volta inteira depois — ver `shopman/shop/services/ifood_http.py`.
# Casa a FORMA da referência (`18.1f9ab259.1758275496.3d4e5f6a`), não as palavras
# em volta: ela aparece ora como `Reference #…` na página do Akamai, ora como
# `referencia=…` no nosso log. Os dois segmentos hexadecimais são o que separa
# essa referência de um telefone — nenhuma corrida de dígitos sozinha casa aqui.
_EDGE_REFERENCE_RE = re.compile(r"\b\d{1,3}\.[0-9a-f]{4,}\.\d{9,11}\.[0-9a-f]{4,}\b")
_EDGE_REFERENCE_SLOT = "\x00ref{}\x00"
# Data ISO (`2026-09-21`) e data-hora (`2026-09-21T14:30:00Z`, `2026-09-21 14:30`)
# têm oito dígitos com hífen — forma que o regex de telefone casa. A mensagem da
# reconciliação financeira chegava ao Sentry como "Reconciliação financeira de
# [phone]", e a data é justamente o que diz qual dia divergiu. Mês e dia são
# validados (01-12, 01-31): uma corrida de dígitos qualquer não ganha passagem.
_ISO_DATE_RE = re.compile(
    r"(?<![\w-])\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"(?:[T ](?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?"
    r"(?![\w-])"
)


def redact_text(value: str) -> str:
    """Remove common PII/secret shapes and URL query/fragment values."""

    # Segredo e bearer vêm ANTES do corte de URL: um `token=` dentro da query
    # precisa deixar o marcador `[redacted]` no texto, porque é por ele que a
    # observação do concierge classifica a redação como `secret`. O regex de URL
    # para em `[`, então o marcador sobrevive ao corte. A atribuição pessoal
    # fica DEPOIS da URL, senão o `[^,;]+` engoliria a URL inteira.
    text = _BEARER_RE.sub(REDACTED, str(value))
    text = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", text)
    text = _URL_RE.sub(lambda match: strip_url_query(match.group(0)), text)
    text = _PERSONAL_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", text)
    text = _EMAIL_RE.sub("[email]", text)
    # A referência do edge (e a data ISO, pelo mesmo motivo) sai de cena antes
    # dos regex de telefone/documento e volta inteira no fim: o timestamp Unix dela é uma corrida de dez dígitos,
    # que o regex de telefone captura por forma. Guardar o trecho é mais seguro
    # que afrouxar o regex — nenhuma outra corrida de dígitos ganha passagem.
    guardadas: list[str] = []

    def _guardar(match: re.Match) -> str:
        guardadas.append(match.group(0))
        return _EDGE_REFERENCE_SLOT.format(len(guardadas) - 1)

    text = _EDGE_REFERENCE_RE.sub(_guardar, text)
    text = _ISO_DATE_RE.sub(_guardar, text)
    text = _PHONE_RE.sub("[phone]", text)
    text = _DOCUMENT_RE.sub("[document]", text)
    for index, original in enumerate(guardadas):
        text = text.replace(_EDGE_REFERENCE_SLOT.format(index), original)
    return text


def strip_url_query(value: str) -> str:
    """Keep scheme, host and PATH; drop userinfo, query and fragment.

    O caminho FICA de propósito. Ele é o que transforma "alguma coisa quebrou"
    em "o webhook do Pix da Efí quebrou" — sem ele o bilhete de erro não paga
    o próprio custo. O que sai é o que carrega segredo por contrato: a query
    (`?token=` da Efí), o fragmento, e o `usuário:senha@` do userinfo, que o
    `netloc` cru levava junto sem ninguém notar.

    Dado pessoal que apareça NO caminho (`/customer/alguem@exemplo.test/`) é
    tratado por `redact_text`, que roda os regex de e-mail, telefone e documento
    sobre o resultado — redigir o trecho, não amputar a rota.
    """

    try:
        split = urlsplit(str(value))
    except (TypeError, ValueError):
        return REDACTED
    if not split.scheme or not split.hostname:
        return str(value).split("?", 1)[0].split("#", 1)[0]
    try:
        port = split.port
    except ValueError:
        return REDACTED
    hostname = split.hostname
    safe_netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        safe_netloc += f":{port}"
    return urlunsplit((split.scheme, safe_netloc, split.path, "", ""))


def redact_observability_value(value: Any, *, key: str = "") -> Any:
    """Recursively sanitize a value before it enters logs or error telemetry."""

    normalized_key = str(key).strip().lower().replace("-", "_")
    if normalized_key in _SENSITIVE_KEYS or normalized_key.endswith(_SENSITIVE_KEY_SUFFIXES):
        return REDACTED
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if normalized_key in _URL_KEYS:
            # Corta userinfo/query/fragmento E redige o que sobrou. Sem o segundo
            # passo, `https://x.test/customer/alguem@exemplo.test/` saía inteiro:
            # o caminho fica de propósito, o dado pessoal dentro dele não.
            return redact_text(strip_url_query(value))
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(nested_key): redact_observability_value(
                nested_value,
                key=str(nested_key),
            )
            for nested_key, nested_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_observability_value(item) for item in value]
    return redact_text(str(value))


def scrub_sentry_event(event: Any) -> Any:
    """Allowlist request metadata and redact every remaining Sentry surface."""

    if not isinstance(event, dict):
        return event

    request = event.get("request")
    if isinstance(request, dict):
        url = request.get("url")
        original_headers = request.get("headers")
        request.clear()
        if isinstance(url, str):
            request["url"] = strip_url_query(url)
        if isinstance(original_headers, Mapping):
            request["headers"] = _safe_headers(original_headers)
    elif request is not None:
        event.pop("request", None)

    # Even with send_default_pii=False, integrations and explicit scope data can
    # repopulate these fields.  Keep the local boundary independent of SDK policy.
    event.pop("user", None)

    for field in tuple(event):
        if field == "request":
            continue
        event[field] = redact_observability_value(event[field], key=field)
    return event


def _safe_headers(headers: Mapping[Any, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in headers.items():
        normalized = str(key).strip().lower()
        if normalized in _SAFE_SENTRY_HEADERS and isinstance(value, str):
            safe[normalized] = redact_text(value)[:200]
    return safe


__all__ = [
    "REDACTED",
    "redact_observability_value",
    "redact_text",
    "scrub_sentry_event",
    "strip_url_query",
]
