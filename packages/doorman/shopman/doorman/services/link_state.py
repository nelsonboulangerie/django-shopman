"""Estado efêmero passado de uma sessão web para a criação de um access link.

Fluxo: o site guarda um contexto opaco (ex.: ``{"cart_session_key": ..., "next": ...}``)
sob um código curto de uso único (``NB-XxXx``); o cliente envia esse código pelo
WhatsApp dentro da mensagem ``#menu NB-XxXx``; o External Request do ManyChat repassa
o texto inteiro como ``access_code``; a
``AccessLinkCreateView`` dá ``pop`` no estado e dobra o dict na ``metadata`` do token.

Aqui o dict é **opaco** — quem guarda decide as chaves. Uso único, TTL curto. NUNCA
deve conter PII: o código só carrega contexto (destino + referência de sacola), não
autentica ninguém (a identidade é o número que envia a mensagem no WhatsApp).
"""

from __future__ import annotations

import re
import secrets

from django.core.cache import cache

from ..conf import get_doorman_settings

# Sem caracteres ambíguos (0/O, 1/I) — o código pode ser lido por humano na composição.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CACHE_KEY = "doorman:link_state:{}"


def _prefix() -> str:
    return get_doorman_settings().LINK_STATE_CODE_PREFIX or "NB-"


def _normalize(code: str) -> str:
    return (code or "").strip().upper()


def new_code(length: int = 6) -> str:
    """Gera um código novo com o prefixo configurado (ex.: ``NB-7Q2K9P``)."""
    body = "".join(secrets.choice(_ALPHABET) for _ in range(length))
    return f"{_prefix()}{body}"


def store_state(data: dict, *, ttl_seconds: int | None = None) -> str:
    """Guarda um contexto opaco sob um código novo e devolve o código."""
    ttl = ttl_seconds if ttl_seconds is not None else get_doorman_settings().LINK_STATE_TTL_SECONDS
    code = new_code()
    cache.set(_CACHE_KEY.format(_normalize(code)), dict(data), timeout=ttl)
    return code


def extract_code(raw: str) -> str:
    """Extrai o código de uma string que pode ser o código puro OU a mensagem inteira
    do WhatsApp (ex.: "#menu NB-7Q2K9P"). Assim o ManyChat só precisa
    repassar o texto da mensagem — sem regex do lado dele."""
    norm = _normalize(raw)
    prefix = _normalize(_prefix())
    if not prefix:
        return norm
    match = re.search(re.escape(prefix) + f"[{re.escape(_ALPHABET)}]+", norm)
    return match.group(0) if match else norm


def contains_code(raw: str) -> bool:
    """True quando a mensagem contém um código de estado com o prefixo configurado.

    Isso deixa o ManyChat simples: ele pode repassar ``last_input_text`` sempre. Uma
    entrada orgânica como ``#menu`` não vira tentativa de handoff expirada; já
    ``#menu NB-ABCD23`` continua consumindo o contexto do site.
    """
    norm = _normalize(raw)
    prefix = _normalize(_prefix())
    if not norm:
        return False
    if not prefix:
        return True
    return bool(re.search(re.escape(prefix) + f"[{re.escape(_ALPHABET)}]+", norm))


def pop_state(code: str) -> dict | None:
    """Consome (uso único) o contexto de um código. Aceita o código puro ou a mensagem
    inteira (extrai o código). ``None`` se inválido/expirado."""
    norm = extract_code(code)
    if not norm:
        return None
    key = _CACHE_KEY.format(norm)
    data = cache.get(key)
    if data is None:
        return None
    cache.delete(key)  # uso único
    return data if isinstance(data, dict) else None


# ── A aba de origem entra sozinha ────────────────────────────────────────────
#
# O código viaja do site para o WhatsApp dentro da mensagem que a pessoa envia. Quem
# ENVIA é a identidade; quem GEROU o código é o navegador onde ela estava. Quando o
# código chega, a criação do link libera aquele navegador — e só ele: a liberação fica
# guardada sob a impressão digital da sessão de origem, nunca sob o código. Assim o
# código não é credencial (vazado, não abre nada em outro navegador) e a aba não
# precisa guardar nada: basta perguntar "tem liberação para mim?".

_RELEASE_KEY = "doorman:link_release:{}"
_REVOKE_KEY = "doorman:link_revoke:{}"


def origin_fingerprint(session_key: str) -> str:
    """Impressão digital de uma sessão web. A chave em si nunca vai para o cache."""
    import hashlib

    key = (session_key or "").strip()
    if not key:
        return ""
    return hashlib.sha256(f"doorman-origin:{key}".encode()).hexdigest()


def release_to_origin(origin: str, *, token: str, revoke_ref: str) -> None:
    """Libera a sessão de origem para trocar ``token`` por uma sessão logada."""
    if not origin or not token:
        return
    ttl = get_doorman_settings().LINK_STATE_TTL_SECONDS
    cache.set(_RELEASE_KEY.format(origin), {"token": token, "revoke_ref": revoke_ref}, timeout=ttl)


def pop_release(origin: str) -> dict | None:
    """Consome (uso único) a liberação pendente desta sessão de origem."""
    if not origin:
        return None
    key = _RELEASE_KEY.format(origin)
    data = cache.get(key)
    if data is None:
        return None
    cache.delete(key)
    return data if isinstance(data, dict) else None


def new_revoke_ref() -> str:
    return secrets.token_urlsafe(24)


def store_revocation(ref: str, data: dict) -> None:
    """Guarda o que é preciso para desfazer uma liberação (``origin`` antes da troca;
    ``session_key``/``device_id`` depois dela)."""
    if not ref:
        return
    ttl = get_doorman_settings().LINK_REVOKE_TTL_SECONDS
    cache.set(_REVOKE_KEY.format(ref), dict(data), timeout=ttl)


def get_revocation(ref: str) -> dict | None:
    if not ref:
        return None
    data = cache.get(_REVOKE_KEY.format(ref))
    return data if isinstance(data, dict) else None


def pop_revocation(ref: str) -> dict | None:
    data = get_revocation(ref)
    if data is not None:
        cache.delete(_REVOKE_KEY.format(ref))
    return data
