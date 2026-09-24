"""iFood OAuth — serviço de token (client_credentials) para as APIs Merchant/Order/Catalog.

Contrato verificado ao vivo (2026-06-30):
``POST {base}/authentication/v1.0/oauth/token``, body form-urlencoded
``grantType=client_credentials`` + ``clientId`` + ``clientSecret`` → ``{"accessToken", "expiresIn"}``
(~6h). ⚠️ O WAF do iFood bloqueia User-Agent genérico (ex.: python-requests/urllib) com 403 —
um User-Agent próprio é obrigatório. Token cacheado em processo até pouco antes de expirar.

Config em ``settings.SHOPMAN_IFOOD`` (env-driven). Inerte (retorna None) sem client_id/secret.

A recusa de borda também alcança o token (medido 19/09/2026)
-----------------------------------------------------------

O edge do Akamai recusa por origem da conexão, e o endpoint de autenticação não
é exceção: o worker publicado registrou ``iFood OAuth: HTTP 403`` no meio de uma
série de chamadas bem-sucedidas, com as mesmas credenciais. Por isso a chamada
de token retenta a recusa de edge, como as demais chamadas fazem em
``ifood_http`` — a classificação da recusa e o backoff vêm de ``ifood_edge``,
que fica abaixo dos dois e impede o ciclo (``ifood_http`` já chama este módulo
para obter o header; este módulo não pode chamá-lo de volta).

⚠️ O backoff aqui roda **sob o lock do módulo**, então é deliberadamente mais
curto que o do ``ifood_http``: ver ``_TOKEN_BACKOFF``.

"Sem token" tem três causas, e cada uma tem outro remédio
---------------------------------------------------------

``get_access_token`` devolvia ``None`` para tudo, e quem chamava traduzia esse
``None`` como "OAuth não configurado" — mandando quem depura conferir uma
variável de ambiente que estava certa. As causas são distintas:

- :data:`NOT_CONFIGURED` — falta ``client_id``/``client_secret``; nada foi enviado.
- :data:`TRANSPORT` — a requisição não chegou a ter resposta.
- :data:`DENIED_EDGE` — o Akamai recusou; retry resolve, e a ``referencia=`` no
  log é o que o suporte do iFood usa.
- :data:`DENIED_API` — o iFood recusou a credencial; retry nenhum resolve.
- :data:`INVALID_RESPONSE` — respondeu ``200`` sem token utilizável.

Quem precisa dizer a verdade ao operador usa :func:`headers_with_reason` /
:func:`token_with_reason` e :func:`failure_message`.
"""

from __future__ import annotations

import logging
import threading
import time

import requests
from django.conf import settings

from shopman.shop.services import ifood_edge

logger = logging.getLogger(__name__)

_TOKEN_PATH = "/authentication/v1.0/oauth/token"
USER_AGENT = "django-shopman/ifood-integration"
_EXPIRY_SKEW_SECONDS = 300  # renova 5 min antes do prazo informado pelo iFood

_DEFAULT_ATTEMPTS = 3
# Menor que o ``_DEFAULT_BACKOFF`` do ``ifood_http`` (0.75s) porque esta espera
# acontece com ``_lock`` tomado, e toda thread que precisar de token fica
# parada nela. Com 3 tentativas o pior caso soma ~0,75s de espera — uma fração
# do timeout da própria requisição, que já roda dentro do mesmo lock.
_TOKEN_BACKOFF = 0.25
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: Razões de "sem token". Ver o cabeçalho do módulo.
NOT_CONFIGURED = "not_configured"
TRANSPORT = "transport"
DENIED_EDGE = "denied_edge"
DENIED_API = "denied_api"
INVALID_RESPONSE = "invalid_response"

_FAILURE_MESSAGES = {
    NOT_CONFIGURED: "iFood OAuth is not configured (client_id/client_secret)",
    TRANSPORT: "iFood OAuth request never got a response (transport)",
    DENIED_EDGE: "iFood OAuth refused at the iFood edge (credentials are configured; see referencia= in the log)",
    DENIED_API: "iFood OAuth refused by the iFood API (credentials are configured but rejected)",
    INVALID_RESPONSE: "iFood OAuth answered without a usable token",
}

