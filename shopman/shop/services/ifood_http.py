"""Camada HTTP única das chamadas ao iFood: retry, classificação da recusa e forense.

Por que existe (medido em 19/09/2026)
-------------------------------------

O polling publicado na DigitalOcean recebe ``HTTP 403`` com página HTML
``Access Denied`` em ~42% das tentativas: em uma hora de log, **um único token**
(renovado uma vez, na subida do worker) produziu 21 respostas boas e 15 recusas,
intercaladas. Do IP local, o mesmo código, a mesma rota e o mesmo tipo de token
responderam ``204`` em 24 de 24 tentativas.

Um token sem permissão não alterna entre `204` e `403` de minuto a minuto. A
recusa é do **edge** (Akamai), decidida por origem da conexão — o app na
DigitalOcean sai por um conjunto compartilhado de IPs de NAT, e parte desses IPs
é recusada. Não é escopo do token nem rota errada.

Deste diagnóstico saem as duas responsabilidades deste módulo:

1. **Retry com backoff.** Uma recusa de edge é sorteada por tentativa: com ~58%
   de sucesso em cada uma, três tentativas levam a falha de 42% para ~7%.
2. **Forense.** A página do Akamai traz um ``Reference #`` — o identificador que
   o suporte do iFood usa para achar a regra que bloqueou e o IP que eles viram.
   O log anterior cortava a resposta em 200 caracteres, exatamente antes dessa
   linha; foi por isso que o chamado 33298264 seguiu sem a prova que o resolveria.

Segurança do retry em chamadas de efeito
----------------------------------------

Retentar ``confirmar``/``despachar``/``cancelar``/``ACK`` seria perigoso se a
requisição pudesse ter chegado ao iFood. **Não pode**: a recusa de edge é
devolvida pelo Akamai, que não encaminha a requisição à origem. Por isso o retry
de recusa de edge é seguro para qualquer verbo, e é o único retry aplicado por
padrão a chamadas de escrita. Falha de transporte e ``5xx`` são ambíguas (a
origem pode ter processado), então só são retentadas quando quem chama declara
``idempotent=True``.
"""

from __future__ import annotations

import html
import logging
import random
import re
import time

import requests
from django.conf import settings

from shopman.shop.services import ifood_auth

logger = logging.getLogger(__name__)

# A recusa do edge vem como HTML, não JSON. A recusa da própria API do iFood vem
# como JSON e significa outra coisa (escopo/permissão) — remédio diferente.
EDGE = "edge"
API = "api"

_REFERENCE_RE = re.compile(r"Reference\s*#\s*([0-9A-Za-z.\-]+)")
# Cabeçalhos que ajudam a rastrear a recusa; nunca inclui Authorization.
_FORENSIC_HEADERS = ("x-ifood-request-id", "x-request-id", "x-correlation-id", "server", "date")