_lock = threading.Lock()
_cache: dict = {"token": None, "expires_at": 0.0}


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def _base_url() -> str:
    return str(_cfg().get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def _attempts() -> int:
    return max(1, int(_cfg().get("retry_attempts") or _DEFAULT_ATTEMPTS))


def _backoff() -> float:
    """Espera entre tentativas do token — chave própria, por causa do lock."""
    return max(0.0, float(_cfg().get("token_retry_backoff") or _TOKEN_BACKOFF))


def failure_message(reason: str) -> str:
    """Frase que diz a verdade sobre a falta de token, para log e erro ao chamador."""
    return _FAILURE_MESSAGES.get(reason, "iFood OAuth is unavailable")


def token_with_reason(*, force: bool = False) -> tuple[str | None, str]:
    """``(token, "")`` ou ``(None, razão)``. A razão é uma das constantes do módulo."""
    cfg = _cfg()
    client_id = str(cfg.get("client_id") or "").strip()
    client_secret = str(cfg.get("client_secret") or "").strip()
    if not (client_id and client_secret):
        logger.warning("iFood OAuth não configurado (client_id/client_secret)")
        return None, NOT_CONFIGURED

    with _lock:
        now = time.monotonic()
        if not force and _cache["token"] and now < _cache["expires_at"]:
            return _cache["token"], ""

        total = _attempts()
        backoff = _backoff()
        for attempt in range(1, total + 1):
            try:
                resp = requests.post(
                    f"{_base_url()}{_TOKEN_PATH}",
                    data={
                        "grantType": "client_credentials",
                        "clientId": client_id,
                        "clientSecret": client_secret,
                    },
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/x-www-form-urlencoded",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=int(cfg.get("timeout") or 30),
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                # Pedir token não tem efeito no iFood, então repetir é seguro
                # mesmo quando a conexão cai no meio — ao contrário do que vale
                # para as chamadas de escrita em ``ifood_http``.
                if attempt < total:
                    ifood_edge.sleep_backoff(backoff, attempt)
                    continue
                logger.warning("iFood OAuth: request falhou (%s)", type(exc).__name__)
                return None, TRANSPORT

            if resp.status_code == 403 and ifood_edge.denial_kind(resp) == ifood_edge.EDGE:
                # Recusa do Akamai, sorteada por requisição: nem a credencial
                # nem a rota mudaram. A referência é o que o suporte do iFood
                # usa para achar a regra — por isso vai inteira ao log.
                if attempt < total:
                    ifood_edge.sleep_backoff(backoff, attempt)
                    continue
                logger.warning(
                    "iFood OAuth: recusado pelo edge do iFood em %s tentativas — %s",
                    total,
                    # Sem corpo: numa recusa de autenticação ele pode ecoar o
                    # que enviamos, inclusive o clientSecret.
                    ifood_edge.forensics(resp, include_body=False),
                )
                return None, DENIED_EDGE

            if resp.status_code in _RETRYABLE_STATUS and attempt < total:
                ifood_edge.sleep_backoff(backoff, attempt)
                continue

            if resp.status_code != 200:
                logger.warning("iFood OAuth: HTTP %s", resp.status_code)
                return None, DENIED_API

            try:
                body = resp.json()
            except ValueError:
                logger.warning("iFood OAuth: resposta não-JSON")
                return None, INVALID_RESPONSE

            token = body.get("accessToken") or body.get("access_token")
            expires_in = int(body.get("expiresIn") or body.get("expires_in") or 0)
            if not token:
                logger.warning("iFood OAuth: resposta sem accessToken")
                return None, INVALID_RESPONSE

            _cache["token"] = token
            # Relógio do momento da resposta, não o da entrada no lock: com
            # retentativa e backoff os dois podem estar a segundos de distância.
            _cache["expires_at"] = time.monotonic() + max(0, expires_in - _EXPIRY_SKEW_SECONDS)
            if attempt > 1:
                logger.info("iFood OAuth: recuperado na tentativa %s de %s", attempt, total)
            logger.info("iFood OAuth: token renovado (expira em %ss)", expires_in)
            return token, ""

    # Inalcançável: todo caminho do laço devolve ou continua, e a última
    # tentativa nunca cai no ``continue``. Fica explícito para não devolver None
    # implícito se alguém mexer no laço.
    return None, TRANSPORT


def get_access_token(*, force: bool = False) -> str | None:
    """Retorna um Bearer token válido (cacheado), ou None se inerte/erro.

    Quem precisa saber **por que** faltou token usa :func:`token_with_reason`.
    """
    token, _reason = token_with_reason(force=force)
    return token


def headers_with_reason(extra: dict | None = None) -> tuple[dict | None, str]:
    """``(headers, "")`` ou ``(None, razão)`` — a forma honesta de :func:`authorized_headers`."""
    token, reason = token_with_reason()
    if not token:
        return None, reason
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if extra:
        headers.update(extra)
    return headers, ""


def authorized_headers(extra: dict | None = None) -> dict | None:
    """Headers (Bearer + User-Agent) prontos para as chamadas à API do iFood, ou None sem token."""
    headers, _reason = headers_with_reason(extra)
    return headers


def reset_cache() -> None:
    """Limpa o token cacheado (testes / refresh forçado)."""
    with _lock:
        _cache["token"] = None
        _cache["expires_at"] = 0.0


__all__ = [
    "get_access_token",
    "token_with_reason",
    "authorized_headers",
    "headers_with_reason",
    "failure_message",
    "reset_cache",
    "USER_AGENT",
    "NOT_CONFIGURED",
    "TRANSPORT",
    "DENIED_EDGE",
    "DENIED_API",
    "INVALID_RESPONSE",
]