_DEFAULT_ATTEMPTS = 3
_DEFAULT_BACKOFF = 0.75  # segundos; dobra a cada tentativa, com jitter
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def base_url() -> str:
    return str(_cfg().get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def _timeout() -> int:
    return int(_cfg().get("timeout") or 30)


def _attempts() -> int:
    return max(1, int(_cfg().get("retry_attempts") or _DEFAULT_ATTEMPTS))


def _backoff() -> float:
    return max(0.0, float(_cfg().get("retry_backoff") or _DEFAULT_BACKOFF))


def denial_kind(resp: requests.Response) -> str:
    """``EDGE`` quando quem recusou foi o Akamai; ``API`` quando foi o iFood.

    A distinção decide o remédio: recusa de edge se resolve com retry e, se
    persistir, com liberação da origem junto ao iFood; recusa de API é escopo do
    token ou permissão do merchant, e retry nenhum resolve.
    """
    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "json" in content_type:
        return API
    body = (resp.text or "")[:2000]
    if "Access Denied" in body or "<HTML" in body.upper():
        return EDGE
    return API


def edge_reference(body: str) -> str:
    """O ``Reference #`` da página do Akamai, ou string vazia.

    O corpo vem com entidades HTML (``&#46;`` no lugar do ponto), então o texto
    é desescapado antes da busca — sem isso a referência não casa.
    """
    match = _REFERENCE_RE.search(html.unescape(body or ""))
    return match.group(1) if match else ""


def _forensics(resp: requests.Response) -> str:
    """Resumo rastreável da recusa, sem segredo nem dado de cliente."""
    parts = [f"http={resp.status_code}"]
    kind = denial_kind(resp)
    parts.append(f"recusa={kind}")
    if kind == EDGE:
        reference = edge_reference(resp.text or "")
        parts.append(f"referencia={reference or 'ausente'}")
    else:
        parts.append(f"corpo={(resp.text or '')[:300]}")
    for header in _FORENSIC_HEADERS:
        value = resp.headers.get(header)
        if value:
            parts.append(f"{header}={value}")
    return " ".join(parts)


def request(
    method: str,
    path: str,
    *,
    label: str,
    extra_headers: dict | None = None,
    idempotent: bool = False,
    attempts: int | None = None,
    **kwargs,
) -> requests.Response | None:
    """Chama a API do iFood com retry de recusa de edge. ``None`` sem token/desistência.

    ``label`` identifica a operação no log (ex.: ``"poll"``, ``"acknowledge"``).
    ``idempotent=True`` autoriza também o retry de ``5xx``/transporte, que são
    ambíguos para chamadas de efeito — ver o cabeçalho do módulo.
    """
    total = attempts if attempts is not None else _attempts()
    url = f"{base_url()}{path}"
    backoff = _backoff()
    last: requests.Response | None = None

    for attempt in range(1, total + 1):
        headers = ifood_auth.authorized_headers(extra_headers)
        if not headers:
            logger.warning("ifood_http.%s: OAuth não configurado — nada enviado", label)
            return None

        try:
            # Despacho por verbo (``requests.get``/``requests.post``) e não
            # ``requests.request``: é assim que a suíte intercepta as chamadas
            # ao iFood, e trocar o ponto de entrada cegaria os testes existentes.
            send = getattr(requests, method.lower())
            resp = send(url, headers=headers, timeout=_timeout(), **kwargs)
        except requests.RequestException as exc:
            # Transporte: só retenta quando a chamada é idempotente, porque a
            # origem pode ter processado antes de a conexão cair.
            if idempotent and attempt < total:
                _sleep(backoff, attempt)
                continue
            logger.warning("ifood_http.%s: transporte falhou (%s)", label, type(exc).__name__)
            return None

        last = resp
        if resp.status_code < 400:
            if attempt > 1:
                logger.info("ifood_http.%s: recuperado na tentativa %s de %s", label, attempt, total)
            return resp

        if resp.status_code == 401:
            # Token expirado/revogado: renova uma vez e repete. Não é o caso do
            # 403 de edge, que não tem nada a ver com o token.
            if attempt < total:
                ifood_auth.get_access_token(force=True)
                continue

        if resp.status_code == 403 and denial_kind(resp) == EDGE:
            # O Akamai recusou antes da origem: a requisição não teve efeito
            # nenhum, então repetir é seguro inclusive para escrita.
            if attempt < total:
                _sleep(backoff, attempt)
                continue
            logger.warning(
                "ifood_http.%s: recusado pelo edge do iFood em %s tentativas — %s",
                label, total, _forensics(resp),
            )
            return None

        if resp.status_code in _RETRYABLE_STATUS and idempotent and attempt < total:
            _sleep(backoff, attempt)
            continue

        logger.warning("ifood_http.%s: %s", label, _forensics(resp))
        return resp

    if last is not None:
        logger.warning("ifood_http.%s: esgotou %s tentativas — %s", label, total, _forensics(last))
    return None


def _sleep(backoff: float, attempt: int) -> None:
    """Espera exponencial com jitter, para não sincronizar retentativas."""
    if backoff <= 0:
        return
    delay = backoff * (2 ** (attempt - 1))
    time.sleep(delay * (0.5 + random.random() / 2))


__all__ = ["request", "denial_kind", "edge_reference", "base_url", "EDGE", "API"]
